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
    lang: Mapped[str] = mapped_column(String(8), default="")  # ru|en|other
    media_type: Mapped[str] = mapped_column(String(12), default="")  # video|carousel|image
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
    visual_notes: Mapped[str] = mapped_column(Text, default="")
    camera_work: Mapped[str] = mapped_column(Text, default="")
    is_deep: Mapped[bool] = mapped_column(Boolean, default=False)
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
    blogger_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bloggers.id"), nullable=True)  # контент для блогера
    format: Mapped[str] = mapped_column(String(16), default="photo")  # photo|carousel|reels
    rubric: Mapped[str] = mapped_column(String(64), default="")
    product: Mapped[str] = mapped_column(String(128), default="")
    product_id: Mapped[str] = mapped_column(String(32), default="")  # id товара из каталога (привязка)
    reels_script: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # сценарий+раскадровка Reels
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


class Blogger(Base):
    """UGC-блогер для охвата (движок Б). Источник нишевого контента/рекламы."""
    __tablename__ = "bloggers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    handle: Mapped[str] = mapped_column(String(128), default="")  # @ник
    platform: Mapped[str] = mapped_column(String(16), default="instagram")  # vk|telegram|instagram|youtube|tiktok
    url: Mapped[str] = mapped_column(String(512), default="")
    niche: Mapped[str] = mapped_column(String(128), default="")  # нутрициолог/фитнес/ЗОЖ/мамы
    followers: Mapped[int] = mapped_column(Integer, default=0)
    er: Mapped[str] = mapped_column(String(16), default="")  # вовлечённость, как строка (напр. «3.2%»)
    city: Mapped[str] = mapped_column(String(64), default="")
    audience: Mapped[str] = mapped_column(String(255), default="")  # пол/возраст/гео
    contact: Mapped[str] = mapped_column(String(255), default="")  # TG/почта
    collab_type: Mapped[str] = mapped_column(String(16), default="gift")  # gift|paid|cpa
    usual_rate: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="lead")  # lead|active|ambassador|blacklist
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Deal(Base):
    """Сделка/коллаборация с блогером + воронка + атрибуция + комплаенс."""
    __tablename__ = "deals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blogger_id: Mapped[int] = mapped_column(ForeignKey("bloggers.id"))
    product: Mapped[str] = mapped_column(String(128), default="")  # SKU/nmId
    # воронка: lead→qualify→contacted→negotiating→agreed→shipped→content→review→published→paid→repeat
    stage: Mapped[str] = mapped_column(String(16), default="lead")
    outcome: Mapped[str] = mapped_column(String(16), default="open")  # open|won|lost|no_reply|not_fit
    collab_type: Mapped[str] = mapped_column(String(16), default="gift")
    platform: Mapped[str] = mapped_column(String(16), default="")  # площадка размещения
    promo_code: Mapped[str] = mapped_column(String(32), default="")
    replacement_article: Mapped[str] = mapped_column(String(32), default="")  # подменный артикул WB
    utm: Mapped[str] = mapped_column(String(128), default="")
    erid: Mapped[str] = mapped_column(String(64), default="")  # маркировка рекламы
    offer_value: Mapped[str] = mapped_column(String(64), default="")  # оплата/ценность
    tracking: Mapped[str] = mapped_column(String(64), default="")  # трек отправления товара
    post_url: Mapped[str] = mapped_column(String(512), default="")
    attributed_orders: Mapped[int] = mapped_column(Integer, default=0)
    attributed_revenue: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_touch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # права на UGC-контент блогера
    rights_repost: Mapped[bool] = mapped_column(Boolean, default=False)  # репост у нас
    rights_ads: Mapped[bool] = mapped_column(Boolean, default=False)  # реклама от лица блогера (whitelisting)
    rights_term: Mapped[str] = mapped_column(String(32), default="")  # срок лицензии
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Deliverable(Base):
    """Что блогер должен выложить по сделке (deliverable) + статус."""
    __tablename__ = "deliverables"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    format: Mapped[str] = mapped_column(String(16), default="reel")  # reel|story|post|video
    platform: Mapped[str] = mapped_column(String(16), default="")
    due: Mapped[str] = mapped_column(String(32), default="")  # срок (свободный текст, напр. «до 15.06»)
    status: Mapped[str] = mapped_column(String(16), default="requested")  # requested|received|approved|published
    url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProductLink(Base):
    """Артикул/ссылка WB на товар каталога — для вставки в текст поста."""
    __tablename__ = "product_links"
    product_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # id из brand_powerelix.json
    nmid: Mapped[str] = mapped_column(String(32), default="")  # артикул Wildberries
    wb_url: Mapped[str] = mapped_column(String(512), default="")
    note: Mapped[str] = mapped_column(String(255), default="")  # доп. акцент для текста
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class MessageTemplate(Base):
    """Шаблон сообщения блогеру (аутрич/бриф/напоминание) с плейсхолдерами."""
    __tablename__ = "message_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    channel: Mapped[str] = mapped_column(String(16), default="any")  # telegram|email|dm|any
    category: Mapped[str] = mapped_column(String(24), default="first_touch")  # first_touch|followup|brief
    body: Mapped[str] = mapped_column(Text, default="")
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
