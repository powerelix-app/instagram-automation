"""Стадия 3 — Генерация: визуал с лицом бренда (Grok) + текст поста (Claude)."""
from __future__ import annotations

import logging
import shutil
from typing import List, Optional

import anthropic
from pydantic import BaseModel, Field

from .. import config, scenes
from . import brand, compliance
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

# Стилевая подпись бренда в каждый визуал-промпт — чтобы кадр был «в духе» POWERELIX.
_BRAND_STYLE = (
    "молодая женщина — постоянное лицо бренда POWERELIX, та же внешность что на референсе; "
    "естественный свет, чистая современная эстетика здоровья и энергии, без текста"
)


# ── Визуал ──

def _visual_prompt(visual_idea: str, hook: str, product: str, with_product_ref: bool) -> str:
    parts: List[str] = []
    if visual_idea:
        parts.append(visual_idea)
    elif hook:
        parts.append(hook)
    if product and product not in ("", "—"):
        if with_product_ref:
            parts.append(
                f"в кадре — РЕАЛЬНАЯ банка продукта «{product}» как на референсе, "
                "этикетка читаема и не искажена, модель держит её в руках или рядом"
            )
        else:
            parts.append(f"в кадре уместно показать продукт: {product}")
    parts.append(_BRAND_STYLE)
    return ". ".join(parts)


# Соотношение сторон по формату: вертикальное видео 9:16, лента 4:5.
_FORMAT_RATIO = {"reels": "9:16", "stories": "9:16", "carousel": "4:5", "photo": "4:5"}


def generate_post_assets(post_id: int, ratio: Optional[str] = None) -> Optional[int]:
    """Генерит визуал с лицом бренда, кладёт в data/media, пишет PostAsset.
    ratio=None → выбирается по формату поста. Возвращает id ассета."""
    if not config.XAI_API_KEY:
        raise RuntimeError("Не задан XAI_API_KEY в .env (нужен для генерации визуала Grok)")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product, hook, visual_idea = post.product, post.hook, post.visual_idea
        ratio = ratio or _FORMAT_RATIO.get(post.format, "4:5")
        ord_ = s.query(PostAsset).filter(PostAsset.post_id == post_id).count()
        post.status = "generating"

    # Референсы: лицо бренда + (если есть) реальная банка этого товара.
    refs = [brand.model_ref()]
    prod_ref = brand.product_ref(product)
    if prod_ref:
        refs.append(prod_ref)
    prompt = _visual_prompt(visual_idea, hook, product, with_product_ref=bool(prod_ref))

    try:
        scene_path = scenes.generate_branded(
            prompt, refs=refs, ratio=ratio, out_name=f"post_{post_id}_{ord_}.png"
        )
        dest = config.MEDIA_DIR / f"post_{post_id}_{ord_}.png"
        shutil.copy(scene_path, dest)
    except Exception:
        with session_scope() as s:  # вернуть статус, не оставлять в «generating»
            p = s.get(Post, post_id)
            if p and p.status == "generating":
                p.status = "draft"
        raise

    with session_scope() as s:
        asset = PostAsset(post_id=post_id, kind="image", path=f"/media/{dest.name}",
                          model="grok-edit", prompt=prompt, ord=ord_)
        s.add(asset)
        p = s.get(Post, post_id)
        if p and p.status == "generating":
            p.status = "review"
        s.flush()
        return asset.id


# ── Текст (если у черновика нет подписи — напр. пришёл из идеи) ──

class TextOut(BaseModel):
    caption: str = Field(description="Готовая подпись к посту на русском, с эмодзи и абзацами, без хэштегов в конце")
    hashtags: List[str] = Field(description="8-15 релевантных хэштегов на русском без решёток")
    cta: str = Field(description="Короткий призыв к действию")


_TEXT_SYSTEM = """Ты — SMM-копирайтер бренда БАД POWERELIX (РФ). По хуку/идее напиши подпись поста.
ЖЁСТКО: БАД — не лекарство; нельзя «лечит/вылечивает/диагностирует/гарантирует результат»;
формулировки мягкие («поддерживает», «способствует», «помогает восполнить»); для продуктовых
постов добавь короткую плашку «БАД. Не является лекарственным средством». Пиши живо, на «ты».
Верни строго структуру по схеме."""


def generate_post_text(post_id: int) -> Optional[int]:
    """Догенерирует подпись/хэштеги/CTA через Claude. Возвращает post_id."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        brief = (
            f"Рубрика: {post.rubric or '—'}\nПродукт: {post.product or '—'}\n"
            f"Формат: {post.format}\nХук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}"
        )
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=2000, system=_TEXT_SYSTEM,
        messages=[{"role": "user", "content": f"Напиши текст поста:\n\n{brief}"}],
        output_format=TextOut,
    )
    out = resp.parsed_output
    with session_scope() as s:
        post = s.get(Post, post_id)
        post.caption = out.caption
        post.hashtags = out.hashtags
        post.cta = out.cta
        return post_id


# ── Аппрув + БАД-комплаенс (Фаза 5) ──

def check_compliance(post_id: int) -> Optional[dict]:
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None
        return compliance.check(p.hook, p.caption, p.visual_idea, p.cta, p.product)


def approve_post(post_id: int, override: bool = False) -> dict:
    """Проверяет комплаенс и одобряет. При нарушениях без override — блок."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"ok": False, "error": "пост не найден"}
        chk = compliance.check(post.hook, post.caption, post.visual_idea, post.cta, post.product)
        post.disclaimer_ok = chk["disclaimer_ok"]
        post.compliance_notes = compliance.summary(chk)
        if chk["blocked"] and not override:
            return {"ok": False, "blocked": True, **chk}
        post.status = "approved"
        if chk["blocked"] and override:
            post.compliance_notes = "ОВЕРРАЙД: " + post.compliance_notes
        return {"ok": True, **chk}


def add_disclaimer(post_id: int) -> bool:
    """Дописывает стандартный дисклеймер БАД в конец подписи (если его нет)."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return False
        if "не является лекарственным средством" not in (post.caption or "").lower():
            post.caption = ((post.caption or "").rstrip() + "\n\n" + compliance.DISCLAIMER).strip()
        return True


def back_to_review(post_id: int) -> bool:
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return False
        post.status = "review"
        return True


# ── для UI ──

def list_posts() -> List[dict]:
    with session_scope() as s:
        posts = s.query(Post).order_by(Post.id.desc()).all()
        out = []
        for p in posts:
            first = (
                s.query(PostAsset).filter(PostAsset.post_id == p.id)
                .order_by(PostAsset.ord).first()
            )
            out.append({
                "id": p.id, "rubric": p.rubric, "product": p.product, "format": p.format,
                "hook": p.hook, "status": p.status, "thumb": first.path if first else "",
            })
        return out


def get_post(post_id: int) -> Optional[dict]:
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None
        assets = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id)
            .order_by(PostAsset.ord).all()
        )
        return {
            "id": p.id, "rubric": p.rubric, "product": p.product, "format": p.format,
            "hook": p.hook, "caption": p.caption, "hashtags": p.hashtags or [],
            "visual_idea": p.visual_idea, "cta": p.cta, "status": p.status,
            "assets": [{"path": a.path, "model": a.model} for a in assets],
        }
