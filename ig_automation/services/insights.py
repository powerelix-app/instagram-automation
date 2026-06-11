"""Стадия 6 — Аналитика: метрики опубликованных постов через IG insights."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .. import config, instagram
from ..db.base import session_scope
from ..db.models import Post, PostMetric
from . import tokens

log = logging.getLogger(__name__)


def pull(post_id: int) -> bool:
    """Тянет метрики поста и пишет снимок PostMetric. Симулированные/неопубликованные — пропуск."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post or post.status != "published" or not post.ig_media_id or post.ig_media_id == "SIMULATED":
            return False
        mid = post.ig_media_id
    data = instagram.get_media_insights(mid, tokens.current_token())
    if not data:
        return False
    with session_scope() as s:
        s.add(PostMetric(
            post_id=post_id, reach=data.get("reach", 0), likes=data.get("likes", 0),
            comments=data.get("comments", 0), saves=data.get("saved", 0),
            shares=data.get("shares", 0), plays=data.get("plays", 0),
        ))
    return True


def pull_all() -> int:
    """Обновляет метрики реальных постов за последние 30 дней. Для планировщика."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    with session_scope() as s:
        ids = [
            p.id for p in s.query(Post)
            .filter(Post.status == "published", Post.ig_media_id != "SIMULATED",
                    Post.ig_media_id != "", Post.published_at >= cutoff)
            .all()
        ]
    return sum(1 for pid in ids if pull(pid))


def overview() -> Dict:
    """Сводка для /analytics: опубликованные посты с последними метриками + средние по рубрикам."""
    with session_scope() as s:
        posts = (
            s.query(Post).filter(Post.status == "published")
            .order_by(Post.published_at.desc()).all()
        )
        rows: List[dict] = []
        rub: Dict[str, list] = {}
        for p in posts:
            m = (
                s.query(PostMetric).filter(PostMetric.post_id == p.id)
                .order_by(PostMetric.id.desc()).first()
            )
            simulated = p.ig_media_id == "SIMULATED"
            reach = m.reach if m else 0
            rows.append({
                "id": p.id, "hook": p.hook, "rubric": p.rubric, "product": p.product,
                "format": p.format, "simulated": simulated, "permalink": p.permalink,
                "published_at": p.published_at,
                "reach": reach, "likes": m.likes if m else 0,
                "comments": m.comments if m else 0, "saves": m.saves if m else 0,
                "shares": m.shares if m else 0,
            })
            if not simulated and m:
                rub.setdefault(p.rubric or "—", []).append(reach)
        by_rubric = [
            {"rubric": k, "posts": len(v), "avg_reach": round(sum(v) / len(v)) if v else 0}
            for k, v in sorted(rub.items(), key=lambda kv: -(sum(kv[1]) / len(kv[1]) if kv[1] else 0))
        ]
        real = [r for r in rows if not r["simulated"]]
        return {
            "rows": rows, "by_rubric": by_rubric,
            "total_published": len(rows), "real_published": len(real),
            "simulated": len(rows) - len(real),
        }
