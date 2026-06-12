"""Стадия 3 — Генерация: визуал с лицом бренда (Grok) + текст поста (Claude)."""
from __future__ import annotations

import logging
import re
import shutil
from typing import List, Optional

import anthropic
from pydantic import BaseModel, Field

from .. import config, overlay, products, scenes
from . import brand, catalog, compliance
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

# Стилевая подпись бренда в каждый визуал-промпт — чтобы кадр был «в духе» POWERELIX.
_BRAND_STYLE = (
    "молодая женщина — постоянное лицо бренда POWERELIX, та же внешность что на референсе; "
    "естественный свет, чистая современная эстетика здоровья и энергии, без текста"
)


# ── Визуал ──

# Убираем из сцены упоминания текста/надписей и CAPS-блоки (это контент плашек —
# AI всё равно рисует его коряво; настоящий текст накладываем оверлеем отдельно).
_TEXT_HINT_RE = re.compile(
    r"(текст на экране|надпис\w*|плашк\w*|кодовое слово|дисклеймер|заголов\w*|субтитр\w*|"
    r"caption|on-?screen)[^.;]*[.;]?", re.IGNORECASE)
_CAPS_RE = re.compile(r"[А-ЯЁA-Z]{3,}(?:[\s,«»\"'–-]+[А-ЯЁA-Z]{2,})*")


def _clean_scene(text: str) -> str:
    text = _TEXT_HINT_RE.sub("", text or "")
    text = _CAPS_RE.sub("", text)
    text = re.sub(r"[«»\"']", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()[:200]


def _visual_prompt(visual_idea: str, hook: str, product: str, with_product_ref: bool) -> str:
    parts: List[str] = ["профессиональная чистая лайфстайл-фотография для Instagram, реалистичная"]
    scene = _clean_scene(visual_idea) or _clean_scene(hook)
    if scene:
        parts.append(scene)
    if product and product not in ("", "—"):
        if with_product_ref:
            parts.append("в руках реальная банка продукта как на референсе, этикетка читаема и не искажена")
        else:
            parts.append(f"уместно показать продукт {product}")
    parts.append(_BRAND_STYLE)
    parts.append(
        "БЕЗ ТЕКСТА в кадре: никаких букв, слов, надписей, плашек, подписей, этикеток с текстом; "
        "no text, no letters, no words, no captions, no labels, no writing anywhere; "
        "оставь чистое пространство для наложения текста потом"
    )
    return ". ".join(parts)


# Соотношение сторон по формату: вертикальное видео 9:16, лента 4:5.
_FORMAT_RATIO = {"reels": "9:16", "stories": "9:16", "carousel": "4:5", "photo": "4:5"}


def _apply_logo(image_path) -> None:
    """Накладывает логотип бренда (если загружен в /brand) в правый нижний угол."""
    logo = brand.logo_ref()
    if not logo:
        return
    try:
        from PIL import Image
        base = Image.open(image_path).convert("RGBA")
        lg = Image.open(logo).convert("RGBA")
        w = int(base.width * 0.18)
        h = max(1, int(lg.height * w / lg.width))
        lg = lg.resize((w, h), Image.LANCZOS)
        m = int(base.width * 0.04)
        base.alpha_composite(lg, (base.width - w - m, base.height - h - m))
        base.convert("RGB").save(image_path)
    except Exception as e:
        log.warning("logo overlay failed: %s", e)


def generate_post_assets(post_id: int, ratio: Optional[str] = None, extra: str = "") -> Optional[int]:
    """Генерит визуал с лицом бренда, кладёт в data/media, пишет PostAsset.
    ratio=None → по формату поста; extra → доп. подсказка к промпту (для слайдов карусели).
    Возвращает id ассета."""
    if not config.XAI_API_KEY:
        raise RuntimeError("Не задан XAI_API_KEY в .env (нужен для генерации визуала Grok)")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product, hook, visual_idea = post.product, post.hook, post.visual_idea
        ratio = ratio or _FORMAT_RATIO.get(post.format, "4:5")
        ord_ = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image").count()
        # пользовательские референсы поста (банка/сцена) — kind="ref"
        user_refs = [
            config.MEDIA_DIR / a.path.replace("/media/", "", 1)
            for a in s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "ref").all()
        ]
        post.status = "generating"

    # Референсы: лицо бренда + (если есть) реальная банка товара + ручные референсы поста.
    refs = [brand.model_ref()]
    prod_ref = brand.product_ref(product)
    if prod_ref:
        refs.append(prod_ref)
    refs += [p for p in user_refs if p.exists()]
    prompt = _visual_prompt(visual_idea, hook, product, with_product_ref=bool(prod_ref))
    if extra:
        prompt += ". " + extra

    try:
        scene_path = scenes.generate_branded(
            prompt, refs=refs, ratio=ratio, out_name=f"post_{post_id}_{ord_}.png"
        )
        dest = config.MEDIA_DIR / f"post_{post_id}_{ord_}.png"
        shutil.copy(scene_path, dest)
        _apply_logo(dest)
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


_SLIDE_HINTS = [
    "",  # слайд 1 — герой: лицо бренда + продукт
    "крупный план продукта на чистом светлом столе, мягкий студийный свет, минимализм",
    "лайфстайл: модель использует продукт в повседневной обстановке, естественно",
    "макро-детали продукта и текстуры, свежесть, аппетитный кадр",
    "продукт рядом с натуральными ингредиентами (фрукты, зелень), чистая эстетика",
]


def generate_carousel(post_id: int, slides: int = 4) -> int:
    """Генерит N слайдов карусели (герой + контент-кадры в стиле бренда). Каждый слайд
    добавляется как PostAsset (ord по порядку). Возвращает кол-во созданных слайдов."""
    slides = max(2, min(slides, 8))
    made = 0
    for i in range(slides):
        hint = _SLIDE_HINTS[i] if i < len(_SLIDE_HINTS) else "ещё один кадр в фирменном стиле бренда"
        try:
            if generate_post_assets(post_id, extra=hint):
                made += 1
        except Exception as e:
            log.warning("carousel slide %d failed: %s", i, e)
    return made


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


def set_post_product(post_id: int, product_id: str) -> None:
    """Привязывает пост к конкретному товару каталога (id + каноничное название)."""
    p = products.product_by_id(product_id)
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return
        post.product_id = str(product_id) if p else ""
        if p:
            post.product = p.get("full_name", p.get("name", ""))


def set_post_blogger(post_id: int, blogger_id: str) -> None:
    """Привязывает пост к блогеру (контент для него) или к своему аккаунту (пусто)."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return
        post.blogger_id = int(blogger_id) if blogger_id else None


def generate_post_text(post_id: int) -> Optional[int]:
    """Догенерирует подпись/хэштеги/CTA через Claude под конкретный товар (если привязан),
    с вставкой артикула/ссылки WB. Возвращает post_id."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        pid = post.product_id
        brief = (
            f"Рубрика: {post.rubric or '—'}\nФормат: {post.format}\n"
            f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}"
        )
    if pid:
        ctx = products.one_context(pid)
        link = catalog.link_line(pid)
        if ctx:
            brief += "\n\n" + ctx
        if link:
            brief += (
                f"\n\nГДЕ КУПИТЬ ({link}). В конце подписи добавь призыв с этим артикулом/ссылкой "
                "(в Instagram ссылка некликабельна — пиши «ищи на Wildberries, артикул XXXX» "
                "или «ссылка в шапке профиля»)."
            )
    else:
        brief = f"Продукт: {post.product or '—'}\n" + brief
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=2000, system=_TEXT_SYSTEM,
        messages=[{"role": "user", "content": f"Напиши текст поста под этот товар:\n\n{brief}"}],
        output_format=TextOut,
    )
    out = resp.parsed_output
    caption = out.caption
    # Гарантируем артикул/ссылку WB В САМОЙ подписи (Claude иногда кладёт в CTA).
    if pid:
        lk = catalog.get_link(pid)
        if lk and lk.get("nmid") and lk["nmid"] not in caption:
            buy = f"\n\n🛒 На Wildberries — артикул {lk['nmid']}"
            if lk.get("wb_url"):
                buy += f"\n{lk['wb_url']}"
            caption = caption.rstrip() + buy
    with session_scope() as s:
        post = s.get(Post, post_id)
        post.caption = caption
        post.hashtags = out.hashtags
        post.cta = out.cta
        return post_id


# ── Reels: сценарий + раскадровка + видео ──

class ReelsScene(BaseModel):
    visual: str = Field(description="что в кадре — раскадровка сцены")
    onscreen: str = Field(description="текст на экране для этой сцены (рус.)")
    voiceover: str = Field(description="закадровый текст/реплика (рус.)")


class ReelsScript(BaseModel):
    hook: str = Field(description="хук первых 0-3 секунд")
    scenes: List[ReelsScene] = Field(description="3-5 сцен — раскадровка по порядку")
    cta: str = Field(description="призыв в конце (с упоминанием WB-артикула, если есть)")
    duration_sec: int = Field(description="рекомендованная длина, сек (15-45)")
    audio: str = Field(description="идея звука/музыки/тренда")


_REELS_SYSTEM = """Ты — сценарист коротких вертикальных видео (Reels) для бренда БАД POWERELIX,
аудитория РУССКОЯЗЫЧНАЯ. По идее поста напиши СЦЕНАРИЙ Reels: хук 0-3 сек, 3-5 сцен
(раскадровка: что в кадре + текст на экране + закадровый текст), CTA, длину, идею звука.
Юр-правила рекламы БАД РФ: без «лечит/диагностирует/гарантирует», мягкие формулировки,
в конце дисклеймер «не является лекарственным средством». Пиши живо, на «ты», по-русски.
Верни строго структуру по схеме."""


def generate_reels_script(post_id: int) -> Optional[int]:
    """Claude пишет сценарий+раскадровку Reels по идее поста. Сохраняет в post.reels_script."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        brief = f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}\nРубрика: {post.rubric or '—'}"
        pid = post.product_id
    if pid:
        ctx = products.one_context(pid)
        if ctx:
            brief += "\n\n" + ctx
        link = catalog.link_line(pid)
        if link:
            brief += f"\n\nГде купить (упомяни в CTA): {link}"
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=3000, system=_REELS_SYSTEM,
        messages=[{"role": "user", "content": f"Сценарий Reels по идее:\n\n{brief}"}],
        output_format=ReelsScript,
    )
    with session_scope() as s:
        post = s.get(Post, post_id)
        post.reels_script = resp.parsed_output.model_dump(mode="json")
        return post_id


def generate_reels_video(post_id: int) -> Optional[int]:
    """hero-кадр 9:16 с лицом бренда → image→video (Replicate). PostAsset kind=video."""
    if not config.REPLICATE_API_TOKEN:
        raise RuntimeError("Не задан REPLICATE_API_TOKEN (нужен для видео)")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product, hook, visual_idea = post.product, post.hook, post.visual_idea
        n = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "video").count()
        post.status = "generating"
    refs = [brand.model_ref()]
    pr = brand.product_ref(product)
    if pr:
        refs.append(pr)
    prompt = _visual_prompt(visual_idea, hook, product, with_product_ref=bool(pr))
    try:
        hero = scenes.generate_branded(prompt, refs=refs, ratio="9:16", out_name=f"reelhero_{post_id}_{n}.png")
        hero_media = config.MEDIA_DIR / f"reelhero_{post_id}_{n}.png"
        shutil.copy(hero, hero_media)  # в /media → Replicate скачает hero по URL (короткий POST)
        video = scenes.generate_video(hero_media, prompt="natural cinematic motion, soft lighting",
                                      duration=5, aspect_ratio="9:16", out_name=f"reel_{post_id}_{n}.mp4")
        dest = config.MEDIA_DIR / f"reel_{post_id}_{n}.mp4"
        shutil.copy(video, dest)
    except Exception:
        with session_scope() as s:
            p = s.get(Post, post_id)
            if p and p.status == "generating":
                p.status = "review"
        raise
    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="video", path=f"/media/{dest.name}", model="grok-video",
                      prompt=prompt, ord=n)
        s.add(a)
        p = s.get(Post, post_id)
        if p and p.status == "generating":
            p.status = "review"
        s.flush()
        return a.id


# ── Текст-оверлей: чёткие плашки поверх чистой картинки (Pillow) ──

class OverlayText(BaseModel):
    headline: str = Field(description="цепкий заголовок для картинки, 2-5 слов, БЕЗ кавычек и точки")
    points: List[str] = Field(description="2-4 коротких пункта-тезиса по 2-4 слова (не предложения!), без точек")
    disclaimer: str = Field(description="для продуктовых постов 'БАД. Не лекарство', иначе пустая строка")


_OVERLAY_SYSTEM = """Ты — дизайнер-копирайтер инфографики Instagram для бренда БАД POWERELIX (РФ).
Придумай ЛАКОНИЧНЫЙ текст ДЛЯ НАЛОЖЕНИЯ на картинку: цепкий заголовок + 2-4 пункта-плашки.
Очень коротко: плашки — это тезисы по 2-4 слова, НЕ предложения. На русском, на «ты», без воды.
БАД-правила РФ: без «лечит/диагностирует/гарантирует», мягкие формулировки. Верни строго по схеме."""


def suggest_overlay_text(post_id: int) -> dict:
    """Claude придумывает короткий текст для наложения (заголовок + 2-4 плашки + дисклеймер)."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"headline": "", "points": [], "disclaimer": ""}
        brief = (
            f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}\n"
            f"Рубрика: {post.rubric or '—'}\nПродукт: {post.product or '—'}"
        )
        pid = post.product_id
    if pid:
        ctx = products.one_context(pid)
        if ctx:
            brief += "\n\n" + ctx
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=800, system=_OVERLAY_SYSTEM,
        messages=[{"role": "user", "content": f"Текст для наложения на картинку поста:\n\n{brief}"}],
        output_format=OverlayText,
    )
    o = resp.parsed_output
    return {"headline": o.headline, "points": [p for p in o.points if p][:4], "disclaimer": o.disclaimer}


def apply_text_overlay(post_id: int, source_asset_id: Optional[int] = None,
                       headline: Optional[str] = None, points: Optional[List[str]] = None,
                       disclaimer: Optional[str] = None) -> Optional[int]:
    """Накладывает текст на чистую картинку (источник или последний визуал) → новый ассет.
    Если текст не передан — придумывает через Claude. Композит помечается model='overlay'."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        q = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image")
        if source_asset_id:
            src = s.get(PostAsset, int(source_asset_id))
        else:  # последний «чистый» визуал (не оверлей)
            src = q.filter(PostAsset.model != "overlay").order_by(PostAsset.ord.desc()).first()
        if not src:
            raise RuntimeError("Нет картинки для наложения — сначала сгенерируй визуал")
        src_path = config.MEDIA_DIR / src.path.replace("/media/", "", 1)
        ord_ = q.count()
    if headline is None and points is None:
        txt = suggest_overlay_text(post_id)
        headline, points, disclaimer = txt["headline"], txt["points"], txt["disclaimer"]
    points = [p for p in (points or []) if p]
    dest = config.MEDIA_DIR / f"post_{post_id}_txt{ord_}.png"
    overlay.render(src_path, points=points, headline=headline or "",
                   disclaimer=disclaimer or "", out_path=str(dest))
    _apply_logo(dest)
    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="image", path=f"/media/{dest.name}", model="overlay",
                      prompt=((headline or "") + " | " + " / ".join(points))[:300], ord=ord_)
        s.add(a)
        s.flush()
        return a.id


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
                s.query(PostAsset).filter(PostAsset.post_id == p.id, PostAsset.kind == "image")
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
            "id": p.id, "rubric": p.rubric, "product": p.product, "product_id": p.product_id,
            "format": p.format,
            "hook": p.hook, "caption": p.caption, "hashtags": p.hashtags or [],
            "visual_idea": p.visual_idea, "cta": p.cta, "status": p.status,
            "scheduled_at": p.scheduled_at, "ig_media_id": p.ig_media_id,
            "permalink": p.permalink, "error": p.error, "reels_script": p.reels_script,
            "blogger_id": p.blogger_id,
            "assets": [{"id": a.id, "path": a.path, "model": a.model} for a in assets if a.kind == "image"],
            "refs": [{"id": a.id, "path": a.path} for a in assets if a.kind == "ref"],
            "videos": [{"id": a.id, "path": a.path} for a in assets if a.kind == "video"],
        }


def add_post_ref(post_id: int, file_bytes: bytes, filename: str) -> Optional[int]:
    """Загружает референс под пост (банка/сцена) — будет добавлен в генерацию."""
    import hashlib
    from pathlib import Path
    ext = Path(filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("формат не поддерживается (PNG/JPG/WEBP)")
    if not file_bytes:
        raise ValueError("пустой файл")
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"ref_{post_id}_{hashlib.md5(file_bytes).hexdigest()[:8]}{ext}"
    (config.MEDIA_DIR / name).write_bytes(file_bytes)
    with session_scope() as s:
        n = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "ref").count()
        a = PostAsset(post_id=post_id, kind="ref", path=f"/media/{name}", model="upload", ord=n)
        s.add(a)
        s.flush()
        return a.id


def delete_post_asset(asset_id: int) -> None:
    with session_scope() as s:
        a = s.get(PostAsset, asset_id)
        if not a:
            return
        try:
            (config.MEDIA_DIR / a.path.replace("/media/", "", 1)).unlink()
        except OSError:
            pass
        s.delete(a)
