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


def scrape(account_id: int) -> int:
    """Тянет свежие посты источника (Apify) → TrendReel(topic=@handle). Возвращает сколько добавлено."""
    from . import recon
    from ..db.models import _now
    with session_scope() as s:
        a = s.get(SourceAccount, account_id)
        if not a:
            return 0
        handle = a.handle
    added = recon.scrape_account(handle, limit=30)
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
