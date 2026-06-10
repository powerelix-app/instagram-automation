"""FastAPI-приложение «Контент-завод» (на базе instagram-automation).

Стек зеркалит wb-promotion: FastAPI + SQLite + APScheduler + Jinja2/HTMX.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config
from . import scheduler as sched_mod
from .api import auth, pages
from .db import base as db_base

log = logging.getLogger(__name__)

STATIC_DIR = "ig_automation/web/static"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def create_app(enable_scheduler: bool = True) -> FastAPI:
    _configure_logging()
    db_base.init()

    if not config.SESSION_SECRET:
        log.warning("CF_SESSION_SECRET не задан — сессии слетят при рестарте (ок для локалки)")
    if not config.ADMIN_PASSWORD:
        log.warning("CF_ADMIN_PASSWORD не задан — вход открыт (dev-режим)")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        sched = sched_mod.start_scheduler() if enable_scheduler else None
        try:
            yield
        finally:
            if sched:
                sched.shutdown(wait=False)

    app = FastAPI(title="POWERELIX Контент-завод", lifespan=lifespan)

    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SESSION_SECRET or os.urandom(32).hex(),
        session_cookie="cf_session",
        max_age=60 * 60 * 24 * 14,
        same_site="lax",
        https_only=False,
    )
    app.include_router(auth.router)
    app.include_router(pages.router)

    os.makedirs(STATIC_DIR, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(HTTPException)
    async def on_http_exc(request: Request, exc: HTTPException):
        if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app
