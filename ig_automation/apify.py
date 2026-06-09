"""Скрапинг публичных данных Instagram-аккаунтов через Apify (instagram-scraper)."""
from __future__ import annotations

from typing import Any

import requests

from . import config

ACTOR = "apify~instagram-scraper"
BASE = "https://api.apify.com/v2"


def _run(payload: dict[str, Any], timeout: int = 600) -> list[dict[str, Any]]:
    if not config.APIFY_TOKEN:
        raise SystemExit("Не задан APIFY_TOKEN в .env")
    r = requests.post(
        f"{BASE}/acts/{ACTOR}/run-sync-get-dataset-items",
        params={"token": config.APIFY_TOKEN},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def scrape_profile(username: str, posts_limit: int = 30) -> dict[str, Any]:
    """Возвращает профиль (bio, подписчики) + последние посты с метриками."""
    user = username.lstrip("@").strip("/").split("/")[-1]
    url = f"https://www.instagram.com/{user}/"
    details = _run({"directUrls": [url], "resultsType": "details"})
    posts = _run(
        {
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": posts_limit,
            "addParentData": False,
        }
    )
    return {"username": user, "details": details, "posts": posts}
