#!/usr/bin/env python3
"""CLI: сгенерировать контент-план для Instagram POWERELIX.

Примеры:
    python generate_plan.py                       # 15 постов, старт завтра, пн-пт
    python generate_plan.py --posts 10 --start 2026-06-15
    python generate_plan.py --focus "запуск Омега-3 и коллагена"
    python generate_plan.py --model claude-haiku-4-5   # дешевле
"""
from __future__ import annotations

import argparse
import json

from ig_automation import config
from ig_automation.config import OUTPUT_DIR
from ig_automation.content_plan import ContentPlan, generate


def to_markdown(plan: ContentPlan) -> str:
    out = [
        f"# Контент-план Instagram POWERELIX — {plan.period}",
        "",
        f"**Стратегия:** {plan.strategy_summary}",
        "",
        "**Рубрики:**",
        *[f"- {r}" for r in plan.rubrics_legend],
        "",
        "---",
        "",
    ]
    for i, p in enumerate(plan.posts, 1):
        out += [
            f"## {i}. {p.date} ({p.weekday}) — {p.format.value}",
            f"**Рубрика:** {p.rubric}  |  **Продукт:** {p.product}",
            "",
            f"**Хук:** {p.hook}",
            "",
            f"**Текст:**\n\n{p.caption}",
            "",
            f"**Визуал:** {p.visual_idea}",
            "",
            f"**CTA:** {p.cta}",
            "",
            f"**Хэштеги:** {' '.join('#' + h.lstrip('#') for h in p.hashtags)}",
            "",
            "---",
            "",
        ]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Генератор контент-плана Instagram POWERELIX")
    ap.add_argument("--posts", type=int, default=15, help="Сколько публикаций (по умолч. 15)")
    ap.add_argument("--start", default="2026-06-09", help="Дата старта YYYY-MM-DD")
    ap.add_argument("--cadence", default="5 публикаций в неделю (пн-пт)", help="Частота")
    ap.add_argument("--focus", default=None, help="Особый акцент плана (необязательно)")
    ap.add_argument("--model", default=None, help="Переопределить модель Claude")
    args = ap.parse_args()

    if args.model:
        config.CLAUDE_MODEL = args.model

    print(f"Генерирую план: {args.posts} постов, старт {args.start}, модель {config.CLAUDE_MODEL}…")
    plan = generate(
        n_posts=args.posts, start_date=args.start, cadence=args.cadence, focus=args.focus
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    base = OUTPUT_DIR / f"content_plan_{args.start}"
    base.with_suffix(".json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
    md = to_markdown(plan)
    base.with_suffix(".md").write_text(md, encoding="utf-8")

    print(f"\n✓ Готово: {len(plan.posts)} постов")
    print(f"  JSON: {base.with_suffix('.json')}")
    print(f"  MD:   {base.with_suffix('.md')}")
    print("\n" + "=" * 60)
    print(md[:1500])


if __name__ == "__main__":
    main()
