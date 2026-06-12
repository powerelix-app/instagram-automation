"""Планировщик (APScheduler). Фаза 1 — каркас: heartbeat + ежедневный refresh токена.
Фазы 6-7 добавят publish_due, pull_insights, recon_cron.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler

from .services import tokens

log = logging.getLogger(__name__)


def _refresh_ig_token() -> None:
    try:
        tokens.ensure_fresh()
    except Exception as e:  # планировщик не должен падать тихо
        log.warning("refresh_ig_token job failed: %s", e)


def _publish_due() -> None:
    try:
        from .services import publisher
        n = publisher.publish_due()
        if n:
            log.info("publish_due: опубликовано запланированных: %d", n)
    except Exception as e:
        log.warning("publish_due job failed: %s", e)


def _pull_insights() -> None:
    try:
        from .services import insights
        n = insights.pull_all()
        if n:
            log.info("pull_insights: обновлено метрик: %d", n)
    except Exception as e:
        log.warning("pull_insights job failed: %s", e)


def _followup_reminders() -> None:
    """Ежедневная сводка задач в Telegram: что опубликовать/проверить + кому из блогеров писать."""
    try:
        from . import config
        from .services import bloggers, notify
        if not notify.configured():
            return
        from datetime import date
        from .db.base import session_scope
        from .db.models import Post
        today = date.today().isoformat()
        with session_scope() as s:
            def cnt(st):
                return s.query(Post).filter(Post.status == st).count()
            review, approved, draft, failed = cnt("review"), cnt("approved"), cnt("draft"), cnt("failed")
            due = sum(1 for p in s.query(Post).filter(Post.status == "scheduled").all()
                      if (p.scheduled_at or "")[:10] <= today)
        fu = bloggers.needs_followup()
        lines = ["📌 <b>POWERELIX — план на день</b>"]
        if due:
            lines.append(f"🔴 Опубликовать сегодня: {due}")
        if failed:
            lines.append(f"⚠️ Ошибки публикации: {failed}")
        if review:
            lines.append(f"👀 На проверке (аппрув): {review}")
        if approved:
            lines.append(f"✅ Готовы — запланировать: {approved}")
        if draft:
            lines.append(f"✏️ Черновики: {draft}")
        if fu:
            lines.append(f"\n📣 Написать блогерам ({len(fu)}):")
            for x in fu[:10]:
                b = x.get("blogger")
                who = ("@" + (b.handle or b.name)) if b else f"сделка #{x['deal'].get('id')}"
                lines.append(f"• {who} — {x['deal'].get('stage', '')}")
        if len(lines) == 1:
            lines.append("Всё разобрано 👍")
        lines.append(f"\n{config.PUBLIC_BASE}")
        notify.send("\n".join(lines))
    except Exception as e:
        log.warning("followup_reminders job failed: %s", e)


def _record_tick(event) -> None:
    try:
        tokens.set_state(
            "scheduler_last_tick",
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    except Exception:
        pass


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_refresh_ig_token, "interval", hours=24, id="refresh_ig_token")
    sched.add_job(_publish_due, "interval", minutes=1, id="publish_due")
    sched.add_job(_pull_insights, "interval", hours=6, id="pull_insights")
    # Ежедневная сводка задач в Telegram — 06:00 UTC = 09:00 МСК.
    sched.add_job(_followup_reminders, "cron", hour=6, minute=0, id="followup_reminders")
    sched.add_listener(_record_tick, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    sched.start()
    log.info("scheduler started: refresh_ig_token 24ч, publish_due 1мин, pull_insights 6ч, "
             "followup_reminders 09:00 МСК")
    return sched
