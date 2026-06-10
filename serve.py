"""Локальный запуск сервиса контент-завода: python serve.py (порт 8010)."""
from __future__ import annotations

import os

import uvicorn

from ig_automation.app import create_app

if __name__ == "__main__":
    port = int(os.getenv("CF_PORT", "8010"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
