"""Стадия 5 — Публикация поста в Instagram (Graph API). Идемпотентна.

SIMULATE_PUBLISH=1 → пишет в БД «как бы опубликовано» без вызова API (пока не
подтвердили реальный постинг). Картинка отдаётся IG по публичному URL /media/...
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict

from .. import config, instagram
from ..db.base import session_scope
from ..db.models import Post, PostAsset
from . import tokens

log = logging.getLogger(__name__)


def _full_caption(caption: str, hashtags) -> str:
    tags = " ".join(f"#{h.lstrip('#')}" for h in (hashtags or []))
    return (caption or "").strip() + ("\n\n" + tags if tags else "")


def publish(post_id: int) -> Dict:
    """Публикует одобренный пост. Возвращает {ok, ...}. Безопасна к повторному вызову."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"ok": False, "error": "пост не найден"}
        if post.status == "published" and post.ig_media_id:
            return {"ok": True, "already": True}
        if post.status not in ("approved", "scheduled"):
            return {"ok": False, "error": "пост не одобрен (нужен статус approved/scheduled)"}
        asset = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id)
            .order_by(PostAsset.ord).first()
        )
        if not asset or asset.kind != "image":
            return {"ok": False, "error": "нет картинки для публикации (сгенерируй визуал)"}
        caption = _full_caption(post.caption, post.hashtags)
        image_url = config.PUBLIC_BASE + asset.path
        post.status = "publishing"

    # ── Симуляция: ничего в IG не уходит ──
    if config.SIMULATE_PUBLISH:
        with session_scope() as s:
            post = s.get(Post, post_id)
            post.status = "published"
            post.ig_media_id = "SIMULATED"
            post.permalink = ""
            post.published_at = datetime.utcnow()
            post.error = ""
        log.info("publish post %s — SIMULATED (image_url=%s)", post_id, image_url)
        return {"ok": True, "simulated": True}

    # ── Боевая публикация ──
    token = tokens.current_token()
    uid = config.IG_USER_ID or "me"
    try:
        cid = instagram.create_image_container(image_url, caption, token, uid)
        for _ in range(20):  # ждём обработку контейнера (фото обычно мгновенно)
            st = instagram.container_status(cid, token)
            if st == "FINISHED":
                break
            if st == "ERROR":
                raise RuntimeError("IG вернул статус контейнера ERROR")
            time.sleep(3)
        res = instagram.publish_container(cid, token, uid)
        media_id = res.get("id", "")
        with session_scope() as s:
            post = s.get(Post, post_id)
            post.status = "published"
            post.ig_media_id = media_id
            post.permalink = instagram.media_permalink(media_id, token)
            post.published_at = datetime.utcnow()
            post.error = ""
        log.info("publish post %s — OK media_id=%s", post_id, media_id)
        return {"ok": True, "media_id": media_id}
    except Exception as e:
        with session_scope() as s:
            post = s.get(Post, post_id)
            if post:
                post.status = "failed"
                post.error = str(e)[:500]
        log.warning("publish post %s failed: %s", post_id, e)
        return {"ok": False, "error": str(e)}


def schedule(post_id: int, when: datetime) -> bool:
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post or post.status not in ("approved", "scheduled", "failed"):
            return False
        post.scheduled_at = when
        post.status = "scheduled"
        return True


def publish_due() -> int:
    """Публикует все запланированные посты, у которых наступило время. Для планировщика."""
    now = datetime.utcnow()
    with session_scope() as s:
        due = [
            p.id for p in s.query(Post)
            .filter(Post.status == "scheduled", Post.scheduled_at.isnot(None), Post.scheduled_at <= now)
            .all()
        ]
    for pid in due:
        publish(pid)
    return len(due)
