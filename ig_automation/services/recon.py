"""Стадия 0 — Разведка трендов: сбор вирусных Reels (Apify) + разбор хука (Claude)."""
from __future__ import annotations

import hashlib
import logging
from typing import List, Optional

import anthropic
import requests
from pydantic import BaseModel, Field
from sqlalchemy import func

from .. import apify, config
from ..db.base import session_scope
from ..db.models import HookAnalysis, Idea, TrendReel

log = logging.getLogger(__name__)


# ── Сбор ──

# CDN Instagram (cdninstagram.com) недоступен с РФ-VPS — после первого таймаута
# выключаем скачивание превью на этот процесс, чтобы сбор не висел минутами.
# Удалённый URL всё равно сохраняем — браузер пользователя (с VPN) подтянет сам.
_cdn_blocked = False


def _download_thumb(url: str) -> str:
    """Best-effort скачивание превью (fail-fast). Возвращает /media-путь или ''."""
    global _cdn_blocked
    if not url or _cdn_blocked:
        return ""
    try:
        name = "thumb_" + hashlib.md5(url.encode()).hexdigest()[:16] + ".jpg"
        dest = config.MEDIA_DIR / name
        if not dest.exists():
            r = requests.get(url, timeout=6)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return f"/media/{name}"
    except requests.RequestException as e:
        _cdn_blocked = True
        log.warning("thumb download failed — отключаю скачивание превью на процесс: %s", e)
        return ""


class _RelItem(BaseModel):
    index: int
    relevant: bool
    reason: str = Field(default="", description="кратко почему (рус.)")
    lang: str = Field(default="other", description="язык ролика: ru, en или other")


class _RelOut(BaseModel):
    items: List[_RelItem]


_REL_SYSTEM = """Бренд POWERELIX — БАДы, витамины, спортпит, ЗОЖ; аудитория РУССКОЯЗЫЧНАЯ.
Тебе дают список вирусных Reels (автор, текст, хэштеги). Для КАЖДОГО верни:
- relevant: релевантен ли как источник идей/хуков для контента бренда. Считай релевантным ШИРОКО:
  здоровье, самочувствие, тело, энергия, сон, иммунитет, ЖКТ, питание, нутрициология,
  витамины/добавки, спорт/фитнес, красота-изнутри, привычки/режим, продуктивность через тело.
  Отсекай (relevant=false) ТОЛЬКО чисто развлекательный вирусняк без связи со здоровьем/телом:
  relatable-юмор, фильтры/эффекты, «угадай животное», мемы про отношения, мода, танцы, дети-приколы.
- reason: кратко почему (рус.).
- lang: язык ролика по тексту/хэштегам — "ru" (русский), "en" (английский/латиница), "other".
Верни по элементу на каждый индекс."""


def _score_relevance(reels: List[dict]) -> List[tuple]:
    """Один батч-запрос к Claude: relevant + причина + язык для каждого ролика.
    Возвращает [(bool, reason, lang)] выровненный по reels. Любой сбой → все релевантны."""
    if not config.ANTHROPIC_API_KEY or not reels:
        return [(True, "", "")] * len(reels)
    lines = []
    for i, r in enumerate(reels):
        tags = " ".join(r.get("hashtags") or [])[:200]
        cap = (r.get("caption") or "").replace("\n", " ")[:200]
        lines.append(f"[{i}] @{r.get('username', '')} | {cap} | теги: {tags}")
    try:
        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=4000, system=_REL_SYSTEM,
            messages=[{"role": "user", "content": "Ролики:\n" + "\n".join(lines)}],
            output_format=_RelOut,
        )
        verdict = {it.index: (it.relevant, it.reason, (getattr(it, "lang", "") or "").lower())
                   for it in resp.parsed_output.items}
        return [verdict.get(i, (True, "", "")) for i in range(len(reels))]
    except Exception as e:
        log.warning("relevance scoring failed, keeping all: %s", e)
        return [(True, "", "")] * len(reels)


def _store_reels(reels: List[dict], topic: str) -> int:
    """AI-оценка релевантности пачки + дедуп по url + запись. Возвращает кол-во новых."""
    scores = _score_relevance(reels)
    added = 0
    with session_scope() as s:
        for r, (rel, reason, lang) in zip(reels, scores):
            url = r.get("url") or ""
            if url and s.query(TrendReel).filter(TrendReel.url == url).first():
                continue
            s.add(TrendReel(
                source_actor=apify.ACTOR, url=url, username=r["username"],
                play_count=r["play_count"], likes=r["likes"], comments=r["comments"],
                caption=r["caption"], hashtags=r["hashtags"], video_url=r["video_url"],
                local_media_path=_download_thumb(r["thumbnail_url"]),
                thumbnail_url=r["thumbnail_url"], music_info=str(r["music_info"])[:512],
                transcript=str(r["transcript"]), topic=topic,
                relevant=rel, relevance_reason=(reason or "")[:255], lang=(lang or "")[:8],
                media_type=r.get("media_type", ""),
            ))
            added += 1
    log.info("store %r: +%d из %d (релевантных %d, ru %d)", topic, added, len(reels),
             sum(1 for rel, _, _ in scores), sum(1 for _, _, lang in scores if lang == "ru"))
    return added


def scrape_topic(topic: str, limit: int = 30) -> int:
    """Сбор по ключевому слову (выдача часто глобально-вирусная — AI-фильтр чистит)."""
    reels = apify.search_reels(topic, limit=limit)
    if not reels:
        log.warning("scrape_topic %r: 0 роликов", topic)
        return 0
    return _store_reels(reels, topic)


def scrape_account(handle: str, limit: int = 30) -> int:
    """Сбор топ-Reels нишевого аккаунта (релевантность по построению). topic = @handle."""
    h = handle.lstrip("@").strip().strip("/").split("/")[-1]
    if not h:
        return 0
    reels = apify.account_reels(h, limit=limit)
    if not reels:
        log.warning("scrape_account %r: 0 роликов", h)
        return 0
    return _store_reels(reels, "@" + h)


# ── Разбор хука (Claude) ──

class HookOut(BaseModel):
    hook: str = Field(description="Главный хук ролика: что в первые 1-3 секунды цепляет зрителя")
    retention_device: str = Field(description="Приём удержания: что заставляет досмотреть (петля, интрига, список, бьюти-эффект)")
    trigger: str = Field(description="Эмоциональный/психологический триггер аудитории")
    structure: str = Field(description="Структура ролика по шагам (сцена 1 → 2 → …)")
    why_viral: str = Field(description="Почему ролик набрал просмотры — главная причина")
    adapted_idea: str = Field(description="Как адаптировать механику под бренд БАД POWERELIX (без копирования), с учётом юр-правил рекламы БАД")


_ANALYZE_SYSTEM = """Ты — продюсер коротких видео и эксперт по виральности в нише здоровья/БАД/ЗОЖ.
Тебе дают данные вирусного Instagram Reels (текст, метрики, музыка). Разбери его механику,
чтобы наш бренд добавок POWERELIX мог СОЗДАТЬ СВОЙ оригинальный ролик по той же механике
(не копию). Учитывай юр-правила рекламы БАД в РФ: без «лечит/диагностирует», формулировки
мягкие («поддерживает», «способствует»). Верни строго структуру по схеме."""


def analyze(reel_id: int) -> Optional[int]:
    """Разбирает ролик через Claude, пишет hook_analyses. Возвращает id разбора."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        if not reel:
            return None
        info = (
            f"Просмотры: {reel.play_count}, лайки: {reel.likes}, комментарии: {reel.comments}\n"
            f"Музыка: {reel.music_info or '—'}\n"
            f"Текст поста: {reel.caption or '—'}\n"
            f"Хэштеги: {', '.join(reel.hashtags or [])}\n"
            f"Транскрипт: {reel.transcript or '—'}"
        )
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL,
        max_tokens=4000,
        system=_ANALYZE_SYSTEM,
        messages=[{"role": "user", "content": f"Разбери этот вирусный Reels:\n\n{info}"}],
        output_format=HookOut,
    )
    out = resp.parsed_output
    with session_scope() as s:
        row = HookAnalysis(
            trend_reel_id=reel_id,
            hook=out.hook,
            retention_device=out.retention_device,
            trigger=out.trigger,
            structure=out.structure,
            why_viral=out.why_viral,
            adapted_idea=out.adapted_idea,
        )
        s.add(row)
        s.flush()
        return row.id


def latest_analysis(reel_id: int) -> Optional[HookAnalysis]:
    with session_scope() as s:
        return (
            s.query(HookAnalysis)
            .filter(HookAnalysis.trend_reel_id == reel_id)
            .order_by(HookAnalysis.id.desc())
            .first()
        )


def to_idea(reel_id: int) -> Optional[int]:
    """Кладёт адаптированную идею из последнего разбора в Банк идей."""
    with session_scope() as s:
        an = (
            s.query(HookAnalysis)
            .filter(HookAnalysis.trend_reel_id == reel_id)
            .order_by(HookAnalysis.id.desc())
            .first()
        )
        if not an:
            return None
        idea = Idea(
            text=an.adapted_idea,
            hook=an.hook,
            source="trend",
            trend_reel_id=reel_id,
            status="new",
        )
        s.add(idea)
        s.flush()
        return idea.id


def list_topics() -> List[dict]:
    """Темы (запросы) со счётчиком, по свежести последнего сбора."""
    with session_scope() as s:
        rows = (
            s.query(TrendReel.topic, func.count(TrendReel.id))
            .group_by(TrendReel.topic)
            .order_by(func.max(TrendReel.scraped_at).desc())
            .all()
        )
        return [{"topic": t, "count": c} for t, c in rows if t]


def count_irrelevant(topic: Optional[str] = None) -> int:
    with session_scope() as s:
        q = s.query(TrendReel).filter(TrendReel.relevant.is_(False))
        if topic:
            q = q.filter(TrendReel.topic == topic)
        return q.count()


def list_reels(topic: Optional[str] = None, include_irrelevant: bool = False,
               lang: str = "") -> List[dict]:
    """Список роликов для UI, по убыванию просмотров. По умолчанию — только
    релевантные нише (AI-фильтр); include_irrelevant=True показывает и отсеянные;
    lang="ru" → только русскоязычные."""
    with session_scope() as s:
        q = s.query(TrendReel)
        if topic:
            q = q.filter(TrendReel.topic == topic)
        if not include_irrelevant:
            q = q.filter(TrendReel.relevant.is_(True))
        if lang:
            q = q.filter(TrendReel.lang == lang)
        reels = q.order_by(TrendReel.play_count.desc()).all()
        analyzed_ids = {a.trend_reel_id for a in s.query(HookAnalysis.trend_reel_id).all()}
        out = []
        for r in reels:
            an = (
                s.query(HookAnalysis)
                .filter(HookAnalysis.trend_reel_id == r.id)
                .order_by(HookAnalysis.id.desc())
                .first()
            )
            out.append({
                "id": r.id, "username": r.username, "url": r.url,
                "play_count": r.play_count, "likes": r.likes, "comments": r.comments,
                "caption": (r.caption or "")[:240],
                "thumb": r.local_media_path or r.thumbnail_url,
                "video_url": r.video_url, "topic": r.topic,
                "analyzed": r.id in analyzed_ids, "analysis": an,
                "relevant": r.relevant, "reason": r.relevance_reason, "lang": r.lang,
                "media_type": r.media_type,
            })
        return out
