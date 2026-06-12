"""Загрузка линейки продуктов POWERELIX и сборка компактного контекста для промпта."""
from __future__ import annotations

import json
from typing import Any

from .config import DATA_DIR

BRAND_FILE = DATA_DIR / "brand_powerelix.json"


def load_brand() -> dict[str, Any]:
    with BRAND_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def products_context() -> str:
    """Краткая текстовая выжимка по каждому продукту — то, что нужно SMM-щику
    (название, форма, курс, слоган, 3 пользы, ключевые БАВ, акцентный цвет)."""
    data = load_brand()
    brand = data["brand"]
    lines: list[str] = [
        f"БРЕНД: {brand['name']} — {brand.get('tagline', '')}. "
        f"Производитель: {brand.get('manufacturer', '')}. Сайт: {brand.get('site', '')}.",
        "",
        "ЛИНЕЙКА ПРОДУКТОВ:",
    ]
    for p in data["products"]:
        subs = p.get("active_substances") or []
        sub_str = ", ".join(
            s["name"]
            + (
                f" {s.get('amount_mg', s.get('amount_mcg', ''))}"
                f"{'мг' if 'amount_mg' in s else ('мкг' if 'amount_mcg' in s else '')}"
            ).rstrip()
            for s in subs[:6]
        )
        if not sub_str:
            sub_str = p.get("active_substances_summary", "")
        benefits = ", ".join(p.get("key_benefits_3", []))
        lines.append(
            f"#{p['id']} {p.get('full_name', p['name'])}\n"
            f"   форма: {p.get('form', '')}; курс: {p.get('duration_days', '')} дней; "
            f"приём: {p.get('dose_per_day', '')}\n"
            f"   слоган: «{p.get('slogan_main', '')}»; польза: {benefits}\n"
            f"   ключевые вещества: {sub_str}; акцентный цвет: {p.get('accent_color', '')}"
        )
    return "\n".join(lines)


def product_names() -> list[str]:
    return [p.get("full_name", p["name"]) for p in load_brand()["products"]]


def products_list() -> list[dict]:
    """Краткий список товаров для пикера/каталога: id, название, акцентный цвет."""
    return [
        {"id": str(p["id"]), "name": p.get("full_name", p["name"]),
         "accent": p.get("accent_color", "")}
        for p in load_brand()["products"]
    ]


def product_by_id(pid: str) -> dict | None:
    for p in load_brand()["products"]:
        if str(p["id"]) == str(pid):
            return p
    return None


def one_context(pid: str) -> str:
    """Детальный контекст ОДНОГО товара для генерации текста под него."""
    p = product_by_id(pid)
    if not p:
        return ""
    subs = ", ".join(s["name"] for s in (p.get("active_substances") or [])[:6]) \
        or p.get("active_substances_summary", "")
    benefits = ", ".join(p.get("key_benefits_3", []))
    return (
        f"ТОВАР: {p.get('full_name', p['name'])}\n"
        f"Форма: {p.get('form', '')}; курс: {p.get('duration_days', '')} дней; приём: {p.get('dose_per_day', '')}\n"
        f"Слоган: «{p.get('slogan_main', '')}»\n"
        f"Польза: {benefits}\n"
        f"Ключевые вещества: {subs}\n"
        f"Акцентный цвет: {p.get('accent_color', '')}"
    )
