"""Конфигурация: читает .env из корня проекта."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

load_dotenv(ROOT / ".env")


# ── Instagram ──
IG_APP_ID = os.getenv("IG_APP_ID", "")
IG_APP_SECRET = os.getenv("IG_APP_SECRET", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_TOKEN_EXPIRES_AT = os.getenv("IG_TOKEN_EXPIRES_AT", "")
IG_API_BASE = "https://graph.instagram.com/v23.0"

# ── Apify ──
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# ── Claude ──
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
