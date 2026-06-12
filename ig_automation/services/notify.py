"""Telegram-уведомления через Cloudflare-релей (api.telegram.org заблокирован с РФ-VPS).
No-op, если CF_TG_TOKEN/CF_TG_CHAT не заданы — сервис работает и без Telegram."""
from __future__ import annotations

import logging

import requests

from .. import config

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(config.TG_TOKEN and config.TG_CHAT)


def send(text: str) -> bool:
    """Отправляет HTML-сообщение в Telegram-чат. Возвращает True при успехе."""
    if not configured():
        log.info("telegram не настроен (CF_TG_TOKEN/CF_TG_CHAT) — пропуск")
        return False
    url = f"{config.TG_RELAY}/bot{config.TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": config.TG_CHAT, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }, timeout=15)
        if r.status_code != 200:
            log.warning("telegram send %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("telegram send error: %s", e)
        return False
