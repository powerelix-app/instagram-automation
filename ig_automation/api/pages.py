"""Страницы сервиса. Фаза 1: Главная (обзор конвейера) + Статус (аккаунт/токен/конфиг)."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..db.base import session_scope
from ..db.models import ContentPlan, Idea, Post, TrendReel
from ..services import tokens
from .auth import auth_disabled, require_user

router = APIRouter()
templates = Jinja2Templates(directory="ig_automation/web/templates")


def _ctx(request: Request, **extra: Any) -> Dict[str, Any]:
    base = {
        "request": request,
        "auth_disabled": auth_disabled(),
        "simulate": config.SIMULATE_PUBLISH,
    }
    base.update(extra)
    return base


def _counts() -> Dict[str, int]:
    with session_scope() as s:
        return {
            "trends": s.query(TrendReel).count(),
            "ideas": s.query(Idea).count(),
            "plans": s.query(ContentPlan).count(),
            "posts": s.query(Post).count(),
        }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, _: bool = Depends(require_user)):
    return templates.TemplateResponse("home.html", _ctx(request, counts=_counts()))


@router.get("/status", response_class=HTMLResponse)
def status(request: Request, _: bool = Depends(require_user)):
    account = tokens.account_info()
    cfg_state = {
        "IG_ACCESS_TOKEN": bool(tokens.current_token()),
        "APIFY_TOKEN": bool(config.APIFY_TOKEN),
        "ANTHROPIC_API_KEY": bool(config.ANTHROPIC_API_KEY),
        "XAI_API_KEY": bool(config.XAI_API_KEY),
        "REPLICATE_API_TOKEN": bool(config.REPLICATE_API_TOKEN),
        "CF_ADMIN_PASSWORD": bool(config.ADMIN_PASSWORD),
        "CF_SESSION_SECRET": bool(config.SESSION_SECRET),
    }
    return templates.TemplateResponse(
        "status.html",
        _ctx(
            request,
            account=account,
            days_left=tokens.days_left(),
            cfg_state=cfg_state,
            claude_model=config.CLAUDE_MODEL,
            counts=_counts(),
            last_tick=tokens.get_state("scheduler_last_tick", "—"),
        ),
    )
