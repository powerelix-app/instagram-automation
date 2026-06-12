"""Каталог товаров + артикулы/ссылки WB (для вставки в текст поста)."""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import products
from ..db.base import session_scope
from ..db.models import ProductLink


def get_link(pid: str) -> Optional[dict]:
    with session_scope() as s:
        x = s.get(ProductLink, str(pid))
        if not x:
            return None
        return {"nmid": x.nmid, "wb_url": x.wb_url, "note": x.note}


def set_link(pid: str, nmid: str = "", wb_url: str = "", note: str = "") -> None:
    with session_scope() as s:
        x = s.get(ProductLink, str(pid))
        if not x:
            x = ProductLink(product_id=str(pid))
            s.add(x)
        x.nmid = (nmid or "").strip()
        x.wb_url = (wb_url or "").strip()
        x.note = (note or "").strip()


def all_with_links() -> List[dict]:
    """Товары каталога + их артикулы/ссылки (для страницы /catalog)."""
    with session_scope() as s:
        links = {x.product_id: x for x in s.query(ProductLink).all()}
        out = []
        for p in products.products_list():
            x = links.get(p["id"])
            out.append({
                "id": p["id"], "name": p["name"], "accent": p["accent"],
                "nmid": x.nmid if x else "", "wb_url": x.wb_url if x else "",
                "note": x.note if x else "",
            })
        return out


def link_line(pid: str) -> str:
    """Готовая строка про где купить (для подсказки Claude)."""
    lk = get_link(pid)
    if not lk:
        return ""
    parts = []
    if lk["nmid"]:
        parts.append(f"артикул Wildberries: {lk['nmid']}")
    if lk["wb_url"]:
        parts.append(f"ссылка: {lk['wb_url']}")
    if lk["note"]:
        parts.append(lk["note"])
    return "; ".join(parts)
