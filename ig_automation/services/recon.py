"""Стадия 0 — Разведка трендов: сбор вирусных Reels (Apify) + разбор хука (Claude)."""
from __future__ import annotations

import hashlib
import logging
import re
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


# ── Глубокий разбор (видео: кадры + транскрипт + vision) ──

class DeepHookOut(HookOut):
    visual_notes: str = Field(description="Визуальный стиль: цвет/свет/декорации/CGI-приёмы, что видно на кадрах")
    camera_work: str = Field(description="Работа камеры и монтаж: движения, ракурсы, ритм склеек (по кадрам)")


_DEEP_SYSTEM = _ANALYZE_SYSTEM + """
Тебе также дают КАДРЫ ролика по таймлайну (слева направо) и транскрипт речи (если есть).
Разбирай именно ВИЗУАЛ: композицию, свет, цвет, декорации, камеру, где продукт в кадре."""


# ── Pinterest ──

_PIN_URL_RE = re.compile(r"pinterest\.[a-z.]+/pin/(\d+)")


def _best_pin_image(url_564: str) -> str:
    """i.pinimg.com отдаёт разные размеры одним хэшем: пробуем originals → 736x → 564x."""
    for size in ("originals", "736x"):
        candidate = re.sub(r"/\d+x/", f"/{size}/", url_564, count=1)
        if candidate != url_564:
            try:
                r = requests.head(candidate, timeout=8)
                if r.status_code == 200:
                    return candidate
            except requests.RequestException:
                break
    return url_564


def _pin_by_url(url: str) -> Optional[dict]:
    """Pinterest-пин по ссылке (включая короткие pin.it) → норм-вид как у reel_by_url."""
    if "pin.it/" in url:
        try:
            url = requests.get(url, timeout=15, allow_redirects=True).url
        except requests.RequestException as e:
            log.warning("pin.it redirect failed: %s", e)
            return None
    m = _PIN_URL_RE.search(url)
    if not m:
        return None
    pin_id = m.group(1)
    try:
        r = requests.get(
            "https://widgets.pinterest.com/v3/pidgets/pins/info/",
            params={"pin_ids": pin_id}, timeout=15)
        r.raise_for_status()
        data = (r.json().get("data") or [None])[0] or {}
    except Exception as e:
        log.warning("pinterest widgets API failed for pin %s: %s", pin_id, e)
        return None
    if not data:
        return None
    images = data.get("images") or {}
    img = (images.get("564x") or images.get("236x") or {}).get("url", "")
    if img:
        img = _best_pin_image(img)

    def _vid_from(vlist: dict) -> str:
        """Из video_list берём лучший mp4, HLS — последним шансом."""
        best_mp4, hls = "", ""
        for v in (vlist or {}).values():
            u = (v or {}).get("url") or ""
            if u.endswith(".mp4"):
                if (v.get("width") or 0) >= 700 or not best_mp4:
                    best_mp4 = u
            elif ".m3u8" in u and not hls:
                hls = u
        return best_mp4 or hls

    video_url = _vid_from((data.get("videos") or {}).get("video_list") or {})
    if not video_url:  # idea-пин: видео лежит в страницах story_pin_data
        for page in ((data.get("story_pin_data") or {}).get("pages") or []):
            for block in (page.get("blocks") or []):
                video_url = _vid_from(((block.get("video") or {}).get("video_list")) or {})
                if video_url:
                    break
            if video_url:
                break
    if not img and not video_url:
        return None
    pinner = data.get("pinner") or {}
    board = data.get("board") or {}
    caption = " · ".join(x for x in (
        (data.get("description") or "").strip(),
        (data.get("attribution") or {}).get("title", "") if data.get("attribution") else "",
        f"доска: {board['name']}" if board.get("name") else "") if x)
    return {
        "url": f"https://www.pinterest.com/pin/{pin_id}/",
        "username": pinner.get("user_name") or pinner.get("full_name") or "",
        "play_count": 0,
        "likes": int((data.get("aggregated_pin_data") or {})
                     .get("aggregated_stats", {}).get("saves") or 0),
        "comments": 0,
        "caption": caption,
        "hashtags": [],
        "video_url": video_url,
        "thumbnail_url": img,
        "music_info": "",
        "media_type": "video" if video_url else "image",
        "images": [img] if (img and not video_url) else None,
        "topic": "pinterest",
    }


def add_reel_by_url(url: str) -> Optional[int]:
    """Ролик по прямой ссылке -> TrendReel (сразу качаем mp4, CDN-ссылки протухают).
    Pinterest-пины (pinterest.*/pin/…, pin.it/…) тоже принимаются — как image."""
    norm = _pin_by_url(url) if ("pinterest." in url or "pin.it/" in url) else apify.reel_by_url(url)
    if not norm:
        return None
    with session_scope() as s:
        row = s.query(TrendReel).filter(TrendReel.url == norm["url"]).first()
        if row:
            reel_id = row.id
        else:
            row = TrendReel(
                source_actor="manual-url", url=norm["url"], username=norm["username"],
                play_count=norm["play_count"], likes=norm["likes"], comments=norm["comments"],
                caption=norm["caption"], hashtags=norm["hashtags"], video_url=norm["video_url"],
                thumbnail_url=norm["thumbnail_url"], music_info=str(norm["music_info"])[:512],
                transcript=str(norm.get("transcript") or ""),
                topic=norm.get("topic") or "по ссылке",
                relevant=True, relevance_reason="добавлен вручную", lang="",
                media_type=norm.get("media_type", "video"),
                images=norm.get("images") or None,
            )
            s.add(row)
            s.flush()
            reel_id = row.id
    with session_scope() as s:
        mt = s.get(TrendReel, reel_id).media_type
    if mt == "video":
        _ensure_video(reel_id)
    else:
        _ensure_images(reel_id)
    return reel_id


def delete_reel(reel_id: int) -> bool:
    """Удаляет ролик разведки: разборы, кадры/видео на диске, запись."""
    import shutil
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        if not reel:
            return False
        local = reel.local_media_path
        for a in s.query(HookAnalysis).filter(HookAnalysis.trend_reel_id == reel_id).all():
            s.delete(a)
        s.delete(reel)
    try:
        shutil.rmtree(config.MEDIA_DIR / "frames" / str(reel_id), ignore_errors=True)
        if local:
            (config.DATA_DIR / local.lstrip("/")).unlink(missing_ok=True)
    except Exception as e:
        log.warning("delete_reel %s: медиа не подчистились: %s", reel_id, e)
    return True


def reel_topic(reel_id: int) -> str:
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        return reel.topic if reel else ""


def _ensure_video(reel_id: int) -> str:
    """Скачивает mp4 в data/media/reels/, пишет local_media_path. Возвращает fs-путь или ''."""
    dest_dir = config.MEDIA_DIR / "reels"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{reel_id}.mp4"
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        if not reel:
            return ""
        if dest.exists() and dest.stat().st_size > 0:
            reel.local_media_path = f"/media/reels/{reel_id}.mp4"
            return str(dest)
        vurl = reel.video_url
        page_url = reel.url
    if not vurl:
        norm = apify.reel_by_url(page_url) if page_url else None
        vurl = (norm or {}).get("video_url") or ""
    if not vurl:
        return ""
    if ".m3u8" in vurl:  # HLS (видео-пины Pinterest) — собираем ффмпегом
        import subprocess
        r = subprocess.run(["ffmpeg", "-y", "-i", vurl, "-c", "copy",
                            "-bsf:a", "aac_adtstoasc", str(dest)],
                           capture_output=True, timeout=600)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            with session_scope() as s:
                reel = s.get(TrendReel, reel_id)
                if reel:
                    reel.local_media_path = f"/media/reels/{reel_id}.mp4"
            return str(dest)
        log.warning("hls download fail: %s", r.stderr[-200:])
        return ""
    data = b""
    try:
        r = requests.get(vurl, timeout=(10, 300))
        r.raise_for_status()
        data = r.content
    except Exception as e:  # CDN недоступен (РКН на VPS) или протух
        log.warning("direct video dl fail (%s) — пробую media-fetcher", e)
        data = apify.fetch_via_actor(vurl) or b""
        if not data and page_url:  # ссылка протухла — перечитать и снова через актор
            norm = apify.reel_by_url(page_url)
            vurl2 = (norm or {}).get("video_url") or ""
            if vurl2:
                data = apify.fetch_via_actor(vurl2) or b""
    if not data:
        return ""
    dest.write_bytes(data)
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        reel.local_media_path = f"/media/reels/{reel_id}.mp4"
    return str(dest)


def _extract_frames(reel_id: int, video_path: str, n: int = 9) -> list:
    """N кадров по таймлайну -> data/media/frames/<id>/f*.jpg. Возвращает fs-пути."""
    import subprocess
    fdir = config.MEDIA_DIR / "frames" / str(reel_id)
    fdir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video_path], capture_output=True, text=True)
    dur = float(probe.stdout or 10)
    out = []
    for i in range(n):
        f = fdir / f"f{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(round(dur * i / n, 2)), "-i", video_path,
             "-frames:v", "1", "-vf", "scale=400:-1", str(f)],
            capture_output=True)
        if f.exists():
            out.append(str(f))
    return out


def _transcribe(video_path: str) -> str:
    """Транскрипт: OpenAI Whisper -> ElevenLabs Scribe fallback. '' если речи нет/сбой."""
    import subprocess, tempfile, os as _os
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3 = tmp.name
    try:
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec",
                        "libmp3lame", "-q:a", "5", mp3], capture_output=True)
        text = ""
        if config.OPENAI_API_KEY:
            try:
                r = requests.post(
                    config.OPENAI_AUDIO_URL,
                    headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                    files={"file": ("a.mp3", open(mp3, "rb"), "audio/mpeg")},
                    data={"model": "whisper-1", "response_format": "text"}, timeout=180)
                if r.ok:
                    text = r.text.strip()
            except Exception as e:
                log.warning("whisper fail: %s", e)
        if not text:
            key = _os.getenv("ELEVENLABS_API_KEY", "")
            if key:
                try:
                    r = requests.post(
                        "https://api.elevenlabs.io/v1/speech-to-text",
                        headers={"xi-api-key": key},
                        files={"file": ("a.mp3", open(mp3, "rb"), "audio/mpeg")},
                        data={"model_id": "scribe_v1"}, timeout=180)
                    if r.ok and r.headers.get("content-type", "").startswith("application/json"):
                        text = (r.json().get("text") or "").strip()
                except Exception as e:
                    log.warning("scribe fail: %s", e)
        # частые галлюцинации на чистой музыке
        if text.lower().strip(" .!") in ("thank you for watching", "thanks for watching",
                                         "спасибо за просмотр", "субтитры делал dimatorzok"):
            text = ""
        return text
    finally:
        try:
            _os.unlink(mp3)
        except OSError:
            pass


def deep_analyze(reel_id: int) -> Optional[int]:
    """Глубокий разбор: видео (кадры+транскрипт) или карусель/картинка (слайды)."""
    import base64
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        _mt = (s.get(TrendReel, reel_id).media_type or "video")
    if _mt in ("carousel", "image"):
        return deep_analyze_images(reel_id)
    video = _ensure_video(reel_id)
    if not video:
        log.warning("deep_analyze %s: видео недоступно", reel_id)
        return None
    frames = _extract_frames(reel_id, video)
    transcript = _transcribe(video)
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        if transcript:
            reel.transcript = transcript
        info = (
            f"Просмотры: {reel.play_count}, лайки: {reel.likes}, комментарии: {reel.comments}\n"
            f"Музыка: {reel.music_info or '—'}\n"
            f"Текст поста: {reel.caption or '—'}\n"
            f"Транскрипт речи: {transcript or '— (только музыка)'}"
        )
    content = []
    for i, f in enumerate(frames):
        content.append({"type": "text", "text": f"Кадр {i + 1}/{len(frames)}:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(open(f, "rb").read()).decode()}})
    content.append({"type": "text", "text": f"Данные ролика:\n{info}\n\nРазбери по схеме."})
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=4000, system=_DEEP_SYSTEM,
        messages=[{"role": "user", "content": content}], output_format=DeepHookOut)
    out = resp.parsed_output
    with session_scope() as s:
        row = HookAnalysis(
            trend_reel_id=reel_id, hook=out.hook, retention_device=out.retention_device,
            trigger=out.trigger, structure=out.structure, why_viral=out.why_viral,
            adapted_idea=out.adapted_idea, visual_notes=out.visual_notes,
            camera_work=out.camera_work, is_deep=True)
        s.add(row)
        s.flush()
        return row.id


def add_uploaded_video(data: bytes, filename: str = "") -> Optional[int]:
    """Загруженный пользователем файл -> TrendReel + сохранение в media/reels."""
    import time
    with session_scope() as s:
        row = TrendReel(
            source_actor="upload", url="", username="(файл)",
            caption=filename or "загруженное видео", topic="загрузка",
            relevant=True, relevance_reason="загружен вручную", media_type="video",
        )
        s.add(row)
        s.flush()
        reel_id = row.id
    dest_dir = config.MEDIA_DIR / "reels"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"{reel_id}.mp4").write_bytes(data)
    with session_scope() as s:
        s.get(TrendReel, reel_id).local_media_path = f"/media/reels/{reel_id}.mp4"
    return reel_id


# ── «Сделать похожий»: storyboard под наш продукт по механике референса ──

class SceneOut(BaseModel):
    n: int = Field(description="Номер сцены по порядку")
    slide_title: str = Field(default="", description="Для КАРУСЕЛИ: короткая надпись на слайд (2-4 слова, про НАШ продукт/выгоду; наложим фирменным шаблоном программно). Для видео — пусто")
    scene: str = Field(description="Что в кадре: композиция, продукт, окружение, свет (конкретно, для генерации)")
    camera: str = Field(description="ОДНО движение камеры на сцену (проезд/облёт/кран/push-in/статика) и ракурс")
    vo: str = Field(description="Закадровый текст на эту сцену (рус., может быть пустым)")
    duration_s: float = Field(description="Длительность сцены в секундах (2-6)")


class StoryboardOut(BaseModel):
    title: str = Field(description="Короткое название ролика")
    concept: str = Field(description="Концепция в 1-2 предложениях: какую механику референса переносим и как")
    scenes: List[SceneOut] = Field(description="5-7 сцен")
    vo_full: str = Field(description="Полный закадровый текст целиком (или пометка 'без голоса, только музыка')")
    music_hint: str = Field(description="Какая музыка/настроение трека")


_SIMILAR_SYSTEM = """Ты — режиссёр коротких рекламных роликов и арт-директор бренда БАД POWERELIX (RU).
Если формат референса — carousel/image: собери вместо ролика КАРУСЕЛЬ. Главное — ПЕРЕНЕСТИ
КРЕАТИВНЫЙ ВИЗУАЛЬНЫЙ ХОД референса (трансформация предмета, неожиданный контекст, стиль
съёмки, палитра — то, что делает его вирусным), а не «продукт на фоне». Для каждого слайда:
scene — детальное описание ВИЗУАЛА (композиция, свет, сюрреальный/креативный приём) БЕЗ
какого-либо текста на изображении; camera — принцип композиции/вёрстки; vo — строка для
ТЕКСТА ПОСТА (подпись, НЕ на картинку); slide_title — короткая надпись слайда (2-4 слова,
наш продукт/выгода) для программного фирменного оверлея; duration_s = 0.
Сам Gemini текст НЕ рисует — надпись накладываем шаблоном бренда.
Иначе:
Тебе дают ГЛУБОКИЙ РАЗБОР чужого вирусного ролика (хук, структура, визуальный мир, камера)
и НАШ ПРОДУКТ. Собери storyboard НАШЕГО ролика по той же МЕХАНИКЕ (не копия: другой продукт,
свой фирменный цвет/мир, та же драматургия и приёмы камеры).
Правила: 9:16, 15-25 сек суммарно; КАЖДАЯ СЦЕНА РОВНО 5 СЕКУНД (duration_s=5) —
видео-движки генерят клипы по 5 сек, поэтому сцен должно быть 3-5 (длительность
референса / 5, округлить), НЕ БОЛЬШЕ ПЯТИ; в каждой сцене ОДНО движение камеры; физика реалистична
(жидкости падают вниз, конденсат стекает по бутылке); продукт с читаемой этикеткой; юр-правила
рекламы БАД РФ — без «лечит», только «поддерживает/способствует»; финальная сцена — пэк-шот
с местом под текст и артикул. Если в референсе нет голоса — можно без VO (укажи это)."""


def make_similar(analysis_id: int, product_id: str) -> Optional[int]:
    """Storyboard нашего ролика по механике разобранного референса."""
    from .catalog import link_line
    from .. import products as products_mod
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        a = s.get(HookAnalysis, analysis_id)
        if not a:
            return None
        reel = s.get(TrendReel, a.trend_reel_id)
        ref = (
            f"Хук: {a.hook}\nУдержание: {a.retention_device}\nТриггер: {a.trigger}\n"
            f"Структура: {a.structure}\nПочему зашло: {a.why_viral}\n"
            f"Визуальный мир: {a.visual_notes or '—'}\nКамера/монтаж: {a.camera_work or '—'}\n"
            f"Транскрипт референса: {(reel.transcript if reel else '') or '— (без речи)'}\n"
            f"Формат референса: {(reel.media_type if reel else 'video') or 'video'}"
        )
        reel_id = a.trend_reel_id
    brand = products_mod.load_brand()
    prod = next((p for p in brand["products"] if str(p["id"]) == str(product_id)), None)
    if not prod:
        return None
    pinfo = (
        f"Продукт: {prod['name']}\nФорма: {prod.get('form','')}\n"
        f"Пользы: {', '.join(prod.get('benefits', [])[:4])}\n"
        f"Слоган: {prod.get('slogan','')}\nФирменный цвет: {prod.get('accent_color','')}\n"
        f"Где купить (для пэк-шота): {link_line(str(product_id)) or 'WB'}"
    )
    # для каруселей/картинок показываем Claude САМИ слайды референса
    import base64 as _b64
    content = []
    frames_dir = config.MEDIA_DIR / "frames" / str(reel_id)
    frame_files = sorted(frames_dir.glob("f*.jpg")) if frames_dir.exists() else []
    if frame_files:
        for i, f in enumerate(frame_files):
            content.append({"type": "text", "text": f"Слайд референса {i + 1}/{len(frame_files)}:"})
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": _b64.b64encode(f.read_bytes()).decode()}})
    is_video = (reel.media_type if reel else "video") not in ("carousel", "image")
    content.append({"type": "text", "text":
                    f"РАЗБОР РЕФЕРЕНСА:\n{ref}\n\nНАШ ПРОДУКТ:\n{pinfo}\n\n"
                    + (("Кадры выше — таймлайн референса для контекста. ВАЖНО: сцен НЕ по числу "
                        "кадров, а по хронометражу — каждая сцена 5 секунд, всего 3-5 сцен "
                        "(длительность референса / 5). Каждая сцена = ключевой момент механики. "
                        if is_video else
                        "ВАЖНО: сцен ровно столько, сколько слайдов выше; сцена N — ТОЧНОЕ "
                        "описание слайда N (та же композиция и действие, например «банку кладут "
                        "в сумку»), только продукт заменён на наш. ") if frame_files else "")
                    + "Собери storyboard."})
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=4000, system=_SIMILAR_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_format=StoryboardOut)
    out = resp.parsed_output
    from ..db.models import Storyboard
    with session_scope() as s:
        row = Storyboard(
            hook_analysis_id=analysis_id, trend_reel_id=reel_id,
            product_id=str(product_id), product_name=prod["name"],
            title=out.title, concept=out.concept,
            scenes=[sc.model_dump() for sc in out.scenes],
            vo_full=out.vo_full, music_hint=out.music_hint)
        s.add(row)
        s.flush()
        return row.id


def _fetch_bytes(url: str) -> bytes:
    """Скачивание с фолбэком на media-fetcher (РКН на VPS)."""
    try:
        r = requests.get(url, timeout=(10, 120))
        r.raise_for_status()
        return r.content
    except Exception:
        return apify.fetch_via_actor(url) or b""


def _ensure_images(reel_id: int) -> list:
    """Слайды карусели/поста -> data/media/frames/<id>/f*.jpg (UI их уже показывает)."""
    fdir = config.MEDIA_DIR / "frames" / str(reel_id)
    fdir.mkdir(parents=True, exist_ok=True)
    existing = sorted(fdir.glob("f*.jpg"))
    if existing:
        return [str(x) for x in existing]
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        urls = list(reel.images or [])
        page_url = reel.url
    if not urls and page_url:  # ссылки протухли — перечитать
        norm = apify.reel_by_url(page_url)
        urls = (norm or {}).get("images") or []
    out = []
    for i, u in enumerate(urls[:10]):
        data = _fetch_bytes(u)
        if data:
            f = fdir / f"f{i}.jpg"
            f.write_bytes(data)
            out.append(str(f))
    return out


_DEEP_IMAGE_SYSTEM = _ANALYZE_SYSTEM + """
Это КАРУСЕЛЬ/ПОСТ-КАРТИНКА (не видео). Тебе дают слайды по порядку. Разбирай:
хук-слайд (почему останавливает скролл), логику последовательности слайдов,
дизайн (шрифты, цвета, сетка, как свёрстан текст), где CTA. В поле structure —
послайдовая структура (слайд 1 → 2 → …), в camera_work — принципы вёрстки/дизайна."""


def deep_analyze_images(reel_id: int) -> Optional[int]:
    """Глубокий разбор карусели/картинки: слайды -> Claude vision."""
    import base64
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    slides = _ensure_images(reel_id)
    if not slides:
        return None
    with session_scope() as s:
        reel = s.get(TrendReel, reel_id)
        info = (
            f"Формат: {reel.media_type}, слайдов: {len(slides)}\n"
            f"Лайки: {reel.likes}, комментарии: {reel.comments}\n"
            f"Текст поста: {reel.caption or '—'}"
        )
    content = []
    for i, f in enumerate(slides):
        content.append({"type": "text", "text": f"Слайд {i + 1}/{len(slides)}:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.b64encode(open(f, "rb").read()).decode()}})
    content.append({"type": "text", "text": f"Данные поста:\n{info}\n\nРазбери по схеме."})
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=4000, system=_DEEP_IMAGE_SYSTEM,
        messages=[{"role": "user", "content": content}], output_format=DeepHookOut)
    out = resp.parsed_output
    with session_scope() as s:
        row = HookAnalysis(
            trend_reel_id=reel_id, hook=out.hook, retention_device=out.retention_device,
            trigger=out.trigger, structure=out.structure, why_viral=out.why_viral,
            adapted_idea=out.adapted_idea, visual_notes=out.visual_notes,
            camera_work=out.camera_work, is_deep=True)
        s.add(row)
        s.flush()
        return row.id


def storyboard_to_post(sb_id: int, selected: Optional[List[int]] = None) -> Optional[int]:
    """Готовый storyboard (со слайдами) -> Пост: подпись про продукт + артикул + ассеты."""
    from .catalog import link_line
    from .. import products as products_mod
    from ..db.models import Storyboard, Post, PostAsset

    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if not sb or not (sb.output_paths or sb.output_video):
            return None
        scenes = list(sb.scenes or [])
        sb_data = {"product_id": sb.product_id, "product_name": sb.product_name,
                   "title": sb.title, "concept": sb.concept,
                   "outputs": [x for i, x in enumerate(sb.output_paths or [])
                               if selected is None or i in selected],
                   "video": sb.output_video or "", "vo_full": sb.vo_full}

    brand = products_mod.load_brand()
    prod = next((p for p in brand["products"]
                 if str(p["id"]) == str(sb_data["product_id"])), {})

    class CaptionOut(BaseModel):
        caption: str = Field(description="Подпись к посту: живой полезный текст про продукт (почему/кому/как принимать), на «ты», с эмодзи и абзацами, 500-900 знаков, БЕЗ хэштегов")
        hashtags: List[str] = Field(description="8-12 релевантных русских хэштегов без #")

    vo_lines = "\n".join(f"- {sc.get('vo','')}" for sc in scenes if sc.get("vo"))
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=2000,
        system="""Ты — SMM-копирайтер бренда БАД POWERELIX (РФ). Пишешь подпись к карусели/ролику.
ЖЁСТКО: БАД — не лекарство; нельзя «лечит/вылечивает/гарантирует»; только «поддерживает/способствует».
Структура: цепляющий первый абзац -> польза и кому подходит -> как принимать -> мягкий CTA.""",
        messages=[{"role": "user", "content":
                   f"Продукт: {prod.get('name')}\nФорма: {prod.get('form','')}\n"
                   f"Пользы: {', '.join(prod.get('benefits', [])[:5])}\n"
                   f"Слоган: {prod.get('slogan','')}\n"
                   f"Концепция поста: {sb_data['concept']}\n"
                   f"Строки со слайдов:\n{vo_lines}\n\nНапиши подпись."}],
        output_format=CaptionOut)
    out = resp.parsed_output
    from .catalog import get_link
    lk = get_link(str(sb_data["product_id"])) or {}
    nm = (lk.get("nmid") or "").strip()
    caption = out.caption.strip()
    if nm:
        # без URL (в IG не кликается), артикул хэштегом — тап открывает поиск
        caption += f"\n\n✅ Артикул на Wildberries: #{nm}"
    caption += "\n\nБАД. Не является лекарственным средством. Есть противопоказания."

    with session_scope() as s:
        post = Post(
            format="carousel" if sb_data["outputs"] and not sb_data["video"] else "reels",
            product=sb_data["product_name"], product_id=str(sb_data["product_id"]),
            hook=sb_data["title"], caption=caption, hashtags=out.hashtags,
            visual_idea=sb_data["concept"], status="review",
            cta="ссылка и артикул в подписи")
        s.add(post)
        s.flush()
        pid = post.id
        if sb_data["video"]:
            s.add(PostAsset(post_id=pid, kind="video", path=sb_data["video"],
                            model="producer", ord=0))
        for i, ap in enumerate(sb_data["outputs"]):
            s.add(PostAsset(post_id=pid, kind="image", path=ap, model="producer", ord=i))
    return pid
