#!/usr/bin/env python3
"""CLI: выгрузить публичные данные аккаунтов-конкурентов через Apify.

Примеры:
    python scrape_competitors.py konkurent1 konkurent2 konkurent3
    python scrape_competitors.py @brand --limit 50 --out competitors_ru
"""
from __future__ import annotations

import argparse
import json

from ig_automation import apify
from ig_automation.config import OUTPUT_DIR


def main() -> None:
    ap = argparse.ArgumentParser(description="Скрапинг конкурентов в Instagram (Apify)")
    ap.add_argument("usernames", nargs="+", help="@юзернеймы аккаунтов")
    ap.add_argument("--limit", type=int, default=30, help="Постов на аккаунт (по умолч. 30)")
    ap.add_argument("--out", default="competitors", help="Имя выходного файла без расширения")
    args = ap.parse_args()

    results = []
    for u in args.usernames:
        print(f"Тяну {u} …")
        try:
            data = apify.scrape_profile(u, args.limit)
            n = len(data.get("posts", []))
            print(f"  ✓ постов: {n}")
            results.append(data)
        except Exception as e:  # noqa: BLE001
            print(f"  ! ошибка по {u}: {e}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"{args.out}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Сохранено: {path} ({len(results)} аккаунтов)")


if __name__ == "__main__":
    main()
