"""Страницы сервиса. Фаза 1: Главная (обзор конвейера) + Статус (аккаунт/токен/конфиг)."""
from __future__ import annotations

from typing import Any, Dict

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..db.base import session_scope
from ..db.models import ContentPlan, Idea, Post, TrendReel
from ..products import product_names
from ..services import brand as brand_svc
from ..services import ideas as ideas_svc
from ..services import compliance, generator, planner, recon, tokens
from .auth import auth_disabled, require_user

log = logging.getLogger(__name__)

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
    return templates.TemplateResponse(request, "home.html", _ctx(request, counts=_counts()))


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
        request,
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


# ── Фаза 2: Разведка ──

@router.get("/recon", response_class=HTMLResponse)
def recon_page(request: Request, topic: str = "", show: str = "", msg: str = "", _: bool = Depends(require_user)):
    topics = recon.list_topics()
    include = show == "all"  # показать отсеянные AI-фильтром
    # "" → последняя тема; "__all__" → все темы вперемешку
    if topic == "__all__":
        sel, filt = "__all__", None
    else:
        sel = topic or (topics[0]["topic"] if topics else "")
        filt = sel or None
    return templates.TemplateResponse(
        request, "recon.html",
        _ctx(
            request,
            reels=recon.list_reels(filt, include_irrelevant=include),
            topics=topics, sel_topic=sel, show_all=include,
            irrelevant_count=recon.count_irrelevant(filt), msg=msg,
        ),
    )


@router.post("/recon/scrape")
def recon_scrape(request: Request, topic: str = Form(...), limit: int = Form(30), _: bool = Depends(require_user)):
    t = topic.strip()
    try:
        added = recon.scrape_topic(t, limit=min(limit, 100))
        msg = f"Собрано новых: {added}" if added else "Новых роликов не найдено (попробуй точнее: омега 3, витамин д, креатин…)"
    except Exception as e:  # сеть/Apify/токен — не роняем страницу
        log.warning("recon scrape failed: %s", e)
        msg = f"Ошибка сбора: {e}"
    # показываем именно собранную тему
    return RedirectResponse(f"/recon?topic={quote(t)}&msg={quote(msg)}", status_code=303)


@router.post("/recon/scrape-account")
def recon_scrape_account(request: Request, username: str = Form(...), limit: int = Form(30), _: bool = Depends(require_user)):
    handle = "@" + username.lstrip("@").strip().strip("/").split("/")[-1]
    try:
        added = recon.scrape_account(username, limit=min(limit, 50))
        msg = f"{handle}: собрано {added}" if added else f"{handle}: 0 (приватный аккаунт или нет Reels?)"
    except Exception as e:
        log.warning("recon scrape-account failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/recon?topic={quote(handle)}&msg={quote(msg)}", status_code=303)


@router.post("/recon/{reel_id}/analyze")
def recon_analyze(request: Request, reel_id: int, _: bool = Depends(require_user)):
    try:
        recon.analyze(reel_id)
        msg = "Хук разобран"
    except Exception as e:
        log.warning("recon analyze failed: %s", e)
        msg = f"Ошибка разбора: {e}"
    return RedirectResponse(f"/recon?msg={msg}", status_code=303)


@router.post("/recon/{reel_id}/to-idea")
def recon_to_idea(request: Request, reel_id: int, _: bool = Depends(require_user)):
    idea_id = recon.to_idea(reel_id)
    msg = "Идея добавлена в банк" if idea_id else "Сначала разбери ролик"
    return RedirectResponse(f"/recon?msg={msg}", status_code=303)


# ── Фаза 3: Контент-план ──

@router.get("/plan", response_class=HTMLResponse)
def plan_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "plan.html", _ctx(request, plans=planner.list_plans(), msg=msg)
    )


@router.post("/plan/generate")
def plan_generate(
    request: Request,
    n_posts: int = Form(10),
    start_date: str = Form(...),
    cadence: str = Form("5 публикаций в неделю (пн-пт)"),
    focus: str = Form(""),
    _: bool = Depends(require_user),
):
    try:
        plan_id = planner.generate_and_store(n_posts, start_date, cadence, focus or None)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)
    except Exception as e:
        log.warning("plan generate failed: %s", e)
        return RedirectResponse(f"/plan?msg=Ошибка генерации: {e}", status_code=303)


@router.get("/plan/{plan_id}", response_class=HTMLResponse)
def plan_detail(request: Request, plan_id: int, msg: str = "", _: bool = Depends(require_user)):
    plan = planner.get_plan(plan_id)
    if not plan:
        return RedirectResponse("/plan?msg=План не найден", status_code=303)
    return templates.TemplateResponse(request, "plan_detail.html", _ctx(request, plan=plan, msg=msg))


@router.post("/plan/{plan_id}/materialize")
def plan_materialize(request: Request, plan_id: int, _: bool = Depends(require_user)):
    added = planner.materialize_posts(plan_id)
    msg = f"Создано черновиков: {added}" if added else "Черновики уже созданы (или план пуст)"
    return RedirectResponse(f"/plan/{plan_id}?msg={msg}", status_code=303)


# ── Фаза 3: Банк идей ──

@router.get("/ideas", response_class=HTMLResponse)
def ideas_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "ideas.html", _ctx(request, ideas=ideas_svc.list_ideas(), msg=msg)
    )


@router.post("/ideas/add")
def ideas_add(
    request: Request,
    text: str = Form(...),
    hook: str = Form(""),
    rubric: str = Form(""),
    product: str = Form(""),
    _: bool = Depends(require_user),
):
    ideas_svc.add_idea(text.strip(), hook.strip(), rubric.strip(), product.strip())
    return RedirectResponse("/ideas?msg=Идея добавлена", status_code=303)


@router.post("/ideas/{idea_id}/to-post")
def ideas_to_post(request: Request, idea_id: int, _: bool = Depends(require_user)):
    post_id = ideas_svc.to_post(idea_id)
    if post_id:
        return RedirectResponse(f"/post/{post_id}", status_code=303)
    return RedirectResponse("/ideas?msg=Идея не найдена", status_code=303)


# ── Бренд-ассеты (банки/логотип/лицо модели) ──

@router.get("/brand", response_class=HTMLResponse)
def brand_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "brand.html",
        _ctx(request, assets=brand_svc.list_assets(), products=product_names(), msg=msg),
    )


@router.post("/brand/upload")
async def brand_upload(
    request: Request,
    kind: str = Form(...),
    product: str = Form(""),
    label: str = Form(""),
    file: UploadFile = File(...),
    _: bool = Depends(require_user),
):
    try:
        data = await file.read()
        brand_svc.add_asset(kind, data, file.filename or "asset.png", product=product, label=label)
        msg = "Ассет добавлен"
    except Exception as e:
        log.warning("brand upload failed: %s", e)
        msg = f"Ошибка загрузки: {e}"
    return RedirectResponse(f"/brand?msg={msg}", status_code=303)


@router.post("/brand/{asset_id}/delete")
def brand_delete(request: Request, asset_id: int, _: bool = Depends(require_user)):
    brand_svc.delete_asset(asset_id)
    return RedirectResponse("/brand?msg=Удалено", status_code=303)


# ── Фаза 4: Посты и генерация ──

@router.get("/posts", response_class=HTMLResponse)
def posts_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "posts.html", _ctx(request, posts=generator.list_posts(), msg=msg)
    )


@router.get("/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: int, msg: str = "", _: bool = Depends(require_user)):
    post = generator.get_post(post_id)
    if not post:
        return RedirectResponse("/posts?msg=Пост не найден", status_code=303)
    chk = generator.check_compliance(post_id)
    return templates.TemplateResponse(request, "post_detail.html", _ctx(request, post=post, chk=chk, msg=msg))


@router.post("/post/{post_id}/gen-visual")
def post_gen_visual(request: Request, post_id: int, _: bool = Depends(require_user)):
    try:
        generator.generate_post_assets(post_id)
        msg = "Визуал сгенерирован"
    except Exception as e:
        log.warning("gen visual failed: %s", e)
        msg = f"Ошибка генерации визуала: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={msg}", status_code=303)


@router.post("/post/{post_id}/gen-text")
def post_gen_text(request: Request, post_id: int, _: bool = Depends(require_user)):
    try:
        generator.generate_post_text(post_id)
        msg = "Текст сгенерирован"
    except Exception as e:
        log.warning("gen text failed: %s", e)
        msg = f"Ошибка генерации текста: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={msg}", status_code=303)


@router.post("/post/{post_id}/approve")
def post_approve(request: Request, post_id: int, override: str = Form(""), _: bool = Depends(require_user)):
    res = generator.approve_post(post_id, override=bool(override))
    if res.get("ok"):
        msg = "✅ Пост одобрен" + (" (с оверрайдом — на твою ответственность!)" if override else "")
    elif res.get("blocked"):
        msg = "🚫 Заблокировано БАД-линтом: " + compliance.summary(res)
    else:
        msg = res.get("error", "ошибка")
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/add-disclaimer")
def post_add_disclaimer(request: Request, post_id: int, _: bool = Depends(require_user)):
    generator.add_disclaimer(post_id)
    return RedirectResponse(f"/post/{post_id}?msg={quote('Дисклеймер БАД добавлен в подпись')}", status_code=303)


@router.post("/post/{post_id}/unapprove")
def post_unapprove(request: Request, post_id: int, _: bool = Depends(require_user)):
    generator.back_to_review(post_id)
    return RedirectResponse(f"/post/{post_id}?msg={quote('Возвращён в ревью')}", status_code=303)
