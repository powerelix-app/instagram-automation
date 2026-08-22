"""Вход в контент-завод.

С 2026-08-22 сервис закрыт общим входом Штаба: nginx спрашивает
/auth/check?service=content у приложения биддера и без сессии сюда не пускает.
Поэтому CF_ADMIN_PASSWORD пуст — второй пароль только мешал бы.

Пароль остаётся как запасной путь: если он задан, работает как раньше.
Пусто И запрос пришёл не через nginx (нет X-Forwarded-For) = локальная
разработка, вход открыт и в интерфейсе висит предупреждение.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config

router = APIRouter()
templates = Jinja2Templates(directory="ig_automation/web/templates")


def auth_disabled() -> bool:
    return not config.ADMIN_PASSWORD


def unguarded(request: Request) -> bool:
    """Сервис реально открыт: пароля нет И зашли не через nginx.

    Через nginx приходит X-Forwarded-For — значит проверка Штаба уже
    отработала, предупреждать не о чем.
    """
    return auth_disabled() and "x-forwarded-for" not in request.headers


def is_authed(request: Request) -> bool:
    if auth_disabled():
        return True
    return bool(request.session.get("authed"))


def require_user(request: Request) -> bool:
    """Зависимость FastAPI: пускает только залогиненных (или dev-режим)."""
    if not is_authed(request):
        raise HTTPException(status_code=401)
    return True


def _check_password(pw: str) -> bool:
    if auth_disabled():
        return True
    return hmac.compare_digest(pw or "", config.ADMIN_PASSWORD)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form("")):
    if _check_password(password):
        request.session["authed"] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Неверный пароль"}, status_code=401
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
