"""Стадия 4 — БАД-комплаенс: линт стоп-слов + проверка дисклеймера перед публикацией.

Реклама БАД в РФ (ст. 25 ФЗ «О рекламе»): нельзя «лечит/вылечивает/диагностирует»,
гарантировать результат, заявлять лечение болезней; для продуктовых постов обязателен
дисклеймер «не является лекарственным средством». Эти правила ловит линт.
"""
from __future__ import annotations

from typing import Dict, List

# Запрещённые формулировки (подстроки, нижний регистр). Лечебные заявления, гарантии,
# лечение конкретных болезней. Мягкие «поддерживает/способствует/помогает восполнить» — ОК.
STOP_WORDS: List[str] = [
    "лечит", "лечат", "вылечива", "вылечит", "вылечи ", "излечива", "излечит",
    "исцеля", "исцелит", "лечение", "лечебн", "лечащ",
    "терапия", "терапевтическ",
    "диагноз", "диагностир",
    "панацея", "гарантиру", "100% результат", "стопроцентн",
    "избавляет от", "избавит от", "избавьтесь от", "избавляемся от",
    "снимает боль", "снимает воспаление", "обезболива", "заживляет",
    "от рака", "против рака", "от диабета", "от гипертони", "от депресс",
    "вылечить", "побеждает болезнь", "от болезни",
]

DISCLAIMER = (
    "БАД. Не является лекарственным средством. Имеются противопоказания, "
    "необходима консультация специалиста."
)
_DISCLAIMER_MARKERS = ["не является лекарственным средством", "не лекарство"]


def check(hook: str, caption: str, visual_idea: str = "", cta: str = "", product: str = "") -> Dict:
    """Проверка поста. Возвращает violations + статус дисклеймера."""
    blob = " ".join([hook or "", caption or "", visual_idea or "", cta or ""]).lower()
    violations = sorted({w.strip() for w in STOP_WORDS if w in blob})

    cap_low = (caption or "").lower()
    has_disclaimer = any(m in cap_low for m in _DISCLAIMER_MARKERS)
    is_product = bool(product and product.strip() not in ("", "—"))
    # дисклеймер обязателен для продуктовых постов
    disclaimer_ok = has_disclaimer or not is_product

    return {
        "violations": violations,
        "has_disclaimer": has_disclaimer,
        "is_product": is_product,
        "disclaimer_ok": disclaimer_ok,
        "blocked": bool(violations) or not disclaimer_ok,
    }


def summary(chk: Dict) -> str:
    parts = []
    if chk["violations"]:
        parts.append("стоп-слова: " + ", ".join(chk["violations"]))
    if not chk["disclaimer_ok"]:
        parts.append("нет дисклеймера БАД")
    return "; ".join(parts) or "чисто"
