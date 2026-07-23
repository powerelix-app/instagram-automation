"""Источники идей для разведки инфографик: сохранённый список аккаунтов
(конкуренты + иностранные доноры). Посты тянем через recon.scrape_account."""
from __future__ import annotations

import logging
from typing import List, Optional

from ..db.base import session_scope
from ..db.models import SourceAccount, TrendReel

log = logging.getLogger(__name__)


def _norm(handle: str) -> str:
    h = (handle or "").lstrip("@").strip().strip("/").split("/")[-1].split("?")[0]
    return "@" + h if h else ""


def add_account(handle: str, kind: str = "donor", note: str = "") -> Optional[int]:
    h = _norm(handle)
    if not h:
        return None
    kind = kind if kind in ("competitor", "donor") else "donor"
    with session_scope() as s:
        ex = s.query(SourceAccount).filter(SourceAccount.handle == h).first()
        if ex:
            return ex.id
        a = SourceAccount(handle=h, kind=kind, note=(note or "")[:255])
        s.add(a)
        s.flush()
        return a.id


def list_accounts() -> List[dict]:
    with session_scope() as s:
        rows = s.query(SourceAccount).order_by(SourceAccount.kind, SourceAccount.handle).all()
        out = []
        for a in rows:
            posts = s.query(TrendReel).filter(TrendReel.topic == a.handle).count()
            out.append({
                "id": a.id, "handle": a.handle, "kind": a.kind, "note": a.note,
                "active": a.active, "last_scraped": a.last_scraped, "posts": posts,
            })
        return out


def delete(account_id: int) -> None:
    with session_scope() as s:
        a = s.get(SourceAccount, account_id)
        if a:
            s.delete(a)


def scrape(account_id: int, top: bool = False, limit: int = 30) -> int:
    """Тянет посты источника (Apify) → TrendReel(topic=@handle). Возвращает сколько добавлено.
    top=True → сканируем широкое окно (limit×3) и оставляем топ-`limit` по просмотрам
    («что реально зашло»); top=False → последние `limit` (свежие)."""
    from . import recon
    from ..db.models import _now
    with session_scope() as s:
        a = s.get(SourceAccount, account_id)
        if not a:
            return 0
        handle = a.handle
    scan = limit * 3 if top else None
    added = recon.scrape_account(handle, limit=limit, scan_limit=scan)
    with session_scope() as s:
        a = s.get(SourceAccount, account_id)
        if a:
            a.last_scraped = _now()
    return added


def generate_ideas(source_id: Optional[int] = None, n: int = 6) -> int:
    """Кирпич 3 — банк идей: Claude генерит N ОРИГИНАЛЬНЫХ концептов инфографик под наши
    товары по виральным форматам ниши. source_id → опираясь на посты этого источника
    (что реально заходит); None → с нуля. Кладёт в общий Банк идей (таблица ideas)."""
    import anthropic
    from pydantic import BaseModel, Field
    from .. import config, products
    from .ideas import add_idea

    brand = products.load_brand()
    cat = "\n".join(f'#{p["id"]} {p.get("full_name", p["name"])} — {", ".join(p.get("key_benefits_3", []))}'
                    for p in brand["products"])
    src_ctx, src_tag = "", "manual"
    if source_id:
        with session_scope() as s:
            a = s.get(SourceAccount, source_id)
            handle = a.handle if a else ""
        if handle:
            with session_scope() as s:
                reels = (s.query(TrendReel).filter(TrendReel.topic == handle)
                         .order_by(TrendReel.play_count.desc()).limit(15).all())
                lines = [f'- [{r.play_count} просм.] {(r.caption or "").strip()[:160]}' for r in reels if r.caption]
            if lines:
                src_ctx = (f"\n\nВИРАЛЬНЫЕ ПОСТЫ ИСТОЧНИКА {handle} (по убыванию просмотров) — учись на их "
                           f"форматах/крючках, но НЕ копируй:\n" + "\n".join(lines))
                src_tag = "trend"

    class _Idea(BaseModel):
        title: str = Field(description="цепляющий заголовок инфографики на русском")
        format: str = Field(description="формат: симптом→продукт | список-чеклист | 2 колонки сравнение | таймлайн-стадии | миф-разоблачение")
        concept: str = Field(description="описание концепта: что в кадре, структура блоков, посыл — 2-4 предложения")
        product_ids: list[str] = Field(description="id наших товаров, которые ложатся в концепт")
        formula: str = Field(description="почему зайдёт: виральная формула/крючок")

    class _Out(BaseModel):
        ideas: list[_Idea]

    prompt = (
        f"Ты — креативщик инфографик-Reels для БАД-бренда POWERELIX (козыри бренда: 274000+ продаж, "
        f"нутрициологи в команде, европейское сырьё, стандарт GMP). Придумай {n} ОРИГИНАЛЬНЫХ концептов "
        f"инфографик под наши товары, используя виральные форматы ниши (симптом→продукт, списки-чеклисты, "
        f"сравнения 2 колонки, таймлайны стадий, мифы-разоблачения). ВАЖНО: не копируй референсы — свой угол, "
        f"свои заголовки, наши товары и наши козыри. Юр-рамка БАД РФ: без «лечит/гарантирует», мягкие "
        f"формулировки.{src_ctx}\n\nНАШИ ТОВАРЫ:\n{cat}"
    )
    client = anthropic.Anthropic()
    resp = client.messages.parse(model=config.CLAUDE_MODEL, max_tokens=3500,
                                 messages=[{"role": "user", "content": prompt}], output_format=_Out)
    cnt = 0
    for it in resp.parsed_output.ideas:
        pnames = ", ".join(str(x).strip().lstrip("#") for x in it.product_ids)
        text = (f"{it.concept}\n\n📐 Формат: {it.format}\n🎯 Почему зайдёт: {it.formula}"
                + (f"\n🫙 Товары: {pnames}" if pnames else ""))
        add_idea(text=text, hook=it.title, rubric=f"инфографика · {it.format}", product=pnames)
        cnt += 1
    return cnt


def generate_from_idea(idea_id: int, ratio: str = "4:5") -> str:
    """Кирпич 4: концепт идеи → готовая инфографика (gpt-image + наши банки + бренд-стиль)."""
    import time
    from .. import config
    from . import producer
    from ..db.models import Idea
    with session_scope() as s:
        idea = s.get(Idea, idea_id)
        if not idea:
            raise ValueError("идея не найдена")
        title, concept, prod = idea.hook or "", idea.text or "", idea.product or ""
    pids = [p.strip().lstrip("#") for p in prod.replace(";", ",").split(",") if p.strip()]
    refs = []
    for pid in pids:
        r = producer._product_ref(pid)
        if r:
            refs.append(r)
    ratio = ratio if ratio in ("4:5", "9:16", "1:1", "3:4") else "4:5"
    prompt = (
        f"Создай ВЕРТИКАЛЬНУЮ инфографику-Reels бренда БАД POWERELIX. Заголовок: «{title}». "
        f"Концепт и структура: {concept}. "
        "Премиальный современный дизайн, фирменная зелень POWERELIX (лайм #C3FF08 → мята #16FFB3) как акцент, "
        "чистый фон, аккуратные иконки и блоки, вордмарк «POWERELIX» сверху. "
        + ("Используй НАШИ банки из референс-изображений — форма и этикетка строго как на них. " if refs else "")
        + "Весь текст — чистый, читаемый РУССКИЙ, крупные заголовки. Без чужого бренда и водяных знаков. "
        "Юр-рамка БАД: без «лечит/гарантирует». Оставь поля по краям — ничего не обрезано по краям."
    )
    img = producer.gen_image_gpt(prompt, refs, aspect=ratio)
    out_dir = config.MEDIA_DIR / "infographics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"idea_{idea_id}_{int(time.time())}.png"
    out.write_bytes(img)
    rel = f"/media/infographics/{out.name}"
    with session_scope() as s:
        idea = s.get(Idea, idea_id)
        if idea:
            idea.image_path = rel
            idea.status = "in_work"
    return rel


def start_from_idea(idea_id: int, ratio: str = "4:5") -> None:
    """Запуск генерации инфографики из идеи в фоновом потоке (gpt-image ~2-3 мин)."""
    import threading
    with session_scope() as s:
        from ..db.models import Idea
        idea = s.get(Idea, idea_id)
        if idea:
            idea.status = "gen"  # «генерится»

    def _run():
        try:
            generate_from_idea(idea_id, ratio)
        except Exception as e:
            log.warning("infographic from idea %s failed: %s", idea_id, e)
            with session_scope() as s:
                from ..db.models import Idea
                idea = s.get(Idea, idea_id)
                if idea:
                    idea.status = "new"
    threading.Thread(target=_run, daemon=True).start()
