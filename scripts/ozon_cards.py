#!/usr/bin/env python3
"""Создание карточек товаров на Ozon через Seller API.

    .venv/bin/python scripts/ozon_cards.py --dry Chlorophyll_01   # показать payload, не отправлять
    .venv/bin/python scripts/ozon_cards.py Chlorophyll_01         # создать одну карточку
    .venv/bin/python scripts/ozon_cards.py --all                  # все из ozon_products.json
    .venv/bin/python scripts/ozon_cards.py --status <task_id>     # статус импорта

Данные берутся из data/ozon_products.json (габариты/ШК/цены/СГР выгружены с WB),
названия и SEO-атрибуты — из data/ozon_cards.json.
Ключи — из .env: OZON_CLIENT_ID / OZON_API_KEY.
"""
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api-seller.ozon.ru"


def env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"нет {name} в .env")


HEADERS = {"Client-Id": env("OZON_CLIENT_ID"), "Api-Key": env("OZON_API_KEY"),
           "Content-Type": "application/json"}

# ── справочники Ozon (разведаны 27.07.2026) ──
CATEGORY_ID = 200000896          # Аптека / БАДы и витамины
BRAND_ID = 972847595             # POWERELIX (уже в справочнике Ozon)
ATTR = {"name_model": 9048, "tnved": 22232, "brand": 85, "composition": 8050,
        "type": 8229, "marking": 23536, "direction": 22009, "country": 4389,
        "form": 8634, "main_component": 9008, "sgr": 21955, "volume": 8163,
        "count_pack": 8513, "age_min": 8632, "contra": 8728, "flavor": 7981,
        "shelf_life": 8205, "indications": 9388}
TNVED_ID = 972939269      # 2106909809 — Пищевые продукты, прочие (значение из справочника Ozon)
TNVED = "2106909809 - Пищевые продукты, в другом месте не поименованные или не включенные: прочие: прочие: прочие: прочие"
CONTRA_ID = 57147         # «БАД. НЕ ЯВЛЯЕТСЯ ЛЕКАРСТВЕННЫМ СРЕДСТВОМ» — единственное значение справочника


def load(name: str) -> dict:
    return json.loads((ROOT / "data" / name).read_text())


def build_item(p: dict, seo: dict) -> dict:
    """Собирает один товар для /v3/product/import."""
    d = p["dims_cm"]
    attrs = [
        {"id": ATTR["name_model"], "values": [{"value": seo["model_name"]}]},
        {"id": ATTR["tnved"], "values": [{"dictionary_value_id": TNVED_ID}]},
        {"id": ATTR["brand"], "values": [{"dictionary_value_id": BRAND_ID, "value": "POWERELIX"}]},
        {"id": ATTR["composition"], "values": [{"value": seo["composition"]}]},
        {"id": ATTR["type"], "values": [{"dictionary_value_id": p["ozon_type_id"],
                                         "value": p["ozon_type"]}]},
        {"id": ATTR["marking"], "values": [{"value": "true"}]},   # БАД маркируется ЧЗ
    ]
    # SEO-слот: направления БАД (мультизначный — главный фильтруемый атрибут)
    if seo.get("directions"):
        attrs.append({"id": ATTR["direction"],
                      "values": [{"dictionary_value_id": i, "value": v}
                                 for i, v in seo["directions"]]})
    if p.get("sgr"):
        attrs.append({"id": ATTR["sgr"], "values": [{"value": p["sgr"]}]})
    for key, val in (("main_component", seo.get("main_component")),
                     ("indications", seo.get("indications"))):
        if val:
            attrs.append({"id": ATTR[key], "values": [{"value": val}]})
    # противопоказания — строго из справочника Ozon (дисклеймер БАД обязателен структурно)
    attrs.append({"id": ATTR["contra"],
                  "values": [{"dictionary_value_id": CONTRA_ID,
                              "value": "БАД. НЕ ЯВЛЯЕТСЯ ЛЕКАРСТВЕННЫМ СРЕДСТВОМ"}]})
    if seo.get("volume_ml"):
        attrs.append({"id": ATTR["volume"], "values": [{"value": str(seo["volume_ml"])}]})
    if seo.get("count_in_pack"):
        attrs.append({"id": ATTR["count_pack"], "values": [{"value": str(seo["count_in_pack"])}]})
    if seo.get("shelf_life_days"):
        attrs.append({"id": ATTR["shelf_life"], "values": [{"value": str(seo["shelf_life_days"])}]})

    return {
        "offer_id": p["vendorCode"],
        "name": seo["title"],
        "description_category_id": CATEGORY_ID,
        "type_id": p["ozon_type_id"],
        "barcode": p["barcode"],
        "price": str(p["price"]),
        "old_price": str(p["price_before"]),
        "vat": "0",                                    # БАД — НДС 0 у большинства; проверить!
        "weight": int(p["weight_kg"] * 1000), "weight_unit": "g",
        "depth": int(d[0] * 10), "width": int(d[1] * 10), "height": int(d[2] * 10),
        "dimension_unit": "mm",
        "images": seo.get("images", []),
        "attributes": attrs,
    }


def import_items(items: list) -> dict:
    r = requests.post(f"{API}/v3/product/import", headers=HEADERS,
                      json={"items": items}, timeout=60)
    return {"http": r.status_code, "body": r.json() if r.text else {}}


def status(task_id: str) -> dict:
    r = requests.post(f"{API}/v1/product/import/info", headers=HEADERS,
                      json={"task_id": int(task_id)}, timeout=60)
    return r.json()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    if args[0] == "--status":
        print(json.dumps(status(args[1]), ensure_ascii=False, indent=1)); return

    dry = "--dry" in args
    args = [a for a in args if not a.startswith("--")] or []
    prods = {p["vendorCode"]: p for p in load("ozon_products.json")["products"]}
    seos = load("ozon_cards.json")

    keys = list(seos.keys()) if ("--all" in sys.argv) else args
    items = []
    for k in keys:
        if k not in prods:
            print(f"⚠️  {k}: нет в ozon_products.json"); continue
        if k not in seos:
            print(f"⚠️  {k}: нет в ozon_cards.json (название/атрибуты)"); continue
        items.append(build_item(prods[k], seos[k]))

    if not items:
        print("нечего отправлять"); sys.exit(1)
    if dry:
        print(json.dumps(items, ensure_ascii=False, indent=1)); return

    res = import_items(items)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    tid = (res.get("body") or {}).get("result", {}).get("task_id")
    if tid:
        print(f"\n→ проверить: .venv/bin/python scripts/ozon_cards.py --status {tid}")


if __name__ == "__main__":
    main()
