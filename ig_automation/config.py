"""Конфигурация: читает .env из корня проекта."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

load_dotenv(ROOT / ".env")
# OPENAI_API_KEY пользователь держит в соседнем проекте wb-design — подхватываем оттуда
# как фолбэк (не дублируем секрет в этот .env). Нужен для openai/gpt-image-1 на Replicate.
load_dotenv(ROOT.parent / "wb-design" / ".env", override=False)


# ── Instagram ──
IG_APP_ID = os.getenv("IG_APP_ID", "")
IG_APP_SECRET = os.getenv("IG_APP_SECRET", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_TOKEN_EXPIRES_AT = os.getenv("IG_TOKEN_EXPIRES_AT", "")
# Хост Instagram Graph API. С РФ-VPS graph.instagram.com заблокирован РКН —
# на проде CF_IG_HOST = URL Cloudflare-релея (как tg-relay для Telegram).
IG_HOST = os.getenv("CF_IG_HOST", "https://graph.instagram.com").rstrip("/")
IG_API_BASE = IG_HOST + "/v23.0"

# ── Apify ──
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# ── Claude ──
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# ── Replicate (генерация сцен, фаза D) ──
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-dev")  # дефолт-«test», дёшево

# ── OpenAI (gpt-image-1 через Replicate требует ключ юзера как input) ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# ── xAI / Grok (grok-2-image) — пока не задан, добавить XAI_API_KEY в .env ──
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
# Модель брендовой генерации (лицо+банка через image-edit с референсами).
# Дефолт — Replicate google/nano-banana (xAI-кредиты кончились 2026-06-11).
# Вернуть Grok: CF_BRANDED_MODEL=grok (нужны кредиты xAI).
BRANDED_MODEL = os.getenv("CF_BRANDED_MODEL", "google/nano-banana")

# ── Content Factory сервис (FastAPI) ──
DB_PATH = os.getenv("CF_DB_PATH", str(DATA_DIR / "content_factory.db"))
MEDIA_DIR = DATA_DIR / "media"
# Секрет сессионной cookie. В проде задать CF_SESSION_SECRET в .env (иначе при
# каждом рестарте все сессии слетают — фолбэк только для локалки).
SESSION_SECRET = os.getenv("CF_SESSION_SECRET", "")
# Пароль единственного админа. Пусто = dev-режим (вход открыт, баннер-предупреждение).
ADMIN_PASSWORD = os.getenv("CF_ADMIN_PASSWORD", "")
# Пока не пройден App Review Meta — публикация в IG идёт в режиме симуляции
# (пишем в БД «как бы опубликовано», без вызова Graph API). Выключить = "0".
SIMULATE_PUBLISH = os.getenv("CF_SIMULATE_PUBLISH", "1") not in ("0", "false", "False")
# Публичный базовый URL сервиса — Graph API требует публичную ссылку на картинку
# (image_url). На проде = поддомен контент-завода.
PUBLIC_BASE = os.getenv("CF_PUBLIC_BASE", "https://content.bandabogachey.online").rstrip("/")
