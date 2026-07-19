"""Кросс-пост опубликованного контента в сообщество ВКонтакте.

VK API открыт с РФ-VPS напрямую (без relay). Схема:
  photos.getWallUploadServer → POST файла → photos.saveWallPhoto →
  wall.post(owner_id=-group, from_group=1, attachments=photo{owner}_{id},...)
До 10 фото одним постом (наши карусели влезают целиком). Ссылки в тексте
VK делает кликабельными сам.

Идемпотентно: пост с заполненным vk_post_id второй раз не уходит.
No-op без CF_VK_TOKEN / CF_VK_GROUP_ID.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List

import requests

from .. import config
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

API = "https://api.vk.com/method"
V = "5.199"


def configured() -> bool:
    return bool(config.VK_USER_TOKEN and config.VK_GROUP_ID)


def _call(method: str, **params) -> dict:
    params.setdefault("v", V)
    params.setdefault("access_token", config.VK_USER_TOKEN)
    r = requests.post(f"{API}/{method}", data=params, timeout=60)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"VK {method}: {body['error'].get('error_msg')}")
    return body["response"]


def _upload_photo(path: Path, group_id: str, retries: int = 3) -> str:
    """Загрузка фото на стену сообщества → attachment-строка photo{owner}_{id}.
    VK при серии загрузок иногда отдаёт пустой photo — ретраим с паузой."""
    import time
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    last = ""
    for attempt in range(retries):
        srv = _call("photos.getWallUploadServer", group_id=group_id)
        with open(path, "rb") as f:
            up = requests.post(srv["upload_url"],
                               files={"photo": (path.name, f, mime)}, timeout=120).json()
        if up.get("photo") and up["photo"] != "[]":
            saved = _call("photos.saveWallPhoto", group_id=group_id,
                          photo=up["photo"], server=up["server"], hash=up["hash"])
            p = saved[0]
            return f"photo{p['owner_id']}_{p['id']}"
        last = str(up)[:150]
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"VK upload не принял файл {path.name}: {last}")


def _upload_video_wallpost(path: Path, group_id: str, name: str, description: str) -> str:
    """Загрузка видео в сообщество с авто-постом на стену (video.save wallpost=1).
    Возвращает attachment-строку video{owner}_{id}."""
    saved = _call("video.save", group_id=group_id, wallpost=1,
                  name=name, description=description)
    upload_url = saved["upload_url"]
    with open(path, "rb") as f:
        up = requests.post(upload_url, files={"video_file": (path.name, f, "video/mp4")},
                           timeout=600).json()
    if "error" in up or not (up.get("video_id") or saved.get("video_id")):
        raise RuntimeError(f"VK video upload: {str(up)[:200]}")
    vid = up.get("video_id") or saved.get("video_id")
    owner = up.get("owner_id") or saved.get("owner_id") or f"-{group_id}"
    return f"video{owner}_{vid}"


def _vk_caption(caption: str, product_id: str) -> str:
    """IG-подпись → VK: артикул текстом, хэштеги можно оставить (в VK работают),
    внизу — ссылки на товар/каталог/сайт (VK кликает их сам)."""
    text = re.sub(r"(Артикул[^\n#]*)#([\w\d]+)", r"\1\2", caption or "", flags=re.IGNORECASE)
    links = []
    if product_id:
        from .catalog import get_link
        lk = get_link(str(product_id)) or {}
        if (lk.get("wb_url") or "").startswith("https://"):
            links.append(f"🛒 Товар на Wildberries: {lk['wb_url']}")
    if config.VK_BRAND_URL:
        links.append(f"💊 Весь каталог: {config.VK_BRAND_URL}")
    if config.VK_SITE_URL:
        links.append(f"🌐 Сайт: {config.VK_SITE_URL}")
    if links:
        text = text.rstrip() + "\n\n" + "\n".join(links)
    return text


def crosspost(post_id: int, force: bool = False) -> Dict:
    """Постит контент поста на стену сообщества. Возвращает {ok, ...}."""
    if not force and not configured():
        return {"ok": False, "skipped": "vk crosspost не настроен"}

    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"ok": False, "error": "пост не найден"}
        if post.vk_post_id:
            return {"ok": True, "already": True, "vk_post_id": post.vk_post_id}
        caption = _vk_caption(post.caption, post.product_id)
        hook = (post.hook or post.product or "POWERELIX")[:100]
        video_asset = (s.query(PostAsset)
                       .filter(PostAsset.post_id == post_id, PostAsset.kind == "video")
                       .order_by(PostAsset.ord.desc()).first())
        video = config.DATA_DIR / video_asset.path.lstrip("/") if video_asset else None

    # path хранится URL-путём вида /media/...  → локальный файл в DATA_DIR
    from . import generator
    images: List[Path] = [
        config.DATA_DIR / a.path.lstrip("/") for a in generator.get_publish_assets(post_id)
    ]
    images = [p for p in images if p.exists()]
    gid = str(config.VK_GROUP_ID).lstrip("-")

    if not images and video and video.exists():  # Reels: видео на стену (video.save wallpost)
        try:
            res = _upload_video_wallpost(video, gid, name=hook, description=caption)
        except Exception as e:
            log.warning("vk video crosspost post %s failed: %s", post_id, e)
            return {"ok": False, "error": str(e)[:300]}
        vk_id = res
        with session_scope() as s:
            post = s.get(Post, post_id)
            if post:
                post.vk_post_id = vk_id
        log.info("vk video crosspost post %s → %s", post_id, vk_id)
        return {"ok": True, "vk_post_id": vk_id,
                "url": f"https://vk.com/{vk_id}"}

    if not images:
        return {"ok": False, "error": "у поста нет локальных картинок/видео для VK"}

    try:
        attachments = [_upload_photo(p, gid) for p in images[:10]]
        res = _call("wall.post", owner_id=f"-{gid}", from_group=1,
                    message=caption, attachments=",".join(attachments))
    except Exception as e:
        log.warning("vk crosspost post %s failed: %s", post_id, e)
        return {"ok": False, "error": str(e)[:300]}

    vk_id = str(res.get("post_id", ""))
    with session_scope() as s:
        post = s.get(Post, post_id)
        if post:
            post.vk_post_id = vk_id
    log.info("vk crosspost post %s → post_id=%s", post_id, vk_id)
    return {"ok": True, "vk_post_id": vk_id,
            "url": f"https://vk.com/wall-{gid}_{vk_id}"}
