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


def _tg_video_variant(public_url: str) -> str:
    """Вертикальные 9:16 Reels Telegram в ленте кропит до ~4:5 (середина кадра).
    Готовим TG-версию 1080x1080 (квадрат показывается целиком на всех
    клиентах): ролик целиком по высоте + размытые бока.
    Возвращает публичный URL варианта ('' — если не вышло, шлём оригинал)."""
    import subprocess
    if not public_url.startswith(config.PUBLIC_BASE):
        return ""
    rel = public_url[len(config.PUBLIC_BASE):].lstrip("/")   # media/...
    src = config.DATA_DIR / rel
    if not src.exists():
        return ""
    try:
        import json as _json
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(src)],
            capture_output=True, timeout=30)
        st = _json.loads(probe.stdout or b"{}").get("streams") or [{}]
        w, h = st[0].get("width", 0), st[0].get("height", 0)
        if not h or w / h > 0.95:  # уже ~квадрат и шире — не трогаем
            return ""
        dst = src.with_name("tg_" + src.name)
        if not dst.exists():
            vf = ("split[a][b];[a]scale=1080:1080:force_original_aspect_ratio=increase,"
                  "crop=1080:1080,boxblur=24[bg];[b]scale=-2:1080[fg];"
                  "[bg][fg]overlay=(W-w)/2:0")
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-filter_complex", vf,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                 "-c:a", "copy", "-movflags", "+faststart", str(dst)],
                capture_output=True, timeout=600)
            if r.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
                log.warning("tg video variant ffmpeg fail: %s", r.stderr[-200:])
                return ""
        return config.PUBLIC_BASE + "/" + str(dst.relative_to(config.DATA_DIR))
    except Exception as e:
        log.warning("tg video variant fail: %s", e)
        return ""


def configured() -> bool:
    return bool(config.CROSSPOST_ENABLED and config.CROSSPOST_ENDPOINT and config.CROSSPOST_SECRET)


def _clean_caption(caption: str) -> str:
    """IG-подпись → TG: без хэштегов, в пределах лимита, по границе слова."""
    # артикул в IG оформлен хэштегом (#WW621739) — в TG оставляем текстом
    text = re.sub(r"(Артикул[^\n#]*)#([\w\d]+)", r"\1\2", caption or "", flags=re.IGNORECASE)
    text = re.sub(r"#[\w\dё_]+", "", text, flags=re.IGNORECASE | re.UNICODE)
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
        product_id = post.product_id
        video = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "video")
            .order_by(PostAsset.ord.desc()).first()
        )
        vid_url = (config.PUBLIC_BASE + video.path) if video else None

    from . import generator
    img_urls = [config.PUBLIC_BASE + a.path for a in generator.get_publish_assets(post_id)]

    vid_dims = None
    if vid_url:
        variant = _tg_video_variant(vid_url)
        if variant:
            vid_url, vid_dims = variant, (1080, 1080)
        kind, urls = "video", [vid_url]
    elif len(img_urls) >= 2:
        kind, urls = "carousel", img_urls[:10]
    elif img_urls:
        kind, urls = "photo", img_urls
    else:
        return {"ok": False, "error": "у поста нет медиа для кросс-поста"}

    # Ссылки — HTML-анкорами в подписи (у альбомов в TG кнопок не бывает,
    # а всё должно быть одним постом)
    import html as _html
    links = []
    if product_id:
        from .catalog import get_link
        lk = get_link(str(product_id)) or {}
        if (lk.get("wb_url") or "").startswith("https://"):
            links.append(f'🛒 <a href="{lk["wb_url"]}">Ссылка на Wildberries</a>')
    if config.CROSSPOST_BUTTON_TEXT and config.CROSSPOST_BUTTON_URL:
        links.append(f'<a href="{config.CROSSPOST_BUTTON_URL}">'
                     f'{_html.escape(config.CROSSPOST_BUTTON_TEXT)}</a>')
    links_block = ("\n\n" + "\n".join(links)) if links else ""
    # видимый текст ссылок тоже входит в лимит 1024 — режем базовый текст с запасом
    visible_links_len = len(re.sub(r"<[^>]+>", "", links_block))
    max_base = _CAPTION_LIMIT - visible_links_len
    if len(caption) > max_base:
        caption = caption[:max_base - 1].rsplit(" ", 1)[0].rstrip() + "…"
    caption = _html.escape(caption) + links_block

    payload = {
        "channel": config.CROSSPOST_CHANNEL,
        "kind": kind,
        "media_urls": urls,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if vid_dims:
        payload["width"], payload["height"] = vid_dims
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
