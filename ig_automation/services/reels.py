"""Многосценный Reels: на каждую сцену из reels_script — своя картинка (лицо бренда) →
короткий клип (Replicate image→video), русская озвучка narration (Replicate TTS) →
склейка и мукс через ffmpeg в вертикальный 1080×1920 mp4.

Тяжёлый процесс (~3-6 мин на 3-4 сцены) → запускается в ФОНОВОМ потоке (start_full_reels);
готовый ролик добавляется как PostAsset kind='video' по завершении."""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional

import requests

from .. import config, scenes
from . import brand, generator as gen
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

MAX_SCENES = 4
VW, VH = 1080, 1920
_lipsync_version: Optional[str] = None


def _public_url(p: Path) -> str:
    """Публичный URL файла из MEDIA_DIR (липсинк fal/Replicate скачивают по нему).
    ВАЖНО: сохраняем путь относительно MEDIA_DIR — файлы из подпапок (bloggers/,
    produced/…) при плоском `/media/{name}` отдавали 404, из-за чего липсинк молча
    не срабатывал и звук просто накладывался поверх (губы не попадали)."""
    p = Path(p)
    try:
        rel = p.resolve().relative_to(Path(config.MEDIA_DIR).resolve()).as_posix()
    except (ValueError, OSError):
        rel = p.name
    return f"{config.PUBLIC_BASE}/media/{rel}"


def _replicate_version_run(version: str, body: dict, poll_tries: int = 100, poll_every: int = 4) -> dict:
    """Запуск Replicate-модели по version-id (для не-official моделей, напр. latentsync)."""
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
    r = requests.post("https://api.replicate.com/v1/predictions", headers=h,
                      json={"version": version, "input": body}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"replicate HTTP {r.status_code}: {r.text[:200]}")
    pred = r.json()
    get = (pred.get("urls") or {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            return pred
        if st in ("failed", "canceled"):
            raise RuntimeError(f"replicate {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        for _a in range(3):
            try:
                pred = requests.get(get, headers=h, timeout=30).json()
                break
            except requests.RequestException:
                time.sleep(2)
    raise RuntimeError("replicate: таймаут lip-sync")


def _lipsync(video: Path, audio: Path, out_path: Path) -> Path:
    """Синхронизирует губы в video под audio. Основной движок — Sync Lipsync 2
    (fal): сохраняет зубы/черты лица, не «мылит» низ лица как latentsync. Фолбэк —
    latentsync (Replicate), чтобы пайплайн не падал при недоступности fal."""
    if config.FAL_KEY:
        try:
            return _lipsync_sync2(video, audio, out_path)
        except Exception as e:
            log.warning("sync-lipsync-2 упал (%s) — фолбэк на latentsync", e)
    return _lipsync_latentsync(video, audio, out_path)


def _lipsync_sync2(video: Path, audio: Path, out_path: Path) -> Path:
    """Sync Lipsync 2 через fal QUEUE API (синхронный fal.run на этой длинной модели
    отдаёт 504/422). Сохраняет зубы/черты лица. Результат тянем с fal.media
    (режется РКН → фолбэк через apify-actor)."""
    hdr = {"Authorization": f"Key {config.FAL_KEY}", "Content-Type": "application/json"}
    sub = requests.post("https://queue.fal.run/fal-ai/sync-lipsync/v2", headers=hdr,
                        json={"video_url": _public_url(video), "audio_url": _public_url(audio)},
                        timeout=60)
    sub.raise_for_status()
    j = sub.json()
    status_url, response_url = j["status_url"], j["response_url"]
    for _ in range(120):  # до ~10 мин
        time.sleep(5)
        st = requests.get(status_url, headers=hdr, timeout=30).json()
        s = st.get("status")
        if s == "COMPLETED":
            break
        if s in ("FAILED", "ERROR"):
            raise RuntimeError(f"sync-lipsync: {s} {str(st)[:200]}")
    else:
        raise RuntimeError("sync-lipsync: таймаут ожидания queue")
    res = requests.get(response_url, headers=hdr, timeout=60).json()
    v = res.get("video")
    url = v.get("url") if isinstance(v, dict) else v
    if not url:
        raise RuntimeError("sync-lipsync: пустой output")
    try:
        out_path.write_bytes(requests.get(url, timeout=180).content)
    except Exception:  # fal.media режется РКН с РФ-VPS
        from .. import apify
        data = apify.fetch_via_actor(url) or b""
        if not data:
            raise RuntimeError("sync-lipsync: не скачался результат")
        out_path.write_bytes(data)
    return out_path


def _lipsync_latentsync(video: Path, audio: Path, out_path: Path) -> Path:
    """Фолбэк-липсинк: bytedance/latentsync (Replicate). Слабее по лицу, но живой."""
    global _lipsync_version
    if _lipsync_version is None:
        h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}"}
        d = requests.get(f"https://api.replicate.com/v1/models/{config.LIPSYNC_MODEL}", headers=h, timeout=30).json()
        _lipsync_version = (d.get("latest_version") or {}).get("id")
        if not _lipsync_version:
            raise RuntimeError("lip-sync: не удалось получить version модели")
    pred = _replicate_version_run(_lipsync_version, {"video": _public_url(video), "audio": _public_url(audio)})
    out = pred.get("output")
    url = out if isinstance(out, str) else (out[0] if isinstance(out, list) and out else None)
    if not url:
        raise RuntimeError("lip-sync: пустой output")
    out_path.write_bytes(requests.get(url, timeout=180).content)
    return out_path


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg fail: {r.stderr[-400:]}")


def _ffprobe_dur(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _tts(text: str, out_path: Path) -> Optional[Path]:
    """Русская озвучка через Replicate (minimax). Возвращает путь к mp3 или None."""
    text = (text or "").strip()
    if not text:
        return None
    body = {"text": text[:4000], "language_boost": "Russian", "voice_id": config.TTS_VOICE,
            "speed": 1.08, "audio_format": "mp3"}
    pred = scenes._call_replicate(config.TTS_MODEL, body, poll_tries=50, poll_every=3)
    out = pred.get("output")
    url = out if isinstance(out, str) else (out[0] if isinstance(out, list) and out else
                                            out.get("audio") if isinstance(out, dict) else None)
    if not url:
        return None
    out_path.write_bytes(requests.get(url, timeout=120).content)
    return out_path


def _scene_clip(post_id: int, idx: int, visual: str, product: str) -> Path:
    """Картинка сцены (лицо бренда + раскадровка, без текста) → короткий клип."""
    refs = [brand.model_ref()]
    pr = brand.product_ref(product)
    if pr:
        refs.append(pr)
    scene = gen._clean_scene(visual) or "лайфстайл-кадр в фирменном стиле бренда"
    prompt = gen._visual_prompt(scene, product, with_product_ref=bool(pr))
    hero = scenes.generate_branded(prompt, refs=refs, ratio="9:16",
                                   out_name=f"reelscene_{post_id}_{idx}.png")
    hero_media = config.MEDIA_DIR / f"reelscene_{post_id}_{idx}.png"
    shutil.copy(hero, hero_media)  # в /media → Replicate скачает по URL (короткий POST)
    last: Optional[Exception] = None
    for attempt in range(3):  # video-модель Replicate периодически флакает — ретраим
        try:
            vid = scenes.generate_video(hero_media, prompt="natural cinematic motion, soft lighting",
                                        duration=5, aspect_ratio="9:16",
                                        out_name=f"reelclip_{post_id}_{idx}.mp4")
            return Path(vid)
        except Exception as e:
            last = e
            log.warning("reels: видео сцены %d, попытка %d/3: %s", idx, attempt + 1, e)
    raise last or RuntimeError("video gen failed")


def _scene_texts(script: dict, scenes_list: list) -> List[str]:
    """Озвучка ПО СЦЕНАМ: хук добавляем к первой, cta — к последней; каждая сцена в
    кадре держится ровно столько, сколько звучит её кусок."""
    out: List[str] = []
    last = len(scenes_list) - 1
    for i, sc in enumerate(scenes_list):
        t = (sc.get("voiceover") or sc.get("onscreen") or "").strip()
        if i == 0:
            t = (script.get("hook", "").strip() + " " + t).strip()
        if i == last:
            t = (t + " " + script.get("cta", "").strip()).strip()
        out.append(t or "…")
    return out


def _silence(dur: float, out_path: Path) -> Path:
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono",
          "-t", f"{max(0.5, dur):.2f}", "-c:a", "aac", "-b:a", "128k", str(out_path)])
    return out_path


def _seg_video(clip: Path, dur: float, out_path: Path) -> Path:
    """Нормализует клип в 1080×1920@30 и подгоняет его длину под `dur` (зацикливает
    движение, если клип короче), без звука."""
    cdur = _ffprobe_dur(clip)
    loop = ["-stream_loop", "-1"] if dur > cdur + 0.3 else []
    _run(["ffmpeg", "-y", *loop, "-i", str(clip), "-t", f"{max(0.5, dur):.2f}",
          "-vf", f"scale={VW}:{VH}:force_original_aspect_ratio=increase,crop={VW}:{VH},fps=30,setsar=1",
          "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(out_path)])
    return out_path


def _assemble_synced(segments: List[tuple], out: Path) -> None:
    """segments = [(clip, audio|None)]. Каждая сцена держится в кадре столько, сколько
    звучит её озвучка (нет аудио → берём длину клипа + тишина). Сцены сменяются в такт
    голосу. Склейка видео (concat copy) + склейка аудио (concat filter) + мукс."""
    seg_vids: List[Path] = []
    seg_auds: List[Path] = []
    tmp: List[Path] = []
    for i, (clip, audio) in enumerate(segments):
        if audio and audio.exists():
            dur = _ffprobe_dur(audio) or _ffprobe_dur(clip) or 5.0
            aud = audio
        else:
            dur = _ffprobe_dur(clip) or 5.0
            aud = _silence(dur, out.with_name(f"{out.stem}_sil{i}.m4a"))
            tmp.append(aud)
        seg = _seg_video(clip, dur, out.with_name(f"{out.stem}_seg{i}.mp4"))
        seg_vids.append(seg)
        seg_auds.append(aud)
        tmp.append(seg)

    # видео: concat demuxer (одинаковые параметры → copy, быстро)
    listf = out.with_name(out.stem + "_list.txt")
    listf.write_text("".join(f"file '{p.resolve()}'\n" for p in seg_vids))
    tmp.append(listf)
    vcat = out.with_name(out.stem + "_v.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(vcat)])
    tmp.append(vcat)

    # аудио: concat filter → aac
    ain: List[str] = []
    for a in seg_auds:
        ain += ["-i", str(a)]
    af = "".join(f"[{i}:a]" for i in range(len(seg_auds))) + f"concat=n={len(seg_auds)}:v=0:a=1[a]"
    acat = out.with_name(out.stem + "_a.m4a")
    _run(["ffmpeg", "-y", *ain, "-filter_complex", af, "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(acat)])
    tmp.append(acat)

    # мукс
    _run(["ffmpeg", "-y", "-i", str(vcat), "-i", str(acat), "-map", "0:v", "-map", "1:a",
          "-c", "copy", "-shortest", str(out)])
    for p in tmp:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def build_full_reels(post_id: int) -> Optional[int]:
    """Синхронная сборка (вызывать в фоне). Возвращает id видео-ассета."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product = post.product
        script = post.reels_script
        n = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "video").count()
        post.status = "generating"
    if not script:  # нет сценария — сгенерим
        gen.generate_reels_script(post_id)
        with session_scope() as s:
            script = s.get(Post, post_id).reels_script
    scenes_list = (script or {}).get("scenes", [])[:MAX_SCENES]
    if not scenes_list:
        raise RuntimeError("В сценарии нет сцен — сгенерируй сценарий Reels")
    if len((script or {}).get("scenes", [])) > MAX_SCENES:
        log.info("reels: сцен %d, беру первые %d", len(script["scenes"]), MAX_SCENES)

    texts = _scene_texts(script, scenes_list)
    segments: List[tuple] = []
    junk: List[Path] = []
    for i, sc in enumerate(scenes_list):
        try:  # упавшая сцена не должна убивать весь ролик — пропускаем её
            clip = _scene_clip(post_id, i, sc.get("visual", ""), product)
        except Exception as e:
            log.warning("reels: сцена %d не сгенерилась, пропускаю: %s", i, e)
            continue
        audio = None
        try:
            audio = _tts(texts[i], config.MEDIA_DIR / f"reelvo_{post_id}_{n}_{i}.mp3")
        except Exception as e:
            log.warning("reels TTS сцена %d не удалась (тишина): %s", i, e)
        if audio:
            # растягиваем клип под длину озвучки и в MEDIA_DIR (нужен публичный URL для lip-sync)
            dur = _ffprobe_dur(audio) or 5.0
            ext = _seg_video(clip, dur + 0.4, config.MEDIA_DIR / f"reelext_{post_id}_{n}_{i}.mp4")
            junk.append(ext)
            if config.LIPSYNC_MODEL:
                try:  # губы под озвучку; синк-видео уже со звуком, но переклеим тот же audio
                    synced = _lipsync(ext, audio, config.MEDIA_DIR / f"reelsync_{post_id}_{n}_{i}.mp4")
                    junk.append(synced)
                    segments.append((synced, audio))
                    continue
                except Exception as e:
                    log.warning("reels: lip-sync сцена %d не удалась, без синка: %s", i, e)
            segments.append((ext, audio))
        else:
            segments.append((clip, None))

    if not segments:
        raise RuntimeError("ни одна сцена не сгенерировалась (Replicate флакнул) — попробуй ещё раз")

    dest = config.MEDIA_DIR / f"reelfull_{post_id}_{n}.mp4"
    _assemble_synced(segments, dest)

    # подчистка промежуточных файлов сцены (оставляем только итоговый ролик)
    for p in junk:
        p.unlink(missing_ok=True)
    for pat in (f"reelvo_{post_id}_{n}_*.mp3", f"reelscene_{post_id}_*.png"):
        for f in config.MEDIA_DIR.glob(pat):
            f.unlink(missing_ok=True)

    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="video", path=f"/media/{dest.name}",
                      model="reels-full", prompt=" ".join(texts)[:300], ord=n)
        s.add(a)
        p = s.get(Post, post_id)
        if p and p.status == "generating":
            p.status = "review"
        s.flush()
        return a.id


def _bg(post_id: int) -> None:
    try:
        aid = build_full_reels(post_id)
        log.info("reels-full готов: post=%s asset=%s", post_id, aid)
    except Exception as e:
        log.warning("reels-full failed post=%s: %s", post_id, e)
        with session_scope() as s:
            p = s.get(Post, post_id)
            if p and p.status == "generating":
                p.status = "review"
                p.error = f"Reels: {e}"[:500]


def start_full_reels(post_id: int) -> None:
    """Запускает сборку в фоновом потоке (ответ возвращается сразу)."""
    threading.Thread(target=_bg, args=(post_id,), daemon=True).start()
