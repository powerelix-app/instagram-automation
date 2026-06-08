"""Тонкая обёртка над Instagram Graph API (Instagram Login).

Используется requests (а не Anthropic SDK) — это другой API, не Claude.
"""
from __future__ import annotations

from typing import Any

import requests

from . import config

PROFILE_FIELDS = "id,username,account_type,media_count,followers_count,follows_count,name,profile_picture_url,biography"


def get_profile() -> dict[str, Any]:
    """Профиль подключённого аккаунта POWERELIX."""
    r = requests.get(
        f"{config.IG_API_BASE}/me",
        params={"fields": PROFILE_FIELDS, "access_token": config.IG_ACCESS_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_media(limit: int = 25) -> list[dict[str, Any]]:
    """Последние публикации аккаунта."""
    r = requests.get(
        f"{config.IG_API_BASE}/me/media",
        params={
            "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
            "limit": limit,
            "access_token": config.IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data", [])


def refresh_token() -> dict[str, Any]:
    """Продлевает долгоживущий токен ещё на 60 дней.

    Работает для токена, которому уже >24ч и который ещё не истёк.
    Вернёт {'access_token', 'token_type', 'expires_in'} — новый токен надо
    положить в .env (IG_ACCESS_TOKEN) и обновить IG_TOKEN_EXPIRES_AT.
    """
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": config.IG_ACCESS_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
