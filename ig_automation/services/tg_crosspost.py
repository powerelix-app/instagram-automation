"""Кросс-пост опубликованного контента в Telegram-канал @powerelix.

Вызывается из publisher.publish сразу после успешной публикации в Instagram
(«одновременно с Инста»). Работает через Cloudflare-релей tg-relay
(api.telegram.org заблокирован с РФ-VPS), файлы шлём multipart-ом из data/media.

Токен — бот @powerelix_brand_bot (он админ канала). Идемпотентно: пост,
у которого tg_message_id уже заполнен, второй раз не уходит.

Форматы:
  video-asset (Reels)   → sendVideo (caption + inline-кнопка)
  1 image               → sendPhoto (caption + inline-кнопка)
  2+ images (карусель)  → sendMediaGroup (caption на первом; кнопок Bot API
                          для media group не поддерживает — шлём без кнопки)

Выключатель: CF_CROSSPOST=1. No-op без токена/канала — сервис живёт и без TG.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

import requests

from .. import config
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

_CAPTION_LIMIT = 1024  # лимит подписи к медиа в Bot API
_VIDEO_LIMIT_MB = 49   # обычный upload ограничен 50 МБ — оставляем запас


def configured() -> bool:
    return bool(config.CROSSPOST_ENABLED and config.CROSSPOST_BOT_TOKEN and config.CROSSPOST_CHANNEL)


def _clean_caption(caption: str) -> str:
    """IG-подпись → TG: без хэштегов, в пределах лимита, по границе слова."""
    text = re.sub(r"#[\w\dё_]+", "", caption or "", flags=re.IGNORECASE | re.UNICODE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > _CAPTION_LIMIT:
        text = text[:_CAPTION_LIMIT - 1].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def _button_markup() -> Optional[str]:
    if not config.CROSSPOST_BUTTON_URL:
        return None
    return json.dumps({"inline_keyboard": [[
        {"text": config.CROSSPOST_BUTTON_TEXT, "url": config.CROSSPOST_BUTTON_URL}
    ]]})


def _api(method: str, data: Dict, files: Optional[Dict] = None) -> Dict:
    url = f"{config.TG_RELAY}/bot{config.CROSSPOST_BOT_TOKEN}/{method}"
    r = requests.post(url, data=data, files=files or {}, timeout=120)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or not body.get("ok"):
        raise RuntimeError(f"TG {method} {r.status_code}: {str(body or r.text)[:300]}")
    return body["result"]


def _asset_file(asset: PostAsset):
    """PostAsset.path (/media/...) → открытый файловый объект."""
    rel = asset.path.split("/media/", 1)[-1]
    p = config.MEDIA_DIR / rel
    if not p.exists():
        raise FileNotFoundError(f"нет файла {p}")
    return p


def crosspost(post_id: int, force: bool = False) -> Dict:
    """Постит контент поста в канал. force=True — слать даже при выключенном флаге
    (для ручного теста). Возвращает {ok, ...}."""
    if not force and not configured():
        return {"ok": False, "skipped": "crosspost не настроен/выключен"}
    if not (config.CROSSPOST_BOT_TOKEN and config.CROSSPOST_CHANNEL):
        return {"ok": False, "error": "нет CF_CROSSPOST_BOT_TOKEN / CF_CROSSPOST_CHANNEL"}

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
        img_paths = [_asset_file(a) for a in images]
        vid_path = _asset_file(video) if video else None

    chat = config.CROSSPOST_CHANNEL
    markup = _button_markup()

    try:
        if vid_path:  # Reels
            if vid_path.stat().st_size > _VIDEO_LIMIT_MB * 1024 * 1024:
                return {"ok": False, "error": f"видео больше {_VIDEO_LIMIT_MB} МБ — пропуск"}
            data = {"chat_id": chat, "caption": caption, "supports_streaming": "true"}
            if markup:
                data["reply_markup"] = markup
            with open(vid_path, "rb") as f:
                msg = _api("sendVideo", data, files={"video": (vid_path.name, f, "video/mp4")})
        elif len(img_paths) >= 2:  # карусель
            media = []
            files = {}
            for i, p in enumerate(img_paths[:10]):
                key = f"photo{i}"
                item = {"type": "photo", "media": f"attach://{key}"}
                if i == 0 and caption:
                    item["caption"] = caption
                media.append(item)
                files[key] = (p.name, open(p, "rb"), "image/jpeg")
            try:
                res = _api("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)}, files=files)
            finally:
                for _, (_, f, _) in files.items():
                    f.close()
            msg = res[0] if isinstance(res, list) and res else {}
        elif len(img_paths) == 1:  # одиночное фото
            data = {"chat_id": chat, "caption": caption}
            if markup:
                data["reply_markup"] = markup
            with open(img_paths[0], "rb") as f:
                msg = _api("sendPhoto", data, files={"photo": (img_paths[0].name, f, "image/jpeg")})
        else:
            return {"ok": False, "error": "у поста нет медиа для кросс-поста"}
    except Exception as e:
        log.warning("tg crosspost post %s failed: %s", post_id, e)
        return {"ok": False, "error": str(e)[:300]}

    message_id = str(msg.get("message_id", ""))
    with session_scope() as s:
        post = s.get(Post, post_id)
        if post:
            post.tg_message_id = message_id
    log.info("tg crosspost post %s → message_id=%s", post_id, message_id)
    return {"ok": True, "tg_message_id": message_id}
