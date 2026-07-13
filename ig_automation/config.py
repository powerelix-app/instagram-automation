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
FAL_KEY = os.getenv("FAL_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ── Claude ──
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# ── Replicate (генерация сцен, фаза D) ──
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "black-forest-labs/flux-dev")  # дефолт-«test», дёшево

# ── OpenAI (gpt-image-1 через Replicate требует ключ юзера как input) ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Whisper: на РФ-VPS ставить ProxyAPI (https://api.proxyapi.ru/openai/v1/audio/transcriptions)
OPENAI_AUDIO_URL = os.getenv("OPENAI_AUDIO_URL", "https://api.openai.com/v1/audio/transcriptions")

# ── Google Veo (видео-генерация через Gemini API) ──
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# veo-3.1-generate-preview (качество) / -fast- (быстрее, дешевле) / -lite- (самый дешёвый, без 4K)
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-fast-generate-preview")
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

# ── Telegram (ежедневные напоминания по фоллоу-апам/задачам) ──
# api.telegram.org заблокирован с РФ-VPS → шлём через Cloudflare-релей (тот же, что
# wb-promotion). Чтобы включить: задать CF_TG_TOKEN (токен бота) и CF_TG_CHAT (chat_id).
TG_TOKEN = os.getenv("CF_TG_TOKEN", "")
TG_CHAT = os.getenv("CF_TG_CHAT", "")
TG_RELAY = os.getenv("CF_TG_RELAY", "https://tg-relay.makc-rogozhnikov.workers.dev").rstrip("/")

# ── Кросс-пост в Telegram-канал @powerelix (бот @powerelix_brand_bot — админ канала) ──
CROSSPOST_ENABLED = os.getenv("CF_CROSSPOST", "0") == "1"
CROSSPOST_ENDPOINT = os.getenv("CF_CROSSPOST_ENDPOINT", "https://bot.bandabogachey.online/powerelix-api/crosspost")
CROSSPOST_SECRET = os.getenv("CF_CROSSPOST_SECRET", "")
CROSSPOST_CHANNEL = os.getenv("CF_CROSSPOST_CHANNEL", "@powerelix")
CROSSPOST_BUTTON_TEXT = os.getenv("CF_CROSSPOST_BUTTON_TEXT", "💊 Каталог и приложение")
CROSSPOST_BUTTON_URL = os.getenv("CF_CROSSPOST_BUTTON_URL", "https://t.me/powerelix_brand_bot")

# ── Кросс-пост во ВКонтакте (сообщество POWERELIX, ключ доступа сообщества) ──
VK_TOKEN = os.getenv("CF_VK_TOKEN", "")
VK_GROUP_ID = os.getenv("CF_VK_GROUP_ID", "")  # без минуса, напр. 233462900
VK_BRAND_URL = os.getenv("CF_VK_BRAND_URL", "https://www.wildberries.ru/brands/312000349-powerelix")
VK_SITE_URL = os.getenv("CF_VK_SITE_URL", "https://powerelix.online")

# ── TTS для озвучки Reels (Replicate, русский — api.openai.com заблокирован с РФ-VPS) ──
TTS_MODEL = os.getenv("CF_TTS_MODEL", "minimax/speech-02-turbo")
TTS_VOICE = os.getenv("CF_TTS_VOICE", "Wise_Woman")
# Lip-sync для Reels (губы модели под озвучку). Пусто = выключить (озвучка просто закадром).
LIPSYNC_MODEL = os.getenv("CF_LIPSYNC_MODEL", "bytedance/latentsync")
