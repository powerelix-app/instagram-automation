"""Стадия 2 — Банк идей: список, добавление вручную, превращение в черновик поста."""
from __future__ import annotations

from typing import List, Optional

from ..db.base import session_scope
from ..db.models import Idea, Post


def list_ideas() -> List[Idea]:
    with session_scope() as s:
        return s.query(Idea).order_by(Idea.id.desc()).all()


def add_idea(text: str, hook: str = "", rubric: str = "", product: str = "") -> int:
    with session_scope() as s:
        idea = Idea(text=text, hook=hook, rubric=rubric, product=product, source="manual", status="new")
        s.add(idea)
        s.flush()
        return idea.id


def to_post(idea_id: int) -> Optional[int]:
    """Создаёт черновик поста из идеи и помечает идею использованной."""
    with session_scope() as s:
        idea = s.get(Idea, idea_id)
        if not idea:
            return None
        post = Post(
            idea_id=idea_id,
            rubric=idea.rubric,
            product=idea.product,
            hook=idea.hook or idea.text[:120],
            visual_idea=idea.text,
            status="draft",
        )
        s.add(post)
        idea.status = "used"
        s.flush()
        return post.id
