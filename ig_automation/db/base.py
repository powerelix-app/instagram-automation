"""SQLite + SQLAlchemy 2.0: движок, сессии, Base. Зеркало паттерна wb-promotion."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .. import config


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: Optional[sessionmaker] = None


def init(db_path: Optional[str] = None) -> None:
    """Создаёт движок и таблицы. Идемпотентно (create_all безопасен)."""
    global _engine, _SessionLocal
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    _SessionLocal = sessionmaker(
        bind=_engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    from . import models  # noqa: F401  — регистрация таблиц до create_all
    Base.metadata.create_all(_engine)
    _migrate(_engine)


def _migrate(engine) -> None:
    """Лёгкие идемпотентные миграции (create_all не добавляет новые колонки)."""
    adds = {
        "trend_reels": [
            ("thumbnail_url", "VARCHAR DEFAULT ''"),
            ("relevant", "BOOLEAN DEFAULT 1"),
            ("relevance_reason", "VARCHAR DEFAULT ''"),
            ("lang", "VARCHAR DEFAULT ''"),
            ("media_type", "VARCHAR DEFAULT ''"),
            ("images", "JSON"),
        ],
        "hook_analyses": [
            ("visual_notes", "TEXT DEFAULT ''"),
            ("camera_work", "TEXT DEFAULT ''"),
            ("is_deep", "BOOLEAN DEFAULT 0"),
        ],
        "posts": [
            ("product_id", "VARCHAR DEFAULT ''"),
            ("reels_script", "TEXT"),
            ("blogger_id", "INTEGER"),
            ("tg_message_id", "VARCHAR DEFAULT ''"),
        ],
        "deals": [
            ("last_touch_at", "DATETIME"),
            ("next_followup_at", "DATETIME"),
            ("rights_repost", "BOOLEAN DEFAULT 0"),
            ("rights_ads", "BOOLEAN DEFAULT 0"),
            ("rights_term", "VARCHAR DEFAULT ''"),
        ],
    }
    with engine.begin() as conn:
        for table, cols in adds.items():
            existing = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            for name, ddl in cols:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("db.init() не вызван")
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    s = get_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
