"""Таблицы контент-завода. SQLAlchemy 2.0 (Mapped/mapped_column), Python 3.9-совместимо."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _now() -> datetime:
    return datetime.utcnow()


class AppState(Base):
    """Служебное key-value: IG-токен/expiry, heartbeat планировщика, флаги."""
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrendReel(Base):
    """Стадия 0 — вирусный чужой Reels, собранный через Apify."""
    __tablename__ = "trend_reels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_actor: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    username: Mapped[str] = mapped_column(String(128), default="")
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    video_url: Mapped[str] = mapped_column(String(1024), default="")
    local_media_path: Mapped[str] = mapped_column(String(512), default="")
    thumbnail_url: Mapped[str] = mapped_column(String(1024), default="")
    music_info: Mapped[str] = mapped_column(String(512), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(128), default="")
    relevant: Mapped[bool] = mapped_column(Boolean, default=True)
    relevance_reason: Mapped[str] = mapped_column(String(255), default="")
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class HookAnalysis(Base):
    """Разбор хука вирусного ролика (Claude)."""
    __tablename__ = "hook_analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trend_reel_id: Mapped[int] = mapped_column(ForeignKey("trend_reels.id"))
    hook: Mapped[str] = mapped_column(Text, default="")
    retention_device: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(Text, default="")
    structure: Mapped[str] = mapped_column(Text, default="")
    why_viral: Mapped[str] = mapped_column(Text, default="")
    adapted_idea: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Idea(Base):
    """Банк идей — из разведки, плана или вручную."""
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")  # trend|plan|manual
    trend_reel_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trend_reels.id"), nullable=True)
    rubric: Mapped[str] = mapped_column(String(64), default="")
    product: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="new")  # new|in_work|used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ContentPlan(Base):
    """Сгенерированный контент-план (обёртка content_plan.generate)."""
    __tablename__ = "content_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(128), default="")
    strategy_summary: Mapped[str] = mapped_column(Text, default="")
    rubrics_legend: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Post(Base):
    """Производственная единица — пост, идущий по конвейеру до публикации."""
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("content_plans.id"), nullable=True)
    idea_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ideas.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(16), default="photo")  # photo|carousel|reels
    rubric: Mapped[str] = mapped_column(String(64), default="")
    product: Mapped[str] = mapped_column(String(128), default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    visual_idea: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(String(256), default="")
    # draft|generating|review|approved|scheduled|published|failed
    status: Mapped[str] = mapped_column(String(16), default="draft")
    disclaimer_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    compliance_notes: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ig_media_id: Mapped[str] = mapped_column(String(64), default="")
    permalink: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PostAsset(Base):
    """Сгенерированный ассет поста (картинка/видео)."""
    __tablename__ = "post_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    kind: Mapped[str] = mapped_column(String(16), default="image")  # image|video
    path: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    ord: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BrandAsset(Base):
    """Бренд-ассеты для генерации: лицо AI-модели, логотип, банки товаров."""
    __tablename__ = "brand_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="product")  # model|logo|product
    product: Mapped[str] = mapped_column(String(128), default="")  # для kind=product
    label: Mapped[str] = mapped_column(String(128), default="")
    path: Mapped[str] = mapped_column(String(512), default="")  # /media/brand/...
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PostMetric(Base):
    """Снимок метрик опубликованного поста (insights)."""
    __tablename__ = "post_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
