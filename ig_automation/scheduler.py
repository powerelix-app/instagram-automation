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
    sched.add_listener(_record_tick, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    sched.start()
    log.info("scheduler started: refresh_ig_token каждые 24ч")
    return sched
