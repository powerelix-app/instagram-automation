"""Производство контента из одобренного storyboard: слайды (ProxyAPI) и ролики (fal).

Фоновые задачи (threading) со статусом в Storyboard.gen_status.
Гео-обходы для РФ-VPS: ElevenLabs — через media-fetcher (Apify, POST-прокси).
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from .. import config
from ..db.base import session_scope
from ..db.models import Storyboard

log = logging.getLogger(__name__)

PROXY_KEY = config.ANTHROPIC_API_KEY  # ProxyAPI: единый ключ на Google/OpenAI/Anthropic
IMG_MODEL = "gemini-3.1-flash-image"
FAL_I2V = "fal-ai/kling-video/v3/standard/image-to-video"
NASTYA_VOICE = "YjESejviApN7SHrbfnA2"


def _out_dir(sb_id: int) -> Path:
    d = config.MEDIA_DIR / "produced" / str(sb_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _product_ref(product_id: str) -> Optional[Path]:
    for ext in ("jpg", "png", "jpeg"):
        p = config.DATA_DIR / "product_refs" / f"{product_id}.{ext}"
        if p.exists():
            return p
    return _fetch_wb_photo(product_id)


def _fetch_wb_photo(product_id: str) -> Optional[Path]:
    """Автозагрузка фото товара из карточки WB (по wb_url из каталога)."""
    import re
    from .catalog import get_link
    link = get_link(str(product_id)) or {}
    m = re.search(r"(\d{7,})", link.get("wb_url") or "")
    if not m:
        return None
    nm = int(m.group(1))
    vol, part = nm // 100000, nm // 1000
    dest_dir = config.DATA_DIR / "product_refs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 31):  # перебор basket-хостов WB
        url = (f"https://basket-{i:02d}.wbbasket.ru/vol{vol}/part{part}/{nm}"
               f"/images/big/1.webp")
        try:
            r = requests.get(url, timeout=8)
            if r.ok and len(r.content) > 10000:
                webp = dest_dir / f"_{product_id}.webp"
                webp.write_bytes(r.content)
                jpg = dest_dir / f"{product_id}.jpg"
                subprocess.run(["ffmpeg", "-y", "-i", str(webp), str(jpg)],
                               capture_output=True, timeout=30)
                webp.unlink(missing_ok=True)
                if jpg.exists():
                    log.info("WB-фото товара %s скачано (nm=%s, basket-%02d)", product_id, nm, i)
                    return jpg
        except Exception:
            continue
    return None


def _set(sb_id: int, **kw):
    with session_scope() as s:
        row = s.get(Storyboard, sb_id)
        for k, v in kw.items():
            setattr(row, k, v)


# ── примитивы ──

def gen_image(prompt: str, ref: Optional[Path] = None, aspect: str = "9:16",
              style_suffix: str = "Photorealistic, raw photo, no glossy CGI look, film grain.",
              refs: Optional[list] = None) -> bytes:
    """Картинка через ProxyAPI gemini flash-image (1+ референсов — опционально)."""
    parts = []
    for rp in (refs or ([ref] if ref else [])):
        rp = Path(rp)
        parts.append({"inline_data": {
            "mime_type": "image/png" if rp.suffix == ".png" else "image/jpeg",
            "data": base64.b64encode(rp.read_bytes()).decode()}})
    parts.append({"text": prompt + f"\nAspect ratio {aspect}. {style_suffix} "
                  "If a product bottle is present keep the label crisp and identical "
                  "to the reference. No watermark."})
    r = requests.post(
        f"https://api.proxyapi.ru/google/v1beta/models/{IMG_MODEL}:generateContent",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
        json={"contents": [{"parts": parts}],
              "generationConfig": {"responseModalities": ["IMAGE"]}},
        timeout=300)
    r.raise_for_status()
    for p in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            return base64.b64decode(p["inlineData"]["data"])
    raise RuntimeError("gemini не вернул картинку")


def fal_i2v(image: bytes, prompt: str, duration: int = 5) -> bytes:
    """Анимация кадра через fal (Kling v3 i2v). Вход — байты стилла."""
    data_uri = "data:image/png;base64," + base64.b64encode(image).decode()
    r = requests.post(
        f"https://queue.fal.run/{FAL_I2V}",
        headers={"Authorization": f"Key {config.FAL_KEY}",
                 "Content-Type": "application/json"},
        json={"image_url": data_uri, "prompt": prompt,
              "duration": "10" if duration > 7 else "5", "sound": False},
        timeout=60)
    r.raise_for_status()
    req = r.json()
    status_url = req.get("status_url") or f"https://queue.fal.run/{FAL_I2V}/requests/{req['request_id']}/status"
    resp_url = req.get("response_url") or f"https://queue.fal.run/{FAL_I2V}/requests/{req['request_id']}"
    for _ in range(120):  # до ~10 мин
        time.sleep(5)
        st = requests.get(status_url, headers={"Authorization": f"Key {config.FAL_KEY}"}, timeout=30).json()
        if st.get("status") == "COMPLETED":
            break
        if st.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal failed: {st}")
    out = requests.get(resp_url, headers={"Authorization": f"Key {config.FAL_KEY}"}, timeout=60).json()
    vurl = (out.get("video") or {}).get("url") or ""
    if not vurl:
        raise RuntimeError(f"fal: нет video.url в ответе: {str(out)[:200]}")
    try:
        return requests.get(vurl, timeout=(10, 300)).content
    except Exception as e:  # fal.media CDN режется с РФ-VPS — качаем через актор
        log.warning("fal cdn fail (%s) — через media-fetcher", e)
        from .. import apify
        data = apify.fetch_via_actor(vurl)
        if not data:
            raise RuntimeError("fal cdn недоступен и через прокси")
        return data


def _eleven_post(path: str, payload: dict) -> bytes:
    """POST к ElevenLabs: напрямую, при гео-блоке — через Apify media-fetcher."""
    key = config.ELEVENLABS_API_KEY
    url = f"https://api.elevenlabs.io{path}"
    try:
        r = requests.post(url, headers={"xi-api-key": key, "Content-Type": "application/json"},
                          json=payload, timeout=180)
        if r.ok and r.headers.get("content-type", "").startswith("audio"):
            return r.content
        raise RuntimeError(f"direct {r.status_code}")
    except Exception as e:
        log.warning("elevenlabs direct fail (%s) — через media-fetcher", e)
        from .. import apify
        items = apify._run_actor(apify.FETCHER_ACTOR, {
            "url": url, "method": "POST",
            "headers": {"xi-api-key": key, "Content-Type": "application/json"},
            "body_b64": base64.b64encode(json.dumps(payload).encode()).decode(),
        }, max_charge_usd=0.05, timeout=240)
        for it in items:
            if it.get("ok") and it.get("downloadUrl"):
                return requests.get(it["downloadUrl"], params={"token": config.APIFY_TOKEN}, timeout=120).content
        raise RuntimeError("elevenlabs недоступен и через прокси")


def tts_nastya(text: str) -> bytes:
    return _eleven_post(f"/v1/text-to-speech/{NASTYA_VOICE}", {
        "text": text, "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.75, "similarity_boost": 0.25,
                           "style": 0.0, "use_speaker_boost": True}})


def gen_music(prompt: str, ms: int) -> bytes:
    return _eleven_post("/v1/music", {"prompt": prompt, "music_length_ms": min(ms, 60000)})


# ── производство ──

def _produce_slides(sb_id: int):
    """Карусель: берём ОРИГИНАЛЬНЫЕ слайды референса и пересоздаём каждый с нашим
    продуктом (image-to-image: слайд-референс + банка). Сцены storyboard — доп. контекст."""
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        scenes = list(sb.scenes or [])
        product_id, reel_id = sb.product_id, sb.trend_reel_id
    bottle = _product_ref(product_id)
    if not bottle:
        _set(sb_id, gen_status="error",
             gen_error="Нет фото продукта: проверь ссылку WB в /catalog "
                       "или положи фото в data/product_refs/<id>.jpg")
        return
    out = _out_dir(sb_id)
    # оригинальные слайды референса (скачаны при глубоком разборе)
    ref_dir = config.MEDIA_DIR / "frames" / str(reel_id)
    ref_slides = sorted(ref_dir.glob("f*.jpg")) if ref_dir.exists() else []
    paths = []
    if ref_slides:
        for i, rs in enumerate(ref_slides):
            _set(sb_id, gen_status=f"слайд {i + 1}/{len(ref_slides)} (по референсу)…")
            hint = scenes[i].get("scene", "") if i < len(scenes) else ""
            prompt = (
                "ПЕРВОЕ изображение — референсный слайд. Пересоздай его МАКСИМАЛЬНО похоже: "
                "та же композиция, ракурс, свет, стиль, креативный приём и настроение. "
                "НО: ЛЮБОЙ продукт/упаковку в кадре замени на НАШ продукт со ВТОРОГО "
                "изображения — форма банки, крышка, цвет и этикетка СТРОГО как на втором "
                "изображении, этикетка чёткая и читаемая. ЗАПРЕЩЕНО придумывать другую "
                "упаковку или оставлять продукт из референса. Цветовую гамму сцены адаптируй "
                "под фирменный цвет нашего продукта.\n"
                + (f"Контекст слайда: {hint}\n" if hint else "")
                + "СТРОГО: никакого текста, букв или надписей на изображении, "
                "кроме этикетки нашего продукта.")
            img = gen_image(prompt, refs=[rs, bottle] if bottle else [rs],
                            aspect="4:5", style_suffix="")
            p = out / f"slide_{i}.png"
            p.write_bytes(img)
            paths.append(f"/media/produced/{sb_id}/slide_{i}.png")
    else:  # фолбэк: по описаниям сцен
        for i, sc in enumerate(scenes):
            _set(sb_id, gen_status=f"слайд {i + 1}/{len(scenes)}…")
            prompt = (f"Слайд {i + 1} Instagram-карусели.\nВИЗУАЛ: {sc.get('scene', '')}\n"
                      f"Композиция: {sc.get('camera', '')}\n"
                      "СТРОГО: без текста и надписей (кроме этикетки продукта).")
            img = gen_image(prompt, ref=bottle, aspect="4:5", style_suffix="")
            p = out / f"slide_{i}.png"
            p.write_bytes(img)
            paths.append(f"/media/produced/{sb_id}/slide_{i}.png")
    _set(sb_id, gen_status="done", output_paths=paths)


def _produce_video(sb_id: int):
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        scenes = list(sb.scenes or [])
        product_id, vo_full, music_hint = sb.product_id, sb.vo_full, sb.music_hint
    ref = _product_ref(product_id)
    out = _out_dir(sb_id)
    clips = []
    for i, sc in enumerate(scenes):
        cp_done = out / f"clip_{i}.mp4"
        if cp_done.exists() and cp_done.stat().st_size > 0:
            clips.append(cp_done)
            continue
        _set(sb_id, gen_status=f"сцена {i + 1}/{len(scenes)}: стилл…")
        still = gen_image(f"Кадр рекламного ролика.\n{sc.get('scene', '')}", ref=ref)
        (out / f"still_{i}.png").write_bytes(still)
        _set(sb_id, gen_status=f"сцена {i + 1}/{len(scenes)}: анимация (fal)…")
        dur = int(float(sc.get("duration_s") or 4)) or 4
        clip = fal_i2v(still, f"{sc.get('camera', 'slow gentle camera move')}. "
                       f"{sc.get('scene', '')}. Single continuous shot, no cuts, "
                       "photorealistic, natural physics, movements natural not robotic.",
                       duration=dur)
        cp = out / f"clip_{i}.mp4"
        cp.write_bytes(clip)
        clips.append(cp)
    # склейка
    _set(sb_id, gen_status="сборка: склейка…")
    inputs, fparts = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", str(c)]
        fparts.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                      f"crop=1080:1920,setsar=1,fps=30[v{i}];")
    concat = "".join(f"[v{i}]" for i in range(len(clips)))
    silent = out / "_silent.mp4"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex",
                    "".join(fparts) + f"{concat}concat=n={len(clips)}:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                    "-pix_fmt", "yuv420p", str(silent)], capture_output=True, timeout=600)
    dur_s = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", str(silent)],
                                 capture_output=True, text=True).stdout or 20)
    # голос + музыка
    audio_in, amaps = [], []
    no_vo = (not vo_full) or ("без голоса" in vo_full.lower())
    if not no_vo:
        _set(sb_id, gen_status="озвучка (Настя)…")
        (out / "vo.mp3").write_bytes(tts_nastya(vo_full))
    _set(sb_id, gen_status="музыка…")
    try:
        (out / "music.mp3").write_bytes(gen_music(
            music_hint or "modern uplifting ad background, instrumental", int(dur_s * 1000)))
    except Exception as e:
        log.warning("music fail: %s", e)
    final = out / "final.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(silent)]
    fc, amix = [], []
    idx = 1
    if (out / "vo.mp3").exists():
        cmd += ["-i", str(out / 'vo.mp3')]
        fc.append(f"[{idx}:a]volume=1.25,adelay=300|300[vo];")
        idx += 1
    if (out / "music.mp3").exists():
        cmd += ["-i", str(out / 'music.mp3')]
        if (out / "vo.mp3").exists():
            fc.append(f"[{idx}:a]volume=0.18[m0];[m0][vo]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus];")
            amix = ["[mus]", "[vo]"]
        else:
            fc.append(f"[{idx}:a]volume=0.5[mus];")
            amix = ["[mus]"]
        idx += 1
    elif (out / "vo.mp3").exists():
        amix = ["[vo]"]
    if amix:
        fc.append("".join(amix) + f"amix=inputs={len(amix)}:duration=first:dropout_transition=0[a]")
        cmd += ["-filter_complex", "".join(fc), "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(final)]
    subprocess.run(cmd, capture_output=True, timeout=600)
    _set(sb_id, gen_status="done",
         output_paths=[f"/media/produced/{sb_id}/still_{i}.png" for i in range(len(scenes))],
         output_video=f"/media/produced/{sb_id}/final.mp4")


def produce(sb_id: int) -> bool:
    """Запуск производства в фоне. True = стартовало."""
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        if not sb or (sb.gen_status and sb.gen_status not in ("", "done", "error")):
            return False
        scenes = list(sb.scenes or [])
        is_carousel = scenes and all(float(x.get("duration_s") or 0) == 0 for x in scenes)
        sb.gen_status = "старт…"
        sb.gen_error = ""

    def _run():
        try:
            (_produce_slides if is_carousel else _produce_video)(sb_id)
        except Exception as e:
            log.exception("produce %s failed", sb_id)
            _set(sb_id, gen_status="error", gen_error=str(e)[:500])

    threading.Thread(target=_run, daemon=True).start()
    return True
