"""IG-токен и состояние аккаунта.

Источник токена: app_state (если продлевали) → фолбэк на .env. Так refresh
не требует правки .env на проде — новый токен оседает в БД.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from .. import config
from ..db.base import session_scope
from ..db.models import AppState

log = logging.getLogger(__name__)

# ── app_state helpers ──

def get_state(key: str, default: str = "") -> str:
    with session_scope() as s:
        row = s.get(AppState, key)
        return row.value if row else default


def set_state(key: str, value: str) -> None:
    with session_scope() as s:
        row = s.get(AppState, key)
        if row:
            row.value = value
        else:
            s.add(AppState(key=key, value=value))


# ── токен ──

def current_token() -> str:
    return get_state("ig_access_token", "") or config.IG_ACCESS_TOKEN


def token_expires_raw() -> str:
    return get_state("ig_token_expires_at", "") or config.IG_TOKEN_EXPIRES_AT


def days_left() -> Optional[int]:
    """Сколько дней до истечения токена, или None если неизвестно."""
    raw = (token_expires_raw() or "").strip()
    if not raw:
        return None
    expires: Optional[datetime] = None
    # эпоха (секунды)?
    try:
        expires = datetime.fromtimestamp(int(float(raw)), tz=timezone.utc)
    except (ValueError, OverflowError):
        # ISO-строка?
        try:
            expires = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return (expires - datetime.now(timezone.utc)).days


def account_info() -> Dict[str, Any]:
    """Профиль подключённого аккаунта + ключевая проверка: тип (нужен BUSINESS)."""
    token = current_token()
    if not token:
        return {"ok": False, "error": "IG_ACCESS_TOKEN не задан (.env)"}
    try:
        r = requests.get(
            f"{config.IG_API_BASE}/me",
            params={
                "fields": "id,username,account_type,media_count,followers_count,name",
                "access_token": token,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        acc_type = (data.get("account_type") or "").upper()
        # Через Instagram Login API публикация доступна бизнес-аккаунту.
        data["can_publish"] = acc_type in ("BUSINESS", "MEDIA_CREATOR")
        return {"ok": True, **data}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def ensure_fresh(threshold_days: int = 7) -> Dict[str, Any]:
    """Если до истечения токена < threshold_days — продлить на 60 дней и сохранить
    в app_state. Безопасна к вызову из планировщика (всё в try)."""
    dl = days_left()
    if dl is None:
        return {"refreshed": False, "reason": "expiry unknown"}
    if dl >= threshold_days:
        return {"refreshed": False, "days_left": dl}
    try:
        r = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": current_token()},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        new_token = body.get("access_token", "")
        expires_in = int(body.get("expires_in", 0))
        if new_token:
            set_state("ig_access_token", new_token)
            new_expiry = int(datetime.now(timezone.utc).timestamp()) + expires_in
            set_state("ig_token_expires_at", str(new_expiry))
        log.info("ig token refreshed, expires_in=%s", expires_in)
        return {"refreshed": True, "expires_in": expires_in}
    except requests.RequestException as e:
        log.warning("ig token refresh failed: %s", e)
        return {"refreshed": False, "error": str(e)}
