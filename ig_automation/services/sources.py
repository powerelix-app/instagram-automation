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
