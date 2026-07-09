"""Скрапинг публичных данных Instagram через Apify (instagram-scraper)."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote

import requests

from . import config

ACTOR = "apify~instagram-scraper"
# Основной актор разведки: поиск вирусных Reels по теме — отдаёт play_count + mp4.
SEARCH_ACTOR = "data-slayer~instagram-search-reels"
BASE = "https://api.apify.com/v2"

log = logging.getLogger(__name__)


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


def _run_actor(
    actor: str, payload: dict[str, Any], max_charge_usd: float = 1.0, timeout: int = 300
) -> list[dict[str, Any]]:
    """Запуск актора с предохранителем по стоимости. Поднимает RuntimeError
    (а не SystemExit) — чтобы не ронять веб-процесс."""
    if not config.APIFY_TOKEN:
        raise RuntimeError("Не задан APIFY_TOKEN в .env")
    r = requests.post(
        f"{BASE}/acts/{actor}/run-sync-get-dataset-items",
        params={"token": config.APIFY_TOKEN, "maxTotalChargeUsd": max_charge_usd},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _first(item: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = item.get(k)
        if v not in (None, "", 0):
            return v
    return None


def _hashtags_from(text: str) -> list[str]:
    return re.findall(r"#([^\s#.,!?]+)", text or "")


def _normalize_reel(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Приводит выдачу разных акторов к единому виду (data-slayer raw-IG и
    apify/instagram-scraper). None — если это ошибка/не видео."""
    if item.get("error"):
        return None

    # caption: строка (instagram-scraper) или объект {text} (raw IG)
    cap = item.get("caption")
    caption = cap.get("text", "") if isinstance(cap, dict) else (cap or item.get("text") or "")

    # username: плоско или вложенно в user{}
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    username = _first(item, "ownerUsername", "username", "owner_username") or user.get("username") or ""

    # url: прямой или из shortcode/code
    url = _first(item, "url", "postUrl", "inputUrl") or ""
    code = _first(item, "code", "shortCode", "shortcode")
    if not url and code:
        url = f"https://www.instagram.com/reel/{code}/"

    video_url = _first(item, "video_url", "videoUrl") or ""
    if not video_url and isinstance(item.get("video_versions"), list) and item["video_versions"]:
        video_url = item["video_versions"][0].get("url", "")

    play = int(_first(item, "play_count", "playCount", "videoPlayCount", "videoViewCount",
                      "video_view_count", "ig_play_count", "views") or 0)

    # тип контента (видео/карусель/фото) — для UI. Карусели и фото тоже берём:
    # под русским хэштегом это нативный нишевый контент (источник идей).
    t = (item.get("type") or item.get("productType") or item.get("product_type") or "").lower()
    if video_url or item.get("media_type") == 2 or t in ("clips", "reel", "video"):
        media_type = "video"
    elif t in ("sidecar", "carousel", "carousel_container") or item.get("media_type") == 8:
        media_type = "carousel"
    else:
        media_type = "image"
    if not url and not caption:  # пропускаем только совсем пустые
        return None

    # превью
    thumb = _first(item, "displayUrl", "thumbnailUrl", "thumbnail_url", "imageUrl")
    if not thumb:
        iv = item.get("image_versions2") or {}
        cands = iv.get("candidates") if isinstance(iv, dict) else None
        if cands:
            thumb = cands[0].get("url", "")

    hashtags = item.get("hashtags") or _hashtags_from(caption)
    return {
        "url": url,
        "username": username,
        "play_count": play,
        "likes": int(_first(item, "like_count", "likesCount", "likes") or 0),
        "comments": int(_first(item, "comment_count", "commentsCount", "comments") or 0),
        "caption": caption,
        "hashtags": hashtags,
        "video_url": video_url,
        "thumbnail_url": thumb or "",
        "media_type": media_type,
        "music_info": "",
        "transcript": _first(item, "transcript", "captions") or "",
    }


def search_reels(topic: str, limit: int = 30, newer_than: str = "30 days") -> list[dict[str, Any]]:
    """Контент по теме. ПЕРВИЧНО — по хэштегу через instagram-scraper: язык термина
    совпадает с языком контента (русский запрос → русский #хэштег → русский контент,
    карусели/фото/видео). ФОЛБЭК — data-slayer (вирусные reels по ключу, чаще иностранные)."""
    tag = topic.lstrip("#").strip().replace(" ", "")
    tag_url = f"https://www.instagram.com/explore/tags/{quote(tag)}/"
    items: list[dict[str, Any]] = []
    try:
        items = _run_actor(ACTOR, {
            "directUrls": [tag_url], "resultsType": "posts",
            "resultsLimit": limit, "addParentData": False,
        })
    except (requests.RequestException, RuntimeError) as e:
        log.warning("apify hashtag scrape failed for %r: %s", topic, e)

    if not items or all(i.get("error") for i in items):
        try:
            items = _run_actor(SEARCH_ACTOR, {"search": topic, "maxItems": limit}, max_charge_usd=1.5)
            log.info("apify fallback (data-slayer) для %r: %d items", topic, len(items))
        except (requests.RequestException, RuntimeError) as e:
            log.warning("apify fallback failed for %r: %s", topic, e)

    reels = [r for r in (_normalize_reel(i) for i in items) if r]
    reels.sort(key=lambda r: r["play_count"], reverse=True)
    return reels


def account_reels(username: str, limit: int = 30) -> list[dict[str, Any]]:
    """Топ-Reels конкретного аккаунта (по убыванию просмотров). Источник гарантированно
    нишевый, если аккаунт нишевый — в отличие от мусорной выдачи по ключевому слову."""
    user = username.lstrip("@").strip("/").split("/")[-1]
    url = f"https://www.instagram.com/{user}/"
    try:
        posts = _run_actor(ACTOR, {
            "directUrls": [url], "resultsType": "posts",
            "resultsLimit": limit, "addParentData": False,
        })
    except (requests.RequestException, RuntimeError) as e:
        log.warning("apify account_reels failed for %r: %s", user, e)
        return []
    reels = [r for r in (_normalize_reel(i) for i in posts) if r]
    reels.sort(key=lambda r: r["play_count"], reverse=True)
    return reels


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


def reel_by_url(url: str) -> Optional[dict[str, Any]]:
    """Один ролик по прямой ссылке (reel/p). Нормализованный вид или None."""
    items = _run({
        "directUrls": [url],
        "resultsType": "posts",
        "resultsLimit": 1,
        "addParentData": False,
    })
    for item in items:
        norm = _normalize_reel(item)
        if norm:
            return norm
    return None


FETCHER_ACTOR = "dRB9VamNfzOU5fgPP"  # наш media-fetcher: качает URL на стороне Apify (обход РКН для VPS)


def fetch_via_actor(url: str, timeout: int = 240) -> Optional[bytes]:
    """Скачивает файл через актор media-fetcher (для хостов, недоступных с РФ-VPS)."""
    try:
        items = _run_actor(FETCHER_ACTOR, {"url": url}, max_charge_usd=0.05, timeout=timeout)
    except Exception as e:
        log.warning("media-fetcher run failed: %s", e)
        return None
    for it in items:
        if it.get("ok") and it.get("downloadUrl"):
            r = requests.get(it["downloadUrl"], params={"token": config.APIFY_TOKEN}, timeout=120)
            if r.ok and r.content:
                return r.content
    return None
