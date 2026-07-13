"""Кросс-пост опубликованного контента в сообщество ВКонтакте.

VK API открыт с РФ-VPS напрямую (без relay). Схема:
  photos.getWallUploadServer → POST файла → photos.saveWallUploadPhoto →
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


def _upload_photo(path: Path, group_id: str) -> str:
    """Загрузка фото на стену сообщества → attachment-строка photo{owner}_{id}."""
    srv = _call("photos.getWallUploadServer", group_id=group_id)
    with open(path, "rb") as f:
        up = requests.post(srv["upload_url"], files={"photo": (path.name, f)}, timeout=120).json()
    if not up.get("photo") or up["photo"] == "[]":
        raise RuntimeError(f"VK upload не принял файл {path.name}")
    saved = _call("photos.saveWallUploadPhoto", group_id=group_id,
                  photo=up["photo"], server=up["server"], hash=up["hash"])
    p = saved[0]
    return f"photo{p['owner_id']}_{p['id']}"


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
        # path хранится URL-путём вида /media/...  → локальный файл в DATA_DIR
        images: List[Path] = [
            config.DATA_DIR / a.path.lstrip("/")
            for a in s.query(PostAsset)
            .filter(PostAsset.post_id == post_id, PostAsset.kind == "image")
            .order_by(PostAsset.ord).all()
        ]

    images = [p for p in images if p.exists()]
    if not images:
        return {"ok": False, "error": "у поста нет локальных картинок для VK"}

    gid = str(config.VK_GROUP_ID).lstrip("-")
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
