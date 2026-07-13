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


def create_image_container(image_url: str, caption: str, token: str, ig_user_id: str) -> str:
    """Шаг 1 публикации фото: создать media-контейнер. Возвращает creation_id."""
    r = requests.post(
        f"{config.IG_API_BASE}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_carousel_item(image_url: str, token: str, ig_user_id: str) -> str:
    """Дочерний контейнер карусели (is_carousel_item)."""
    r = requests.post(f"{config.IG_API_BASE}/{ig_user_id}/media", data={
        "image_url": image_url, "is_carousel_item": "true", "access_token": token,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


def create_carousel_container(children: list, caption: str, token: str, ig_user_id: str) -> str:
    """Карусель-контейнер из готовых дочерних (2-10 шт)."""
    r = requests.post(f"{config.IG_API_BASE}/{ig_user_id}/media", data={
        "media_type": "CAROUSEL", "children": ",".join(children),
        "caption": caption, "access_token": token,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


def container_status(creation_id: str, token: str) -> str:
    """Статус контейнера: IN_PROGRESS | FINISHED | ERROR | PUBLISHED."""
    r = requests.get(
        f"{config.IG_API_BASE}/{creation_id}",
        params={"fields": "status_code", "access_token": token},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("status_code", "")


def publish_container(creation_id: str, token: str, ig_user_id: str) -> dict[str, Any]:
    """Шаг 2: опубликовать готовый контейнер. Возвращает {'id': media_id}."""
    r = requests.post(
        f"{config.IG_API_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def media_permalink(media_id: str, token: str) -> str:
    try:
        r = requests.get(
            f"{config.IG_API_BASE}/{media_id}",
            params={"fields": "permalink", "access_token": token}, timeout=30,
        )
        r.raise_for_status()
        return r.json().get("permalink", "")
    except requests.RequestException:
        return ""


def get_media_insights(media_id: str, token: str) -> dict[str, int]:
    """Метрики опубликованного медиа (reach/saved/likes/comments/shares).
    Набор метрик зависит от типа поста — берём безопасный и парсим что вернулось."""
    out: dict[str, int] = {}
    try:
        r = requests.get(
            f"{config.IG_API_BASE}/{media_id}/insights",
            params={"metric": "reach,saved,likes,comments,shares", "access_token": token},
            timeout=30,
        )
        if r.status_code >= 400:
            return out
        for item in r.json().get("data", []):
            vals = item.get("values") or []
            v = vals[0].get("value") if vals else (item.get("total_value") or {}).get("value")
            out[item.get("name")] = int(v or 0)
    except (requests.RequestException, ValueError):
        pass
    return out


def refresh_token() -> dict[str, Any]:
    """Продлевает долгоживущий токен ещё на 60 дней.

    Работает для токена, которому уже >24ч и который ещё не истёк.
    Вернёт {'access_token', 'token_type', 'expires_in'} — новый токен надо
    положить в .env (IG_ACCESS_TOKEN) и обновить IG_TOKEN_EXPIRES_AT.
    """
    r = requests.get(
        f"{config.IG_HOST}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": config.IG_ACCESS_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
