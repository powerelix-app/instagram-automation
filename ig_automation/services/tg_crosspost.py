"""Кросс-пост опубликованного контента в Telegram-канал @powerelix.

Вызывается из publisher.publish сразу после успешной публикации в Instagram
(«одновременно с Инста»). РФ-VPS не может грузить большие файлы в
api.telegram.org (relay рвёт большие POST), поэтому шлём МАЛЕНЬКИЙ JSON
со ссылками на публичные медиа (CF_PUBLIC_BASE/media/...) на наш не-РФ
сервер (Aeza, бот @powerelix_brand_bot) — он скачивает байты сам и постит
в канал напрямую. Endpoint: POST {CF_CROSSPOST_ENDPOINT} c X-Crosspost-Secret.

Идемпотентно: пост с заполненным tg_message_id второй раз не уходит.
Выключатель: CF_CROSSPOST=1. No-op без endpoint/секрета.
"""
from __future__ import annotations

import logging
import re
from typing import Dict

import requests

from .. import config
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

_CAPTION_LIMIT = 1024  # лимит подписи к медиа в Bot API


def configured() -> bool:
    return bool(config.CROSSPOST_ENABLED and config.CROSSPOST_ENDPOINT and config.CROSSPOST_SECRET)


def _clean_caption(caption: str) -> str:
    """IG-подпись → TG: без хэштегов, в пределах лимита, по границе слова."""
    text = re.sub(r"#[\w\dё_]+", "", caption or "", flags=re.IGNORECASE | re.UNICODE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > _CAPTION_LIMIT:
        text = text[:_CAPTION_LIMIT - 1].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def crosspost(post_id: int, force: bool = False) -> Dict:
    """Постит контент поста в канал через Aeza-endpoint. force=True — слать даже
    при выключенном флаге (ручной тест). Возвращает {ok, ...}."""
    if not force and not configured():
        return {"ok": False, "skipped": "crosspost не настроен/выключен"}
    if not (config.CROSSPOST_ENDPOINT and config.CROSSPOST_SECRET):
        return {"ok": False, "error": "нет CF_CROSSPOST_ENDPOINT / CF_CROSSPOST_SECRET"}

    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"ok": False, "error": "пост не найден"}
        if post.tg_message_id:
            return {"ok": True, "already": True, "tg_message_id": post.tg_message_id}
        caption = _clean_caption(post.caption)
        images = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image")
            .order_by(PostAsset.ord).all()
        )
        video = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "video")
            .order_by(PostAsset.ord.desc()).first()
        )
        img_urls = [config.PUBLIC_BASE + a.path for a in images]
        vid_url = (config.PUBLIC_BASE + video.path) if video else None

    if vid_url:
        kind, urls = "video", [vid_url]
    elif len(img_urls) >= 2:
        kind, urls = "carousel", img_urls[:10]
    elif img_urls:
        kind, urls = "photo", img_urls
    else:
        return {"ok": False, "error": "у поста нет медиа для кросс-поста"}

    payload = {
        "channel": config.CROSSPOST_CHANNEL,
        "kind": kind,
        "media_urls": urls,
        "caption": caption,
        "button_text": config.CROSSPOST_BUTTON_TEXT,
        "button_url": config.CROSSPOST_BUTTON_URL,
    }
    try:
        r = requests.post(
            config.CROSSPOST_ENDPOINT,
            json=payload,
            headers={"X-Crosspost-Secret": config.CROSSPOST_SECRET},
            timeout=180,  # Aeza качает медиа + грузит в TG — может занять минуту+
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not body.get("ok"):
            raise RuntimeError(f"crosspost endpoint {r.status_code}: {str(body or r.text)[:200]}")
    except Exception as e:
        log.warning("tg crosspost post %s failed: %s", post_id, e)
        return {"ok": False, "error": str(e)[:300]}

    message_id = str(body.get("message_id", ""))
    with session_scope() as s:
        post = s.get(Post, post_id)
        if post:
            post.tg_message_id = message_id
    log.info("tg crosspost post %s → message_id=%s", post_id, message_id)
    return {"ok": True, "tg_message_id": message_id}
