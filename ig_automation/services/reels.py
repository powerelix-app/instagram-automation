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
            "speed": 1.0, "audio_format": "mp3"}
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
    vid = scenes.generate_video(hero_media, prompt="natural cinematic motion, soft lighting",
                                duration=5, aspect_ratio="9:16",
                                out_name=f"reelclip_{post_id}_{idx}.mp4")
    return Path(vid)


def _narration(script: dict, scenes_list: list) -> str:
    """Текст озвучки: хук + voiceover ТОЛЬКО используемых сцен + cta (иначе озвучка
    окажется длиннее видео и хвост застынет)."""
    parts = [script.get("hook", "")]
    for sc in scenes_list:
        parts.append(sc.get("voiceover") or sc.get("onscreen") or "")
    parts.append(script.get("cta", ""))
    return " ".join(p.strip() for p in parts if p and p.strip())


def _assemble(clips: List[Path], audio: Optional[Path], out: Path) -> None:
    """Нормализует клипы в 1080×1920@30, склеивает; добивает видео до длины озвучки
    (заморозкой последнего кадра) и муксует звук."""
    # 1) склейка с нормализацией
    inputs: List[str] = []
    filt = []
    for i, c in enumerate(clips):
        inputs += ["-i", str(c)]
        filt.append(f"[{i}:v]scale={VW}:{VH}:force_original_aspect_ratio=increase,"
                    f"crop={VW}:{VH},fps=30,setsar=1[v{i}]")
    concat = "".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[outv]"
    tmp_concat = out.with_name(out.stem + "_concat.mp4")
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt) + ";" + concat,
          "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(tmp_concat)])

    if not audio or not audio.exists():
        shutil.move(str(tmp_concat), str(out))
        return
    # 2) подгон под озвучку + мукс. Если озвучка длиннее видео — ЗАЦИКЛИВАЕМ видео под
    # неё (сцены продолжают двигаться), а не морозим последний кадр.
    vdur, adur = _ffprobe_dur(tmp_concat), _ffprobe_dur(audio)
    target = max(vdur, adur)
    loop = ["-stream_loop", "-1"] if adur > vdur + 0.3 else []
    _run(["ffmpeg", "-y", *loop, "-i", str(tmp_concat), "-i", str(audio),
          "-map", "0:v", "-map", "1:a", "-t", f"{target:.2f}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(out)])
    tmp_concat.unlink(missing_ok=True)


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

    clips: List[Path] = []
    for i, sc in enumerate(scenes_list):
        clips.append(_scene_clip(post_id, i, sc.get("visual", ""), product))

    narration = _narration(script, scenes_list)
    audio = None
    try:
        audio = _tts(narration, config.MEDIA_DIR / f"reelvo_{post_id}_{n}.mp3")
    except Exception as e:
        log.warning("reels TTS failed (соберу без озвучки): %s", e)

    dest = config.MEDIA_DIR / f"reelfull_{post_id}_{n}.mp4"
    _assemble(clips, audio, dest)

    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="video", path=f"/media/{dest.name}",
                      model="reels-full", prompt=narration[:300], ord=n)
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
