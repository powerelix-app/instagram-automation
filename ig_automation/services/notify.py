"""Telegram-уведомления через Cloudflare-релей (api.telegram.org заблокирован с РФ-VPS).
No-op, если CF_TG_TOKEN/CF_TG_CHAT не заданы — сервис работает и без Telegram."""
from __future__ import annotations

import logging

import requests

from .. import config

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(config.TG_TOKEN and config.TG_CHAT)


def send(text: str, html: bool = True) -> bool:
    """Отправляет сообщение в Telegram-чат. Возвращает True при успехе."""
    if not configured():
        log.info("telegram не настроен (CF_TG_TOKEN/CF_TG_CHAT) — пропуск")
        return False
    url = f"{config.TG_RELAY}/bot{config.TG_TOKEN}/sendMessage"
    try:
        body = {"chat_id": config.TG_CHAT, "text": text, "disable_web_page_preview": True}
        if html:
            body["parse_mode"] = "HTML"
        r = requests.post(url, json=body, timeout=15)
        if r.status_code != 200:
            log.warning("telegram send %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("telegram send error: %s", e)
        return False


def send_photo(photo_url: str, caption: str = "") -> bool:
    """Отправляет фото по ПУБЛИЧНОМУ URL с подписью (маленький JSON — релей тянет).
    Telegram сам скачивает картинку по URL. Подпись ≤1024 (лимит Bot API)."""
    if not configured():
        return False
    url = f"{config.TG_RELAY}/bot{config.TG_TOKEN}/sendPhoto"
    try:
        r = requests.post(url, json={
            "chat_id": config.TG_CHAT, "photo": photo_url, "caption": caption[:1024],
        }, timeout=25)
        if r.status_code != 200:
            log.warning("telegram sendPhoto %s: %s", r.status_code, r.text[:250])
            return False
        return True
    except Exception as e:
        log.warning("telegram sendPhoto error: %s", e)
        return False


def send_post(photo_url: str, caption: str = "") -> bool:
    """Готовый пост в TG для ручной выкладки: фото + подпись. Если подпись длиннее
    лимита к фото (1024) — шлём фото отдельно, затем полный текст сообщением."""
    caption = caption or ""
    if len(caption) <= 1024:
        return send_photo(photo_url, caption)
    ok = send_photo(photo_url, "📸 Готовый пост — полный текст ниже 👇")
    send(caption, html=False)
    return ok
