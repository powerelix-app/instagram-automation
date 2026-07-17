"""Воркер очереди генерации. Отдельный процесс/сервис: рестарт веб-сервера
(content-factory) больше не убивает идущую генерацию — она живёт здесь.

Запуск: python -m ig_automation.worker
Один воркер = последовательная генерация (не жжём деньги параллельными fal-вызовами).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from .db import base as db
from .db.models import GenJob
from .services import producer

log = logging.getLogger("cf.worker")
POLL_SEC = 3


def _reset_orphans() -> None:
    """Задачи, застрявшие в running (воркер убили посреди работы), возвращаем
    в очередь — генерация перезапишет файлы, это идемпотентно."""
    with db.session_scope() as s:
        orphans = s.query(GenJob).filter(GenJob.status == "running").all()
        for j in orphans:
            j.status = "queued"
            j.started_at = None
            log.warning("orphan job %s (sb=%s %s) -> queued", j.id, j.sb_id, j.kind)


def _take_next():
    """Атомарно берём старейшую queued-задачу и помечаем running."""
    with db.session_scope() as s:
        j = (s.query(GenJob).filter(GenJob.status == "queued")
             .order_by(GenJob.created_at, GenJob.id).first())
        if not j:
            return None
        j.status = "running"
        j.started_at = datetime.utcnow()
        return (j.id, j.sb_id, j.post_id, j.kind, j.only)


def _finish(job_id: int, status: str, error: str = "") -> None:
    with db.session_scope() as s:
        j = s.get(GenJob, job_id)
        if j:
            j.status = status
            j.error = error[:500]
            j.finished_at = datetime.utcnow()


def run() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init()
    _reset_orphans()
    log.info("worker запущен, poll=%ss", POLL_SEC)
    while True:
        job = _take_next()
        if not job:
            time.sleep(POLL_SEC)
            continue
        job_id, sb_id, post_id, kind, only = job
        log.info("job %s: %s sb=%s post=%s only=%s", job_id, kind, sb_id, post_id, only)
        try:
            producer.execute_job(kind, sb_id=sb_id, post_id=post_id, only=only)
            _finish(job_id, "done")
            log.info("job %s done", job_id)
        except Exception as e:  # execute_job уже поставил status=error раскадровке
            _finish(job_id, "failed", str(e))
            log.exception("job %s failed", job_id)


if __name__ == "__main__":
    run()
