"""Стадия 1 — Контент-план: обёртка content_plan.generate в БД + черновики постов."""
from __future__ import annotations

import logging
from typing import List, Optional

from .. import config, content_plan
from ..db.base import session_scope
from ..db.models import ContentPlan, Post

log = logging.getLogger(__name__)

# Форматы из content_plan.PostFormat → наши коды format в posts.
_FMT = {"Reels": "reels", "Карусель": "carousel", "Stories": "stories", "Пост (фото)": "photo"}


def generate_and_store(n_posts: int, start_date: str, cadence: str, focus: Optional[str],
                       rhythm: str = "2:1", slots: str = "") -> int:
    """Генерит план через Claude и сохраняет в БД. Возвращает id плана."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    plan = content_plan.generate(n_posts=n_posts, start_date=start_date, cadence=cadence,
                                 focus=focus, rhythm=rhythm, slots=slots)
    raw = plan.model_dump(mode="json")
    with session_scope() as s:
        row = ContentPlan(
            period=plan.period,
            strategy_summary=plan.strategy_summary,
            rubrics_legend=plan.rubrics_legend,
            params={"n_posts": n_posts, "start_date": start_date, "cadence": cadence,
                    "focus": focus, "rhythm": rhythm, "slots": slots},
            raw=raw,
        )
        s.add(row)
        s.flush()
        log.info("content plan stored id=%s posts=%d", row.id, len(plan.posts))
        return row.id


def _planned_utc(date_s: str, time_s: str):
    """Дата+время плана (МСК) → scheduled_at в UTC-naive (как в publisher.schedule).
    Ставим на черновик как ПЛАНОВУЮ дату — планировщик публикации фильтрует по
    status='scheduled', поэтому черновик сам не улетит; дата лишь предзаполняет слот."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        hh, mm = (time_s or "10:00").split(":")[:2]
        naive = datetime.fromisoformat(f"{date_s}T{int(hh):02d}:{int(mm):02d}")
        return naive.replace(tzinfo=ZoneInfo("Europe/Moscow")).astimezone(
            ZoneInfo("UTC")).replace(tzinfo=None)
    except Exception:
        return None


def materialize_posts(plan_id: int) -> int:
    """Создаёт черновики постов из плана + проставляет плановую дату/слот. Идемпотентно."""
    with session_scope() as s:
        plan = s.get(ContentPlan, plan_id)
        if not plan or not plan.raw:
            return 0
        if s.query(Post).filter(Post.plan_id == plan_id).count() > 0:
            return 0
        added = 0
        for p in plan.raw.get("posts", []):
            s.add(Post(
                plan_id=plan_id,
                format=_FMT.get(p.get("format", ""), "photo"),
                rubric=p.get("rubric", ""),
                product=p.get("product", ""),
                hook=p.get("hook", ""),
                caption=p.get("caption", ""),
                hashtags=(p.get("hashtags", []) or [])[:5],
                visual_idea=p.get("visual_idea", ""),
                cta=p.get("cta", ""),
                scheduled_at=_planned_utc(p.get("date", ""), p.get("time", "")),
                status="draft",
            ))
            added += 1
        return added


def list_plans() -> List[dict]:
    with session_scope() as s:
        plans = s.query(ContentPlan).order_by(ContentPlan.id.desc()).all()
        return [{
            "id": p.id, "period": p.period, "strategy_summary": p.strategy_summary,
            "n_posts": len((p.raw or {}).get("posts", [])),
            "materialized": s.query(Post).filter(Post.plan_id == p.id).count(),
            "created_at": p.created_at,
        } for p in plans]


def get_plan(plan_id: int) -> Optional[dict]:
    with session_scope() as s:
        p = s.get(ContentPlan, plan_id)
        if not p:
            return None
        return {
            "id": p.id, "period": p.period, "strategy_summary": p.strategy_summary,
            "rubrics_legend": p.rubrics_legend or [], "posts": (p.raw or {}).get("posts", []),
            "materialized": s.query(Post).filter(Post.plan_id == p.id).count(),
        }
