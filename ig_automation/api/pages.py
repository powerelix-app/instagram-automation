"""Страницы сервиса. Фаза 1: Главная (обзор конвейера) + Статус (аккаунт/токен/конфиг)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import logging
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..db.base import session_scope
from ..db.models import Blogger, ContentPlan, Deal, Idea, Post, TrendReel
from ..products import product_names, products_list
from ..services import brand as brand_svc
from ..services import catalog as catalog_svc
from ..services import ideas as ideas_svc
from ..services import bloggers as bloggers_svc
from ..services import compliance, generator, insights, planner, publisher, recon, reels, tokens
from ..services import comparison as comparison_svc
from ..services import seamless as seamless_svc
from ..services import sources as sources_svc
from .auth import auth_disabled, require_user

log = logging.getLogger(__name__)
_MSK = ZoneInfo("Europe/Moscow")

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


def _today() -> Dict[str, Any]:
    """Дашборд «Что сегодня»: что требует действия — публикация, проверка, блогеры."""
    today = datetime.now(_MSK).date().isoformat()

    def slim(p: Post) -> dict:
        return {"id": p.id, "hook": (p.hook or p.product or "пост")[:64],
                "format": p.format, "scheduled_at": p.scheduled_at or ""}

    with session_scope() as s:
        def by(status):
            return [slim(p) for p in s.query(Post).filter(Post.status == status)
                    .order_by(Post.id.desc()).all()]
        review, draft, approved, failed = by("review"), by("draft"), by("approved"), by("failed")
        scheduled = [slim(p) for p in s.query(Post).filter(Post.status == "scheduled")
                     .order_by(Post.scheduled_at).all()]
    due = [p for p in scheduled if p["scheduled_at"][:10] <= today]
    followups = bloggers_svc.needs_followup()
    return {
        "due": due, "review": review, "draft": draft, "approved": approved,
        "failed": failed, "followups": followups,
        "nothing": not (due or review or draft or approved or failed or followups),
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, _: bool = Depends(require_user)):
    return templates.TemplateResponse(request, "home.html", _ctx(request, counts=_counts(), today=_today()))


@router.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", _: bool = Depends(require_user)):
    """Сквозной поиск по CRM: блогеры, посты, сделки (Python-side — корректный регистр кириллицы)."""
    q = (q or "").strip()
    res: Dict[str, list] = {"bloggers": [], "posts": [], "deals": []}
    if len(q) >= 2:
        ql = q.lower()

        def hit(*vals):
            return any(ql in (v or "").lower() for v in vals)

        with session_scope() as s:
            for b in s.query(Blogger).order_by(Blogger.id.desc()).all():
                if hit(b.name, b.handle, b.niche, b.notes, b.city, b.contact):
                    res["bloggers"].append({"id": b.id, "name": b.name, "handle": b.handle,
                                            "niche": b.niche, "status": b.status})
            for p in s.query(Post).order_by(Post.id.desc()).all():
                if hit(p.hook, p.caption, p.product, p.rubric, p.visual_idea):
                    res["posts"].append({"id": p.id, "hook": (p.hook or p.product or "пост")[:70],
                                         "status": p.status, "format": p.format})
            blmap = {b.id: b.name for b in s.query(Blogger).all()}
            for d in s.query(Deal).order_by(Deal.id.desc()).all():
                if hit(d.notes, d.promo_code, d.product, d.post_url):
                    res["deals"].append({"id": d.id, "blogger_id": d.blogger_id,
                                         "blogger": blmap.get(d.blogger_id, "?"),
                                         "stage": d.stage, "promo": d.promo_code})
    total = sum(len(v) for v in res.values())
    return templates.TemplateResponse(request, "search.html", _ctx(request, q=q, res=res, total=total))


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
def recon_page(request: Request, topic: str = "", show: str = "", lang: str = "", sort: str = "",
              msg: str = "", _: bool = Depends(require_user)):
    topics = recon.list_topics()
    include = show == "all"  # показать отсеянные AI-фильтром
    sel_sort = sort if sort in ("views", "new", "old") else "views"
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
            reels=recon.list_reels(filt, include_irrelevant=include, lang=lang, sort=sel_sort),
            topics=topics, sel_topic=sel, show_all=include, sel_lang=lang, sel_sort=sel_sort,
            irrelevant_count=recon.count_irrelevant(filt), msg=msg,
            products=catalog_svc.all_with_links(),
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


@router.post("/recon/{reel_id}/delete")
def recon_delete(request: Request, reel_id: int, topic: str = Form(""), _: bool = Depends(require_user)):
    ok = recon.delete_reel(reel_id)
    msg = "Ролик удалён" if ok else "Ролик не найден"
    return RedirectResponse(f"/recon?topic={quote(topic)}&msg={quote(msg)}", status_code=303)


# ── Источники идей (разведка инфографик по аккаунтам) ──
@router.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(request, "sources.html",
                                      _ctx(request, accounts=sources_svc.list_accounts(), msg=msg))


@router.post("/sources/add")
def sources_add(request: Request, handle: str = Form(...), kind: str = Form("donor"),
                note: str = Form(""), _: bool = Depends(require_user)):
    aid = sources_svc.add_account(handle, kind, note)
    msg = "Источник добавлен" if aid else "Не разобрал ник — проверь ссылку/@"
    return RedirectResponse(f"/sources?msg={quote(msg)}", status_code=303)


@router.post("/sources/{account_id}/scrape")
def sources_scrape(request: Request, account_id: int, _: bool = Depends(require_user)):
    try:
        added = sources_svc.scrape(account_id)
        msg = f"Собрано постов: {added}" if added else "0 (приватный аккаунт, нет Reels или лимит Apify?)"
    except Exception as e:
        log.warning("sources scrape failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/sources?msg={quote(msg)}", status_code=303)


@router.post("/sources/{account_id}/delete")
def sources_delete(request: Request, account_id: int, _: bool = Depends(require_user)):
    sources_svc.delete(account_id)
    return RedirectResponse(f"/sources?msg={quote('Источник удалён')}", status_code=303)


@router.post("/sources/{account_id}/ideas")
def sources_ideas(request: Request, account_id: int, _: bool = Depends(require_user)):
    try:
        n = sources_svc.generate_ideas(account_id, n=6)
        msg = f"Сгенерировано идей: {n} — смотри в Банке идей"
    except Exception as e:
        log.warning("sources ideas failed: %s", e)
        msg = f"Ошибка (нужен баланс ProxyAPI?): {e}"
    return RedirectResponse(f"/ideas?msg={quote(msg)}", status_code=303)


@router.post("/sources/ideas-scratch")
def sources_ideas_scratch(request: Request, _: bool = Depends(require_user)):
    try:
        n = sources_svc.generate_ideas(None, n=6)
        msg = f"Сгенерировано идей с нуля: {n} — смотри в Банке идей"
    except Exception as e:
        log.warning("sources ideas-scratch failed: %s", e)
        msg = f"Ошибка (нужен баланс ProxyAPI?): {e}"
    return RedirectResponse(f"/ideas?msg={quote(msg)}", status_code=303)


@router.post("/recon/add-url")
def recon_add_url(request: Request, url: str = Form(...), _: bool = Depends(require_user)):
    """Разбор по прямой ссылке: скачиваем ролик + сразу глубокий разбор (кадры+vision)."""
    u = url.strip()
    topic = "по ссылке"
    try:
        reel_id = recon.add_reel_by_url(u)
        if not reel_id:
            msg = "Не удалось получить контент (ссылка верна? пост публичный?)"
        else:
            topic = recon.reel_topic(reel_id) or topic
            recon.deep_analyze(reel_id)
            msg = "Контент скачан и разобран (глубокий разбор)"
    except Exception as e:
        log.warning("recon add-url failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/recon?topic={quote(topic)}&msg={quote(msg)}", status_code=303)


@router.post("/recon/{reel_id}/deep-analyze")
def recon_deep_analyze(request: Request, reel_id: int, _: bool = Depends(require_user)):
    """Глубокий разбор существующего ролика: mp4 + кадры + транскрипт + vision."""
    try:
        rid = recon.deep_analyze(reel_id)
        msg = "Глубокий разбор готов" if rid else "Видео недоступно (протухла ссылка CDN)"
    except Exception as e:
        log.warning("recon deep failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/recon?msg={quote(msg)}", status_code=303)


@router.post("/recon/upload")
async def recon_upload(request: Request, video: UploadFile = File(...), _: bool = Depends(require_user)):
    """Загрузка своего видеофайла -> глубокий разбор."""
    try:
        data = await video.read()
        if len(data) > 200 * 1024 * 1024:
            raise ValueError("файл больше 200MB")
        reel_id = recon.add_uploaded_video(data, video.filename or "")
        recon.deep_analyze(reel_id)
        msg = "Видео загружено и разобрано"
    except Exception as e:
        log.warning("recon upload failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/recon?topic={quote('загрузка')}&msg={quote(msg)}", status_code=303)


@router.post("/recon/analysis/{analysis_id}/make-similar")
def recon_make_similar(request: Request, analysis_id: int, product_id: str = Form(...), _: bool = Depends(require_user)):
    """Storyboard нашего ролика по механике разобранного референса."""
    try:
        sb_id = recon.make_similar(analysis_id, product_id)
        if sb_id:
            return RedirectResponse(f"/storyboard/{sb_id}", status_code=303)
        msg = "Не удалось (нет разбора или продукта)"
    except Exception as e:
        log.warning("make-similar failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/recon?msg={quote(msg)}", status_code=303)


@router.get("/storyboards", response_class=HTMLResponse)
def storyboards_page(request: Request, _: bool = Depends(require_user)):
    from ..db.base import session_scope
    from ..db.models import Storyboard
    with session_scope() as s:
        rows = s.query(Storyboard).order_by(Storyboard.id.desc()).limit(50).all()
        items = [{"id": r.id, "title": r.title, "product": r.product_name,
                  "status": r.status, "created": r.created_at} for r in rows]
    return templates.TemplateResponse(request, "storyboards.html", _ctx(request, items=items))


@router.get("/storyboard/{sb_id}", response_class=HTMLResponse)
def storyboard_page(request: Request, sb_id: int, _: bool = Depends(require_user)):
    from ..db.base import session_scope
    from ..db.models import Storyboard
    with session_scope() as s:
        r = s.get(Storyboard, sb_id)
        if not r:
            raise HTTPException(404)
        sb = {"id": r.id, "title": r.title, "concept": r.concept, "product": r.product_name,
              "scenes": r.scenes or [], "vo_full": r.vo_full, "music_hint": r.music_hint,
              "status": r.status, "reel_id": r.trend_reel_id,
              "model_key": getattr(r, "model_key", "") or "",
              "video_engine": getattr(r, "video_engine", "") or "",
              "img_ratio": getattr(r, "img_ratio", "") or "",
              "include_model": bool(getattr(r, "include_model", True)),
              "include_product": bool(getattr(r, "include_product", True)),
              "gen_status": r.gen_status or "", "gen_error": r.gen_error or "",
              "outputs": r.output_paths or [], "video": r.output_video or "",
              "is_carousel": bool(r.scenes) and all(float(x.get("duration_s") or 0) == 0 for x in (r.scenes or []))}
    return templates.TemplateResponse(request, "storyboard.html", _ctx(request, sb=sb, models=brand_svc.list_models(),
             video_engines=[{"key": k, "name": v[1]} for k, v in __import__("ig_automation.services.producer", fromlist=["x"]).VIDEO_ENGINES.items()]))


@router.post("/storyboard/{sb_id}/delete")
def storyboard_delete(request: Request, sb_id: int, _: bool = Depends(require_user)):
    """Удаляет раскадровку вместе со сгенерированными слайдами/видео на диске."""
    import shutil
    from ..db.models import Storyboard
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            s.delete(sb)
    shutil.rmtree(config.DATA_DIR / "media" / "produced" / str(sb_id), ignore_errors=True)
    return RedirectResponse("/storyboards?msg=" + quote("Раскадровка удалена"), status_code=303)


@router.post("/storyboard/{sb_id}/engine")
def storyboard_set_engine(request: Request, sb_id: int, video_engine: str = Form(""), _: bool = Depends(require_user)):
    from ..db.models import Storyboard
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            sb.video_engine = video_engine
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote("Движок анимации выбран"), status_code=303)


@router.post("/storyboard/{sb_id}/ratio")
def storyboard_set_ratio(request: Request, sb_id: int, img_ratio: str = Form(""), _: bool = Depends(require_user)):
    from ..db.models import Storyboard
    if img_ratio not in ("4:5", "9:16", "1:1", ""):
        raise HTTPException(400)
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            sb.img_ratio = img_ratio
    names = {"4:5": "лента (4:5)", "9:16": "Reels/сторис (9:16)", "1:1": "квадрат (1:1)"}
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote(f"Формат: {names.get(img_ratio, 'лента (4:5)')}"),
                            status_code=303)


@router.post("/storyboard/{sb_id}/scene")
def storyboard_set_scene(request: Request, sb_id: int,
                         include_model: bool = Form(False),
                         include_product: bool = Form(False),
                         _: bool = Depends(require_user)):
    from ..db.models import Storyboard
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            sb.include_model = include_model
            sb.include_product = include_product
    what = (("👤 человек" if include_model else "без человека") + " + "
            + ("🫙 банка" if include_product else "без банки"))
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote(f"✅ Фильтр «что в кадре» применён — {what}"),
                            status_code=303)


@router.post("/storyboard/{sb_id}/stage/{stage}")
def storyboard_stage(request: Request, sb_id: int, stage: str, _: bool = Depends(require_user)):
    from ..services import producer
    if stage not in ("stills", "clips", "assemble"):
        raise HTTPException(400)
    ok = producer.run_stage(sb_id, stage)
    names = {"stills": "Генерирую кадры", "clips": "Анимирую кадры", "assemble": "Собираю ролик"}
    msg = names[stage] + "…" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote(msg), status_code=303)


@router.post("/storyboard/{sb_id}/still/{i}/regen")
def storyboard_still_regen(request: Request, sb_id: int, i: int, _: bool = Depends(require_user)):
    from ..services import producer
    ok = producer.run_stage(sb_id, "stills", only=i)
    msg = f"Перегенерирую кадр {i + 1}…" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote(msg), status_code=303)


@router.post("/storyboard/{sb_id}/clip/{i}/regen")
def storyboard_clip_regen(request: Request, sb_id: int, i: int, _: bool = Depends(require_user)):
    from ..services import producer
    ok = producer.run_stage(sb_id, "clips", only=i)
    msg = f"Переанимирую сцену {i + 1}…" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote(msg), status_code=303)


@router.post("/storyboard/{sb_id}/model")
def storyboard_set_model(request: Request, sb_id: int, model_key: str = Form(""), _: bool = Depends(require_user)):
    from ..db.models import Storyboard
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            sb.model_key = model_key
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote("Модель выбрана"), status_code=303)


@router.post("/post/{post_id}/model")
def post_set_model(request: Request, post_id: int, model_key: str = Form(""), _: bool = Depends(require_user)):
    with session_scope() as s:
        post = s.get(Post, post_id)
        if post:
            post.model_key = model_key
    return RedirectResponse(f"/post/{post_id}?msg=" + quote("Модель выбрана"), status_code=303)


@router.post("/storyboard/{sb_id}/scenes")
async def storyboard_scenes_save(request: Request, sb_id: int, _: bool = Depends(require_user)):
    """Правка промптов сцен перед генерацией."""
    from ..db.models import Storyboard
    form = await request.form()
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if sb:
            scenes = list(sb.scenes or [])
            for i in range(len(scenes)):
                v = form.get(f"scene_{i}")
                if v is not None and v.strip():
                    scenes[i] = {**scenes[i], "scene": v.strip()}
            sb.scenes = scenes
    return RedirectResponse(f"/storyboard/{sb_id}?msg=" + quote("Сцены сохранены"), status_code=303)


@router.post("/storyboard/{sb_id}/approve")
def storyboard_approve(request: Request, sb_id: int, _: bool = Depends(require_user)):
    from ..db.base import session_scope
    from ..db.models import Storyboard
    with session_scope() as s:
        r = s.get(Storyboard, sb_id)
        if r:
            r.status = "approved"
    return RedirectResponse(f"/storyboard/{sb_id}", status_code=303)


@router.post("/storyboard/{sb_id}/generate")
def storyboard_generate(request: Request, sb_id: int, _: bool = Depends(require_user)):
    """Производство контента из одобренного storyboard (фон)."""
    from ..services import producer
    started = producer.produce(sb_id)
    return RedirectResponse(f"/storyboard/{sb_id}", status_code=303)


@router.post("/storyboard/{sb_id}/to-post")
async def storyboard_to_post(request: Request, sb_id: int, _: bool = Depends(require_user)):
    """Storyboard со сгенерированным контентом -> пост (подпись+артикул+выбранные ассеты)."""
    try:
        form = await request.form()
        sel = [int(x) for x in form.getlist("slides")] or None
        pid = recon.storyboard_to_post(sb_id, selected=sel)
        if pid:
            return RedirectResponse(f"/post/{pid}", status_code=303)
        msg = "Сначала сгенерируй контент (слайды/ролик)"
    except Exception as e:
        log.warning("to-post failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/storyboard/{sb_id}?msg={quote(msg)}", status_code=303)


# ── Фаза 3: Контент-план ──

@router.get("/plan", response_class=HTMLResponse)
def plan_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "plan.html", _ctx(request, plans=planner.list_plans(), msg=msg)
    )


@router.post("/plan/generate")
def plan_generate(
    request: Request,
    start_date: str = Form(...),
    posts_per_day: int = Form(3),
    days: int = Form(7),
    rhythm: str = Form("2:1"),
    slots: str = Form("10:00, 14:00, 19:00"),
    focus: str = Form(""),
    _: bool = Depends(require_user),
):
    try:
        posts_per_day = max(1, min(posts_per_day, 6))
        days = max(1, min(days, 14))
        n_posts = posts_per_day * days
        cadence = f"{posts_per_day} публикации в день, {days} дней подряд"
        plan_id = planner.generate_and_store(n_posts, start_date, cadence, focus or None,
                                             rhythm=rhythm, slots=slots)
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
def plan_materialize(request: Request, plan_id: int, date: str = Form(""),
                     _: bool = Depends(require_user)):
    added = planner.materialize_posts(plan_id, only_date=date or None)
    if added:
        msg = f"Создано черновиков: {added}" + (f" (день {date})" if date else "")
    else:
        msg = "Черновики уже созданы (или день/план пуст)"
    return RedirectResponse(f"/plan/{plan_id}?msg={msg}", status_code=303)


@router.post("/plan/{plan_id}/delete")
def plan_delete(request: Request, plan_id: int, _: bool = Depends(require_user)):
    res = planner.delete_plan(plan_id)
    if res.get("ok"):
        msg = f"План #{plan_id} удалён (черновиков снято: {res['removed']}, сохранено опубликованных: {res['kept']})"
    else:
        msg = res.get("error", "ошибка")
    return RedirectResponse(f"/plan?msg={quote(msg)}", status_code=303)


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


@router.post("/post/{post_id}/delete")
def post_delete(request: Request, post_id: int, _: bool = Depends(require_user)):
    generator.delete_post(post_id)
    return RedirectResponse("/posts?msg=" + quote("Пост удалён"), status_code=303)


@router.get("/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, post_id: int, msg: str = "", _: bool = Depends(require_user)):
    post = generator.get_post(post_id)
    if not post:
        return RedirectResponse("/posts?msg=Пост не найден", status_code=303)
    chk = generator.check_compliance(post_id)
    return templates.TemplateResponse(
        request, "post_detail.html",
        _ctx(request, post=post, chk=chk, catalog_products=products_list(),
             bloggers=bloggers_svc.list_bloggers(), models=brand_svc.list_models(), msg=msg),
    )


@router.post("/post/{post_id}/gen-visual")
def post_gen_visual(request: Request, post_id: int, _: bool = Depends(require_user)):
    from ..services import producer
    ok = producer.enqueue_post(post_id, "post_visual")
    msg = "Визуал в очереди — обнови страницу через минуту" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/overlay")
def post_overlay(request: Request, post_id: int, source_asset_id: str = Form(""),
                 headline: str = Form(""), subtitle: str = Form(""), tag: str = Form(""),
                 disclaimer: str = Form(""), _: bool = Depends(require_user)):
    try:
        src = int(source_asset_id) if source_asset_id.strip() else None
        hl, sub, tg, dis = headline.strip(), subtitle.strip(), tag.strip(), disclaimer.strip()
        if not hl and not sub:  # ничего не ввели → Claude придумает сам
            aid = generator.apply_text_overlay(post_id, source_asset_id=src)
        else:
            aid = generator.apply_text_overlay(post_id, source_asset_id=src, headline=hl,
                                               subtitle=sub, tag=tg or None, disclaimer=dis)
        msg = "Обложка наложена на картинку" if aid else "Не удалось наложить текст"
    except Exception as e:
        log.warning("overlay failed: %s", e)
        msg = f"Ошибка наложения текста: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/set-product")
def post_set_product(request: Request, post_id: int, product_id: str = Form(""), _: bool = Depends(require_user)):
    generator.set_post_product(post_id, product_id)
    return RedirectResponse(f"/post/{post_id}?msg={quote('Товар привязан — перегенерируй текст')}", status_code=303)


@router.post("/post/{post_id}/set-format")
def post_set_format(request: Request, post_id: int, fmt: str = Form(""), _: bool = Depends(require_user)):
    """Формат поста задаёт соотношение сторон генерации (см. generator._FORMAT_RATIO)."""
    if fmt not in ("photo", "carousel", "reels"):
        raise HTTPException(400)
    with session_scope() as s:
        p = s.get(Post, post_id)
        if p:
            p.format = fmt
    names = {"photo": "одиночный пост (4:5)", "carousel": "карусель (4:5)", "reels": "Reels — вертикаль (9:16)"}
    return RedirectResponse(f"/post/{post_id}?msg=" + quote(f"Формат: {names[fmt]} — перегенерируй визуал"),
                            status_code=303)


@router.post("/post/{post_id}/set-blogger")
def post_set_blogger(request: Request, post_id: int, blogger_id: str = Form(""), _: bool = Depends(require_user)):
    generator.set_post_blogger(post_id, blogger_id)
    return RedirectResponse(f"/post/{post_id}?msg={quote('Привязка к блогеру обновлена')}", status_code=303)


@router.get("/catalog", response_class=HTMLResponse)
def catalog_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(request, "catalog.html", _ctx(request, items=catalog_svc.all_with_links(), msg=msg))


@router.post("/catalog/save")
def catalog_save(request: Request, product_id: str = Form(...), nmid: str = Form(""),
                 wb_url: str = Form(""), note: str = Form(""), _: bool = Depends(require_user)):
    catalog_svc.set_link(product_id, nmid, wb_url, note)
    return RedirectResponse("/catalog?msg=Сохранено", status_code=303)


@router.post("/post/{post_id}/ref-upload")
async def post_ref_upload(request: Request, post_id: int, file: UploadFile = File(...), _: bool = Depends(require_user)):
    try:
        data = await file.read()
        generator.add_post_ref(post_id, data, file.filename or "ref.png")
        msg = "Референс добавлен — будет учтён при генерации"
    except Exception as e:
        log.warning("ref upload failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/ref-url")
def post_ref_url(request: Request, post_id: int, url: str = Form(...), _: bool = Depends(require_user)):
    """Как в разведке: скачивает настоящий пин/пост по ссылке и добавляет как референс поста."""
    try:
        generator.add_post_ref_by_url(post_id, url.strip())
        msg = "Референс скачан — генерация пересоздаст его точь-в-точь под наш продукт/модель"
    except Exception as e:
        log.warning("ref-url failed: %s", e)
        msg = f"Ошибка: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/asset/{aid}/delete")
def post_asset_delete(request: Request, post_id: int, aid: int, _: bool = Depends(require_user)):
    generator.delete_post_asset(aid)
    return RedirectResponse(f"/post/{post_id}", status_code=303)


@router.post("/post/{post_id}/asset/{aid}/select")
def post_asset_select(request: Request, post_id: int, aid: int, _: bool = Depends(require_user)):
    """Для photo/reels с несколькими вариантами картинки — какую именно публиковать."""
    ok = generator.select_post_image(post_id, aid)
    msg = "Выбрана для публикации" if ok else "Не удалось выбрать"
    return RedirectResponse(f"/post/{post_id}?msg=" + quote(msg), status_code=303)


@router.post("/post/{post_id}/gen-carousel")
def post_gen_carousel(request: Request, post_id: int, slides: int = Form(4), _: bool = Depends(require_user)):
    from ..services import producer
    ok = producer.enqueue_post(post_id, "post_carousel", slides=slides)
    msg = f"Карусель ({slides} слайдов) в очереди — обнови страницу через 1-2 минуты" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/gen-reels-script")
def post_gen_reels_script(request: Request, post_id: int, _: bool = Depends(require_user)):
    try:
        generator.generate_reels_script(post_id)
        msg = "🎬 Сценарий Reels готов"
    except Exception as e:
        log.warning("reels script failed: %s", e)
        msg = f"Ошибка сценария: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/gen-reels-video")
def post_gen_reels_video(request: Request, post_id: int, _: bool = Depends(require_user)):
    from ..services import producer
    ok = producer.enqueue_post(post_id, "post_reels_video")
    msg = "🎬 Видео в очереди — обнови страницу через 1-2 минуты" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/gen-reels-full")
def post_gen_reels_full(request: Request, post_id: int, _: bool = Depends(require_user)):
    try:
        reels.start_full_reels(post_id)
        msg = "🎬 Многосценный Reels собирается в фоне (~3-6 мин) — обновите страницу позже"
    except Exception as e:
        log.warning("reels-full start failed: %s", e)
        msg = f"Ошибка запуска сборки: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


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


@router.post("/post/{post_id}/publish")
def post_publish(request: Request, post_id: int,
                 platforms: List[str] = Form(default=[]), _: bool = Depends(require_user)):
    res = publisher.publish(post_id, platforms=platforms or None)
    if res.get("ok"):
        if res.get("simulated"):
            msg = "🧪 Опубликовано (симуляция — в IG не ушло)"
        elif res.get("already"):
            msg = "Уже было опубликовано"
        else:
            names = {"ig": "Instagram", "tg": "Telegram", "vk": "ВКонтакте"}
            where = ", ".join(names.get(x, x) for x in res.get("platforms", [])) or "Instagram"
            msg = f"✅ Опубликовано: {where}"
    else:
        msg = "Ошибка публикации: " + res.get("error", "")
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


@router.get("/post/{post_id}/manual-pack")
def post_manual_pack(request: Request, post_id: int, _: bool = Depends(require_user)):
    """ZIP для ручной публикации: слайды по порядку + готовые подписи (IG / TG / VK)."""
    import io
    import zipfile
    from ..services.publisher import _full_caption
    from ..services.tg_crosspost import _clean_caption
    from ..services.vk_crosspost import _vk_caption
    from fastapi.responses import Response

    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return RedirectResponse("/posts?msg=" + quote("пост не найден"), status_code=303)
        caption, hashtags, product_id = post.caption or "", post.hashtags, post.product_id

    paths = [config.DATA_DIR / a.path.lstrip("/") for a in generator.get_publish_assets(post_id)]
    paths = [p for p in paths if p.exists()]
    if not paths:
        return RedirectResponse(f"/post/{post_id}?msg=" + quote("нет картинок — сгенерируй визуал"),
                                status_code=303)
    ig_text = _full_caption(caption, hashtags)
    tg_text = _clean_caption(caption)
    vk_text = _vk_caption(caption, product_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, pth in enumerate(paths, 1):
            z.writestr(f"{i:02d}{pth.suffix or '.png'}", pth.read_bytes())
        z.writestr("подпись_instagram.txt", ig_text)
        z.writestr("подпись_telegram.txt", tg_text)
        z.writestr("подпись_vk.txt", vk_text)
        z.writestr("README.txt",
                   "Слайды выкладывать по порядку номеров.\n"
                   "Подписи готовы под каждую площадку: IG — с хэштегами, "
                   "TG — без хэштегов, VK — со ссылками на товар/каталог/сайт.")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="post_{post_id}_manual.zip"'})


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, _: bool = Depends(require_user)):
    return templates.TemplateResponse(request, "analytics.html", _ctx(request, data=insights.overview()))


# ── Движок Б: UGC-CRM блогеров ──

@router.get("/bloggers", response_class=HTMLResponse)
def bloggers_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "bloggers.html",
        _ctx(request, bloggers=bloggers_svc.list_bloggers(), status_labels=bloggers_svc.STATUS_LABELS,
             followups=bloggers_svc.needs_followup(), summary=bloggers_svc.crm_summary(), msg=msg),
    )


@router.post("/bloggers/add")
async def bloggers_add(request: Request, _: bool = Depends(require_user)):
    form = await request.form()
    bid = bloggers_svc.add_blogger(**{k: form[k] for k in form})
    return RedirectResponse(f"/blogger/{bid}", status_code=303)


@router.get("/blogger/{bid}", response_class=HTMLResponse)
def blogger_detail(request: Request, bid: int, msg: str = "", _: bool = Depends(require_user)):
    data = bloggers_svc.get_blogger(bid)
    if not data:
        return RedirectResponse("/bloggers?msg=Блогер не найден", status_code=303)
    return templates.TemplateResponse(
        request, "blogger_detail.html",
        _ctx(request, b=data["b"], deals=data["deals"], linked_posts=data["posts"],
             stages=bloggers_svc.STAGES, status_labels=bloggers_svc.STATUS_LABELS,
             msg_templates=bloggers_svc.templates_for(data["b"]), msg=msg),
    )


@router.post("/blogger/{bid}/status")
def blogger_status(request: Request, bid: int, status: str = Form(...), _: bool = Depends(require_user)):
    bloggers_svc.set_status(bid, status)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Статус обновлён')}", status_code=303)


@router.post("/blogger/{bid}/delete")
def blogger_delete(request: Request, bid: int, _: bool = Depends(require_user)):
    bloggers_svc.delete_blogger(bid)
    return RedirectResponse("/bloggers?msg=Блогер удалён", status_code=303)


@router.post("/blogger/{bid}/add-deal")
def blogger_add_deal(request: Request, bid: int, product: str = Form(""), collab_type: str = Form("gift"),
                     platform: str = Form(""), _: bool = Depends(require_user)):
    bloggers_svc.add_deal(bid, product=product, collab_type=collab_type, platform=platform)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Сделка создана')}", status_code=303)


@router.post("/deal/{deal_id}/stage")
def deal_stage(request: Request, deal_id: int, bid: int = Form(...), stage: str = Form(...), _: bool = Depends(require_user)):
    bloggers_svc.set_deal_stage(deal_id, stage)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Стадия обновлена')}", status_code=303)


@router.post("/deal/{deal_id}/outcome")
def deal_outcome(request: Request, deal_id: int, bid: int = Form(...), outcome: str = Form(...), _: bool = Depends(require_user)):
    bloggers_svc.set_deal_outcome(deal_id, outcome)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Исход обновлён')}", status_code=303)


@router.post("/deal/{deal_id}/update")
async def deal_update(request: Request, deal_id: int, _: bool = Depends(require_user)):
    form = await request.form()
    bloggers_svc.update_deal(deal_id, **{k: form[k] for k in form})
    return RedirectResponse(f"/blogger/{form.get('blogger_id', '')}?msg={quote('Сделка обновлена')}", status_code=303)


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, _: bool = Depends(require_user)):
    return templates.TemplateResponse(request, "pipeline.html", _ctx(request, cols=bloggers_svc.pipeline()))


@router.post("/deal/{deal_id}/touch")
def deal_touch(request: Request, deal_id: int, bid: int = Form(...), days: int = Form(4), _: bool = Depends(require_user)):
    bloggers_svc.log_touch(deal_id, followup_days=days)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Касание записано, напоминание через %d дн.' % days)}", status_code=303)


# ── Шаблоны сообщений ──

@router.get("/templates", response_class=HTMLResponse)
def templates_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "templates.html",
        _ctx(request, items=bloggers_svc.list_templates(), cat_labels=bloggers_svc.CAT_LABELS, msg=msg),
    )


@router.post("/templates/add")
def templates_add(request: Request, name: str = Form(...), channel: str = Form("any"),
                  category: str = Form("first_touch"), body: str = Form(...), _: bool = Depends(require_user)):
    bloggers_svc.add_template(name, channel, category, body)
    return RedirectResponse("/templates?msg=Шаблон добавлен", status_code=303)


@router.post("/templates/{tid}/delete")
def templates_delete(request: Request, tid: int, _: bool = Depends(require_user)):
    bloggers_svc.delete_template(tid)
    return RedirectResponse("/templates?msg=Удалён", status_code=303)


# ── Deliverables + импорт выручки WB (B3) ──

@router.post("/deal/{deal_id}/deliverable")
def deal_add_deliverable(request: Request, deal_id: int, bid: int = Form(...), format: str = Form("reel"),
                         platform: str = Form(""), due: str = Form(""), _: bool = Depends(require_user)):
    bloggers_svc.add_deliverable(deal_id, format=format, platform=platform, due=due)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Deliverable добавлен')}", status_code=303)


@router.post("/deliverable/{did}/status")
def deliverable_status(request: Request, did: int, bid: int = Form(...), status: str = Form(""),
                       url: str = Form(""), _: bool = Depends(require_user)):
    bloggers_svc.set_deliverable(did, status=status, url=url)
    return RedirectResponse(f"/blogger/{bid}?msg={quote('Статус обновлён')}", status_code=303)


@router.post("/deliverable/{did}/delete")
def deliverable_delete(request: Request, did: int, bid: int = Form(...), _: bool = Depends(require_user)):
    bloggers_svc.delete_deliverable(did)
    return RedirectResponse(f"/blogger/{bid}", status_code=303)


@router.get("/wb-import", response_class=HTMLResponse)
def wb_import_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "wb_import.html", _ctx(request, summary=bloggers_svc.crm_summary(), msg=msg)
    )


@router.post("/wb-import")
def wb_import_do(request: Request, text: str = Form(""), _: bool = Depends(require_user)):
    res = bloggers_svc.wb_import(text)
    msg = f"Обновлено сделок: {res['updated']}"
    if res["notfound"]:
        msg += "; коды без сделок: " + ", ".join(res["notfound"][:10])
    return RedirectResponse(f"/wb-import?msg={quote(msg)}", status_code=303)


@router.post("/post/{post_id}/schedule")
def post_schedule(request: Request, post_id: int, when: str = Form(...),
                  platforms: List[str] = Form(default=[]), _: bool = Depends(require_user)):
    try:
        naive = datetime.fromisoformat(when)  # из <input type=datetime-local>, трактуем как МСК
        utc_naive = naive.replace(tzinfo=_MSK).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        ok = publisher.schedule(post_id, utc_naive, platforms=platforms or None)
        msg = "📅 Запланировано (по МСК)" if ok else "Сначала одобри пост"
    except Exception as e:
        msg = f"Неверная дата: {e}"
    return RedirectResponse(f"/post/{post_id}?msg={quote(msg)}", status_code=303)


# ── Сравнение (N товаров в один кадр по референсу) ──

@router.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "compare.html",
        _ctx(request, items=comparison_svc.list_all(), products=catalog_svc.all_with_links(), msg=msg),
    )


@router.post("/compare/new")
async def compare_new(request: Request, file: Optional[UploadFile] = File(None),
                      url: str = Form(""), product_ids: Optional[List[str]] = Form(None), title: str = Form(""),
                      style: str = Form("auto"), ratio: str = Form("4:5"),
                      _: bool = Depends(require_user)):
    try:
        pids = [p for p in (product_ids or []) if p and p.strip()]  # пусто → авто-подбор в create()
        if file is not None and file.filename:
            data = await file.read()
            cid = comparison_svc.create(data, file.filename or "ref.jpg", pids, title, style, ratio)
        elif url.strip():
            cid = comparison_svc.create_by_url(url, pids, title, style, ratio)
        else:
            raise ValueError("дай файл или ссылку на референс")
        comparison_svc.enqueue(cid)
        msg = ("Собираю сравнение — обнови через минуту-две"
               + ("" if pids else " (товары подобрал по картинке автоматически)"))
    except Exception as e:
        log.warning("compare create failed: %s", e)
        msg = f"Ошибка: {e}"
        return RedirectResponse(f"/compare?msg={quote(msg)}", status_code=303)
    return RedirectResponse(f"/compare/{cid}?msg={quote(msg)}", status_code=303)


@router.get("/compare/{cid}", response_class=HTMLResponse)
def compare_detail(request: Request, cid: int, msg: str = "", _: bool = Depends(require_user)):
    item = comparison_svc.get(cid)
    if not item:
        return RedirectResponse("/compare?msg=" + quote("не найдено"), status_code=303)
    return templates.TemplateResponse(request, "compare_detail.html", _ctx(request, item=item, msg=msg))


@router.post("/compare/{cid}/regenerate")
def compare_regenerate(request: Request, cid: int, _: bool = Depends(require_user)):
    ok = comparison_svc.enqueue(cid)
    msg = "Перегенерирую — обнови через минуту-две" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/compare/{cid}?msg=" + quote(msg), status_code=303)


@router.post("/compare/{cid}/restyle")
def compare_restyle(request: Request, cid: int, style: str = Form("auto"),
                    ratio: str = Form(""), _: bool = Depends(require_user)):
    res = comparison_svc.restyle(cid, style, ratio)
    msg = (f"Формат: {res['fmt_ru']} ({res['ratio']}) — пересобираю…" if res.get("ok")
           else res.get("error", "ошибка"))
    return RedirectResponse(f"/compare/{cid}?msg=" + quote(msg), status_code=303)


# ── Prompt-lab: веб-вьюер плейбуков промптов + каталога техник SYNTX ──

def _md_title(p) -> str:
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return p.stem


@router.get("/prompt-lab", response_class=HTMLResponse)
def promptlab_index(request: Request, _: bool = Depends(require_user)):
    base = config.DATA_DIR / "promptlab"
    files, syntx = [], []
    home_html = None
    if base.exists():
        # витрина сверху: capabilities.md (что умею) — приоритет, иначе README
        for hb in ("capabilities.md", "README.md"):
            hp = base / hb
            if hp.exists():
                import markdown as _md
                home_html = _md.markdown(hp.read_text(encoding="utf-8"),
                                         extensions=["fenced_code", "tables", "sane_lists"])
                break
        skip = {"capabilities.md", "README.md"}
        for p in sorted(base.glob("*.md")):
            if p.name not in skip:
                files.append({"path": p.name, "title": _md_title(p)})
        _labels = {"syntx": "SYNTX — 385 техник AI-контента", "egor-xr": "Егор Кузьмин XR",
                   "sasha-sadekov": "Саша Садеков"}
        for sub in sorted(base.iterdir()):
            if sub.is_dir():
                sfiles = [{"path": f"{sub.name}/{p.name}", "title": _md_title(p)}
                          for p in sorted(sub.glob("*.md"))]
                if sfiles:
                    syntx.append({"name": _labels.get(sub.name, sub.name), "files": sfiles})
    return templates.TemplateResponse(request, "promptlab.html",
        _ctx(request, pl_files=files, pl_sources=syntx, pl_content=None, pl_home=home_html, pl_title="База знаний"))


@router.get("/prompt-lab/{path:path}", response_class=HTMLResponse)
def promptlab_view(request: Request, path: str, _: bool = Depends(require_user)):
    base = (config.DATA_DIR / "promptlab").resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)) or not target.exists() or target.suffix != ".md":
        return RedirectResponse("/prompt-lab", status_code=303)
    import markdown as _md
    html = _md.markdown(target.read_text(encoding="utf-8"),
                        extensions=["fenced_code", "tables", "sane_lists"])
    return templates.TemplateResponse(request, "promptlab.html",
        _ctx(request, pl_content=html, pl_title=_md_title(target), pl_files=None, pl_syntx=None))


@router.post("/compare/{cid}/delete")
def compare_delete(request: Request, cid: int, _: bool = Depends(require_user)):
    comparison_svc.delete(cid)
    return RedirectResponse("/compare?msg=" + quote("Удалено"), status_code=303)


# ── Бесшовная карусель (один фон -> N слайдов) ──

@router.get("/seamless", response_class=HTMLResponse)
def seamless_page(request: Request, msg: str = "", _: bool = Depends(require_user)):
    return templates.TemplateResponse(
        request, "seamless.html",
        _ctx(request, items=seamless_svc.list_all(), products=catalog_svc.all_with_links(),
             models=brand_svc.list_models(), msg=msg),
    )


@router.post("/seamless/new")
async def seamless_new(request: Request, product_id: str = Form(...), slides_n: int = Form(5),
                       theme: str = Form(""), headlines: str = Form(""),
                       model_keys: List[str] = Form(default=[]), slide_scenes: str = Form(""),
                       file: Optional[UploadFile] = File(None), _: bool = Depends(require_user)):
    try:
        lines = [ln.strip() for ln in headlines.splitlines() if ln.strip()]
        scenes = [ln.strip() for ln in slide_scenes.splitlines() if ln.strip()]
        ref_bytes, ref_name = None, ""
        if file is not None and file.filename:
            ref_bytes = await file.read()
            ref_name = file.filename
        keys = [k for k in model_keys if k]
        cid = seamless_svc.create(product_id, slides_n, theme, ref_bytes, ref_name, lines,
                                  model_key=(keys[0] if len(keys) == 1 else ""),
                                  model_keys=(keys if len(keys) >= 2 else None),
                                  slide_scenes=scenes)
        seamless_svc.enqueue(cid)
        msg = "Собираю карусель — обнови страницу через пару минут"
    except Exception as e:
        log.warning("seamless create failed: %s", e)
        msg = f"Ошибка: {e}"
        return RedirectResponse(f"/seamless?msg={quote(msg)}", status_code=303)
    return RedirectResponse(f"/seamless/{cid}?msg={quote(msg)}", status_code=303)


@router.get("/seamless/{cid}", response_class=HTMLResponse)
def seamless_detail(request: Request, cid: int, msg: str = "", _: bool = Depends(require_user)):
    item = seamless_svc.get(cid)
    if not item:
        return RedirectResponse("/seamless?msg=" + quote("не найдено"), status_code=303)
    return templates.TemplateResponse(request, "seamless_detail.html", _ctx(request, item=item, msg=msg))


@router.post("/seamless/{cid}/regenerate")
def seamless_regenerate(request: Request, cid: int, _: bool = Depends(require_user)):
    ok = seamless_svc.enqueue(cid)
    msg = "Перегенерирую — обнови через пару минут" if ok else "Уже идёт генерация — подожди"
    return RedirectResponse(f"/seamless/{cid}?msg=" + quote(msg), status_code=303)


@router.post("/seamless/{cid}/delete")
def seamless_delete(request: Request, cid: int, _: bool = Depends(require_user)):
    seamless_svc.delete(cid)
    return RedirectResponse("/seamless?msg=" + quote("Удалено"), status_code=303)
