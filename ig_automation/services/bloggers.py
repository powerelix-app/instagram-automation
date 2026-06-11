"""Движок Б — UGC-CRM: блогеры + сделки + воронка. Не зависит от генерации/Grok."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..db.base import session_scope
from ..db.models import Blogger, Deal

# Воронка работы с блогером (порядок = стадии).
STAGES: List[tuple] = [
    ("lead", "Лид"), ("qualify", "Квалификация"), ("contacted", "Контакт"),
    ("negotiating", "Переговоры"), ("agreed", "Согласовано"), ("shipped", "Товар отправлен"),
    ("content", "Контент"), ("review", "Аппрув"), ("published", "Опубликовано"),
    ("paid", "Оплачено"), ("repeat", "Повтор"),
]
STAGE_LABELS = dict(STAGES)
STATUS_LABELS = {"lead": "Лид", "active": "Активный", "ambassador": "Амбассадор", "blacklist": "Чёрный список"}


# ── Блогеры ──

def list_bloggers() -> List[Blogger]:
    with session_scope() as s:
        return s.query(Blogger).order_by(Blogger.id.desc()).all()


def add_blogger(**f) -> int:
    with session_scope() as s:
        b = Blogger(
            name=f.get("name", "").strip(), handle=f.get("handle", "").strip(),
            platform=f.get("platform", "instagram"), url=f.get("url", "").strip(),
            niche=f.get("niche", "").strip(), followers=int(f.get("followers") or 0),
            er=f.get("er", "").strip(), city=f.get("city", "").strip(),
            audience=f.get("audience", "").strip(), contact=f.get("contact", "").strip(),
            collab_type=f.get("collab_type", "gift"), usual_rate=f.get("usual_rate", "").strip(),
            notes=f.get("notes", "").strip(),
        )
        s.add(b)
        s.flush()
        return b.id


def get_blogger(bid: int) -> Optional[dict]:
    with session_scope() as s:
        b = s.get(Blogger, bid)
        if not b:
            return None
        deals = s.query(Deal).filter(Deal.blogger_id == bid).order_by(Deal.id.desc()).all()
        return {
            "b": b,
            "deals": [_deal_dict(d) for d in deals],
        }


def set_status(bid: int, status: str) -> None:
    with session_scope() as s:
        b = s.get(Blogger, bid)
        if b:
            b.status = status


def delete_blogger(bid: int) -> None:
    with session_scope() as s:
        for d in s.query(Deal).filter(Deal.blogger_id == bid).all():
            s.delete(d)
        b = s.get(Blogger, bid)
        if b:
            s.delete(b)


# ── Сделки ──

def _deal_dict(d: Deal) -> dict:
    return {
        "id": d.id, "blogger_id": d.blogger_id, "product": d.product, "stage": d.stage,
        "stage_label": STAGE_LABELS.get(d.stage, d.stage), "outcome": d.outcome,
        "collab_type": d.collab_type, "platform": d.platform, "promo_code": d.promo_code,
        "replacement_article": d.replacement_article, "utm": d.utm, "erid": d.erid,
        "offer_value": d.offer_value, "tracking": d.tracking, "post_url": d.post_url,
        "attributed_orders": d.attributed_orders, "attributed_revenue": d.attributed_revenue,
        "notes": d.notes,
    }


def add_deal(blogger_id: int, product: str = "", collab_type: str = "gift", platform: str = "") -> int:
    with session_scope() as s:
        d = Deal(blogger_id=blogger_id, product=product.strip(), collab_type=collab_type,
                 platform=platform.strip(), stage="lead")
        s.add(d)
        s.flush()
        return d.id


def set_deal_stage(deal_id: int, stage: str) -> None:
    with session_scope() as s:
        d = s.get(Deal, deal_id)
        if d and stage in STAGE_LABELS:
            d.stage = stage


def set_deal_outcome(deal_id: int, outcome: str) -> None:
    with session_scope() as s:
        d = s.get(Deal, deal_id)
        if d:
            d.outcome = outcome


_DEAL_FIELDS = ("product", "platform", "promo_code", "replacement_article", "utm", "erid",
                "offer_value", "tracking", "post_url", "notes")


def update_deal(deal_id: int, **f) -> None:
    with session_scope() as s:
        d = s.get(Deal, deal_id)
        if not d:
            return
        for k in _DEAL_FIELDS:
            if k in f:
                setattr(d, k, (f[k] or "").strip())
        if "attributed_orders" in f:
            d.attributed_orders = int(f["attributed_orders"] or 0)
        if "attributed_revenue" in f:
            d.attributed_revenue = int(f["attributed_revenue"] or 0)


def pipeline() -> List[dict]:
    """Сделки, сгруппированные по стадиям (для доски-воронки)."""
    with session_scope() as s:
        deals = s.query(Deal).filter(Deal.outcome == "open").all()
        blmap = {b.id: b for b in s.query(Blogger).all()}
        cols = []
        for key, label in STAGES:
            items = [
                {"deal": _deal_dict(d), "blogger": blmap.get(d.blogger_id)}
                for d in deals if d.stage == key
            ]
            cols.append({"key": key, "label": label, "cards": items})
        return cols
