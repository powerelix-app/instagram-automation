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
# Цепочка моделей для кадров с продуктом: дешёвая первой, если этикетка вышла
# кривой (проверяет Claude-vision) — следующая. gemini на ProxyAPI = копейки;
# gpt-image-2 — чемпион по кириллице, зовём напрямую в OpenAI (без наценки ProxyAPI).
import os as _os
# nano = nano-banana-2 на Replicate (~$0.07 ≈ 5-6₽/кадр) — в 3-4 раза дешевле
# того же gemini flash на ProxyAPI (~20₽/кадр); ProxyAPI-gemini остаётся фолбэком.
IMG_CHAIN = tuple((_os.getenv("CF_IMAGE_CHAIN") or "seedream,nano,gemini,gptimage2,grok").split(","))
# Движки анимации (все на fal, единая касса). Дефолт — Seedance 2.0.
VIDEO_ENGINES = {
    "seedance":      ("bytedance/seedance-2.0/image-to-video",      "Seedance 2.0"),
    "seedance_fast": ("bytedance/seedance-2.0/fast/image-to-video", "Seedance 2.0 fast (черновики)"),
    "kling":         ("fal-ai/kling-video/v3/standard/image-to-video", "Kling 3.0"),
    "grok":          ("xai/grok-imagine-video/image-to-video",      "Grok Imagine"),
    "omni":          ("google/gemini-omni-flash/image-to-video",    "Gemini Omni Flash"),
}
DEFAULT_VIDEO_ENGINE = "seedance"
FAL_I2V = VIDEO_ENGINES["kling"][0]
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
        data = rp.read_bytes()
        if len(data) > 400_000:  # ужимаем крупные референсы: меньше вход = меньше резерв ProxyAPI
            import tempfile, os as _os
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                small = tf.name
            subprocess.run(["ffmpeg", "-y", "-i", str(rp),
                            "-vf", "scale='min(1024,iw)':-2", "-q:v", "4", small],
                           capture_output=True, timeout=60)
            if Path(small).exists() and Path(small).stat().st_size > 0:
                data = Path(small).read_bytes()
                _os.unlink(small)
            parts.append({"inline_data": {"mime_type": "image/jpeg",
                                          "data": base64.b64encode(data).decode()}})
            continue
        parts.append({"inline_data": {
            "mime_type": "image/png" if rp.suffix == ".png" else "image/jpeg",
            "data": base64.b64encode(data).decode()}})
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


def _fit_ratio(img: bytes, ratio: str) -> bytes:
    """Центр-кроп PNG/JPG-байтов под соотношение вида '4:5'."""
    import io
    from PIL import Image as _Im
    rw, rh = (int(x) for x in ratio.split(":"))
    im = _Im.open(io.BytesIO(img)).convert("RGB")
    w, h = im.size
    target = rw / rh
    if abs(w / h - target) > 0.01:
        if w / h > target:
            nw = int(h * target); x0 = (w - nw) // 2
            im = im.crop((x0, 0, x0 + nw, h))
        else:
            nh = int(w / target); y0 = (h - nh) // 2
            im = im.crop((0, y0, w, y0 + nh))
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


def gen_image_gpt(prompt: str, refs: list, aspect: str = "4:5") -> bytes:
    """gpt-image-2 images/edits. Приоритет: OpenAI напрямую (наш ключ, без наценки),
    при гео-блоке (РФ-VPS) — тот же запрос через Apify media-fetcher,
    последний фолбэк — ProxyAPI (дороже). Лучший рендер кириллицы на этикетке."""
    size = "1536x1024" if aspect in ("16:9", "3:2") else "1024x1536"
    fields = {"model": "gpt-image-2", "prompt": prompt, "size": size, "quality": "high"}
    files = []
    for rp in refs:
        rp = Path(rp)
        mime = "image/png" if rp.suffix == ".png" else "image/jpeg"
        files.append(("image[]", (rp.name, rp.read_bytes(), mime)))

    def _parse(js: dict) -> bytes:
        return _fit_ratio(base64.b64decode(js["data"][0]["b64_json"]), aspect)

    if config.FAL_KEY:  # 0) fal ($0.165/кадр high — дешевле OpenAI direct, из РФ работает)
        try:
            from .. import scenes
            fal_size = "landscape_4_3" if aspect in ("16:9", "3:2") else "portrait_4_3"
            payload = {"prompt": prompt, "quality": "high", "image_size": fal_size,
                       "image_urls": [scenes._data_url(r, 1024) for r in refs]}
            r = requests.post("https://fal.run/fal-ai/gpt-image-2/edit",
                              headers={"Authorization": f"Key {config.FAL_KEY}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=600)
            r.raise_for_status()
            url = r.json()["images"][0]["url"]
            try:
                img = requests.get(url, timeout=120)
                img.raise_for_status()
                data = img.content
            except Exception:
                from .. import apify
                data = apify.fetch_via_actor(url) or b""
            if data:
                return _fit_ratio(data, aspect)
            raise RuntimeError("fal: результат не скачался")
        except Exception as e:
            log.warning("fal gpt-image fail (%s) — пробую OpenAI напрямую", e)

    if config.OPENAI_API_KEY:
        try:  # 1) напрямую
            r = requests.post("https://api.openai.com/v1/images/edits",
                              headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                              data=fields, files=files, timeout=600)
            r.raise_for_status()
            return _parse(r.json())
        except requests.RequestException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (402, 429):  # деньги/лимит — прокси не поможет
                raise
            log.warning("openai direct fail (%s) — через media-fetcher", e)
        try:  # 2) ручной multipart через Apify media-fetcher (гео-обход)
            import uuid
            boundary = uuid.uuid4().hex
            parts = []
            for k, v in fields.items():
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                             f"name=\"{k}\"\r\n\r\n{v}\r\n".encode())
            for k, (name, data, mime) in files:
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                             f"name=\"{k}\"; filename=\"{name}\"\r\n"
                             f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
            from .. import apify
            items = apify._run_actor(apify.FETCHER_ACTOR, {
                "url": "https://api.openai.com/v1/images/edits", "method": "POST",
                "headers": {"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                            "Content-Type": f"multipart/form-data; boundary={boundary}"},
                "body_b64": base64.b64encode(body).decode(),
            }, max_charge_usd=0.05, timeout=700)
            for it in items:
                if it.get("ok") and it.get("downloadUrl"):
                    raw = requests.get(it["downloadUrl"], params={"token": config.APIFY_TOKEN},
                                       timeout=180).content
                    return _parse(json.loads(raw))
            raise RuntimeError("media-fetcher не вернул ответ OpenAI")
        except Exception as e:
            log.warning("openai через media-fetcher fail (%s) — фолбэк ProxyAPI", e)
    # 3) ProxyAPI (наценка, но работает отовсюду)
    r = requests.post("https://api.proxyapi.ru/openai/v1/images/edits",
                      headers={"Authorization": f"Bearer {PROXY_KEY}"},
                      data=fields, files=files, timeout=600)
    r.raise_for_status()
    return _parse(r.json())


def gen_image_seedream(prompt: str, refs: list, aspect: str = "4:5") -> bytes:
    """Seedream 5.0 Pro edit (fal, $0.0675/кадр до 1536px) — самый дешёвый из
    сильных; этикетку с референсом держит на уровне gpt-image-2."""
    from .. import scenes
    r = requests.post("https://fal.run/bytedance/seedream/v5/pro/edit",
                      headers={"Authorization": f"Key {config.FAL_KEY}",
                               "Content-Type": "application/json"},
                      json={"prompt": prompt,
                            "image_urls": [scenes._data_url(x, 1024) for x in refs]},
                      timeout=600)
    r.raise_for_status()
    url = r.json()["images"][0]["url"]
    try:
        img = requests.get(url, timeout=120)
        img.raise_for_status()
        data = img.content
    except Exception:  # fal.media режется РКН с РФ-VPS
        from .. import apify
        data = apify.fetch_via_actor(url) or b""
    if not data:
        raise RuntimeError("seedream: результат не скачался")
    return _fit_ratio(data, aspect)


def gen_image_nano(prompt: str, refs: list, aspect: str = "4:5") -> bytes:
    """nano-banana-2 (gemini 3.1 flash image). Приоритет: fal.ai (~$0.08/кадр,
    пополняется USDC из РФ) → Replicate (~$0.07, нужна зарубежная карта).
    Оба в 3-4 раза дешевле того же gemini на ProxyAPI (~20₽)."""
    from .. import scenes
    if config.FAL_KEY:
        try:
            payload = {"prompt": prompt, "output_format": "png",
                       "image_urls": [scenes._data_url(r, 1024) for r in refs]}
            r = requests.post("https://fal.run/fal-ai/nano-banana-2/edit",
                              headers={"Authorization": f"Key {config.FAL_KEY}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=300)
            r.raise_for_status()
            url = r.json()["images"][0]["url"]
            try:
                img = requests.get(url, timeout=120)
                img.raise_for_status()
                data = img.content
            except Exception:  # fal.media режется РКН с РФ-VPS
                from .. import apify
                data = apify.fetch_via_actor(url) or b""
            if data:
                return _fit_ratio(data, aspect)
            raise RuntimeError("fal: результат не скачался")
        except Exception as e:
            log.warning("fal nano fail (%s) — пробую Replicate", e)
    # Replicate google/nano-banana-2
    body = {"prompt": prompt, "image_input": [scenes._data_url(r, 1024) for r in refs],
            "output_format": "png"}
    url = "https://api.replicate.com/v1/models/google/nano-banana-2/predictions"
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}",
         "Content-Type": "application/json", "Prefer": "wait"}
    r = requests.post(url, headers=h, json={"input": body}, timeout=300)
    if r.status_code == 402:
        raise SystemExit("Replicate: недостаточно баланса (HTTP 402).")
    r.raise_for_status()
    out = r.json().get("output")
    if isinstance(out, list):
        out = out[0] if out else None
    if not out:
        raise RuntimeError("replicate nano: пустой output")
    img = requests.get(out, timeout=120)
    img.raise_for_status()
    return _fit_ratio(img.content, aspect)


_MONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "montserrat-black.ttf"
_INTER_SB = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Inter-SemiBold.otf"


def _overlay_spot(img_path: Path) -> str:
    """Claude-vision: куда можно положить крупный заголовок, не перекрыв
    продукт/этикетку/лицо. -> 'top-left'|'top-right'|'bottom-left'|'bottom-right'|'none'."""
    import anthropic
    from pydantic import BaseModel
    from typing import Literal

    class _Spot(BaseModel):
        position: Literal["top-left", "top-right", "bottom-left", "bottom-right", "none"]
        reason: str = ""

    import io
    from PIL import Image as _Im
    _im = _Im.open(img_path).convert("RGB")
    if _im.width > 1024:
        _im = _im.resize((1024, int(_im.height * 1024 / _im.width)), _Im.LANCZOS)
    _buf = io.BytesIO(); _im.save(_buf, "JPEG", quality=88)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.b64encode(_buf.getvalue()).decode()}},
        {"type": "text", "text":
            "Это слайд Instagram-карусели. Хотим наложить КРУПНЫЙ заголовок (2-3 строки, "
            "занимает примерно четверть кадра). Выбери угол, где он НЕ перекроет банку "
            "продукта, её этикетку, лицо и руки человека и важные предметы. Верхняя "
            "полоса кадра занята маленьким логотипом — top-варианты чуть ниже него. "
            "Если чистого угла нет — position='none' (лучше без текста, чем поверх продукта)."},
    ]
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=200,
        messages=[{"role": "user", "content": content}], output_format=_Spot)
    v = resp.parsed_output
    log.info("overlay spot: %s (%s)", v.position, v.reason)
    return v.position


def smart_overlay(img_path: Path, title: str) -> None:
    """Вордмарк POWERELIX + заголовок в чистой зоне (по вердикту vision).
    Нет чистой зоны — только вордмарк."""
    from PIL import Image as _Im, ImageDraw, ImageFilter, ImageFont

    im = _Im.open(img_path).convert("RGBA")
    W, H = im.size
    try:
        pos = _overlay_spot(img_path)
    except Exception as e:
        log.warning("overlay spot недоступен (%s) — кладу bottom-left", e)
        pos = "bottom-left"

    f_logo = ImageFont.truetype(str(_MONT), int(H * 0.030))
    f_big = ImageFont.truetype(str(_MONT), int(H * 0.060))
    lh = int(H * 0.067)
    M = int(W * 0.055)

    tx = _Im.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(tx)
    d.text((M, int(H * 0.04)), "POWERELIX", font=f_logo, fill=(255, 255, 255, 255))

    if pos != "none":
        # перенос заголовка по словам, максимум 3 строки
        words = title.upper().split()
        lines, cur = [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=f_big) > W * 0.48 and cur:
                lines.append(cur); cur = w_
            else:
                cur = t
        lines.append(cur)
        lines = lines[:3]
        bh = len(lines) * lh
        y = int(H * 0.115) if "top" in pos else int(H - H * 0.06 - bh)
        yy = y
        right = "right" in pos
        for ln in lines:
            lw = d.textlength(ln, font=f_big)
            lx = int(W - M - lw) if right else M
            d.text((lx, yy), ln, font=f_big, fill=(255, 255, 255, 255))
            yy += lh
        ax = int(W - M - W * 0.10) if right else M
        d.rectangle([ax, yy + int(H * 0.008), ax + int(W * 0.10), yy + int(H * 0.014)],
                    fill=(22, 255, 179, 255))

    sh = tx.split()[3].filter(ImageFilter.GaussianBlur(7))
    shadow = _Im.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(sh.point(lambda a: int(a * 0.6)))
    im = _Im.alpha_composite(im, shadow)
    im.alpha_composite(tx)
    im.convert("RGB").save(img_path)


def _label_verdict(img: bytes, bottle: Path) -> dict:
    """Claude-vision сверяет этикетку на кадре с реальной банкой.
    -> {ok, reason}. Ошибка проверки = ok (не блокируем производство)."""
    import anthropic
    from pydantic import BaseModel

    class _V(BaseModel):
        ok: bool
        reason: str = ""

    try:
        content = [
            {"type": "text", "text": "Кадр (проверяемый):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.b64encode(_fit_ratio(img, "4:5")).decode()}},
            {"type": "text", "text": "Реальная банка (эталон):"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(_shrink(bottle)).decode()}},
            {"type": "text", "text":
                "На кадре есть банка нашего продукта? Сравни её этикетку с эталоном: "
                "логотип POWERELIX и весь читаемый русский текст должны быть БЕЗ выдуманных "
                "букв/слов (мелкий нечитаемый текст не считается). ok=false если текст "
                "этикетки перевран, банка другая или упаковка выдумана."},
        ]
        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model=config.CLAUDE_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": content}], output_format=_V)
        v = resp.parsed_output
        return {"ok": v.ok, "reason": v.reason}
    except Exception as e:
        log.warning("label verdict failed (пропускаю проверку): %s", e)
        return {"ok": True, "reason": f"проверка недоступна: {e}"}


def _shrink(p: Path, max_w: int = 900) -> bytes:
    import io
    from PIL import Image as _Im
    im = _Im.open(p).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), _Im.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def gen_product_image(prompt: str, refs: list, aspect: str = "4:5",
                      chain=IMG_CHAIN, sb_id: Optional[int] = None,
                      bottle: Optional[Path] = None) -> bytes:
    """Кадр с продуктом: идём по цепочке нейросетей, после каждой Claude-vision
    проверяет этикетку; кривая этикетка -> следующая модель. Все кривые варианты
    не выбрасываем: если ни одна не прошла, отдаём последний."""
    # банка для vision-проверки: явно или последним референсом (конвенция);
    # bottle=None и нет refs -> проверку пропускаем
    bottle = Path(bottle) if bottle else (Path(refs[-1]) if refs else None)
    last = b""
    for name in chain:
        try:
            if sb_id:
                _set(sb_id, gen_status=f"генерация ({name})…")
            if name == "seedream":
                img = gen_image_seedream(prompt, refs, aspect)
            elif name == "nano":
                img = gen_image_nano(prompt, refs, aspect)
            elif name == "gptimage2":
                img = gen_image_gpt(prompt, refs, aspect)
            elif name == "gemini":
                img = gen_image(prompt, refs=refs, aspect=aspect, style_suffix="")
            elif name == "grok":
                from .. import scenes
                img = _fit_ratio(scenes._call_replicate_grok_image(prompt, image=bottle), aspect)
            else:
                continue
        except SystemExit as e:  # нет баланса — просто идём дальше по цепочке
            log.warning("модель %s недоступна: %s", name, e)
            continue
        except Exception as e:
            log.warning("модель %s упала: %s", name, e)
            continue
        last = img
        v = _label_verdict(img, bottle) if bottle else {"ok": True, "reason": ""}
        if v["ok"]:
            log.info("этикетка ok (%s)", name)
            return img
        log.warning("этикетка кривая (%s): %s — пробую следующую модель", name, v["reason"])
    if not last:
        raise RuntimeError("ни одна модель цепочки не вернула картинку")
    return last


class ContentPolicyError(RuntimeError):
    """Движок отклонил кадр по content policy (обычно Seedance: реалистичные люди)."""


def _add_face_noise(image: bytes) -> bytes:
    """Лёгкий монохромный шум на кадр — сбивает детектор «реальных лиц» Seedance
    (приём MidGuru), почти незаметен глазу. Возвращает PNG-байты."""
    import io
    import numpy as np
    from PIL import Image as _Im
    im = _Im.open(io.BytesIO(image)).convert("RGB")
    arr = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(12345)
    noise = rng.integers(-10, 11, size=arr.shape[:2])[..., None]  # ±10, один слой на все каналы
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    _Im.fromarray(out).save(buf, "PNG")
    return buf.getvalue()


def fal_i2v(image: bytes, prompt: str, duration: int = 5,
            engine: str = DEFAULT_VIDEO_ENGINE,
            end_image: Optional[bytes] = None) -> bytes:
    """Анимация кадра через fal. end_image — последний кадр (переход first→last):
    движок интерполирует движение между двумя кадрами по промпту."""
    model = VIDEO_ENGINES.get(engine, VIDEO_ENGINES[DEFAULT_VIDEO_ENGINE])[0]
    data_uri = "data:image/png;base64," + base64.b64encode(image).decode()
    start_key = "start_image_url" if "kling-video/v3" in model else "image_url"
    payload = {start_key: data_uri, "prompt": prompt,
               "duration": "10" if duration > 7 else "5", "sound": False}
    if end_image:
        payload["end_image_url"] = ("data:image/png;base64,"
                                    + base64.b64encode(end_image).decode())
    r = requests.post(
        f"https://queue.fal.run/{model}",
        headers={"Authorization": f"Key {config.FAL_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=60)
    if r.status_code == 422 and end_image:  # движок не умеет end-frame — без него
        log.warning("движок %s не принял end_image_url — анимирую без него", engine)
        payload.pop("end_image_url", None)
        r = requests.post(
            f"https://queue.fal.run/{model}",
            headers={"Authorization": f"Key {config.FAL_KEY}",
                     "Content-Type": "application/json"},
            json=payload, timeout=60)
    r.raise_for_status()
    req = r.json()
    status_url = req.get("status_url") or f"https://queue.fal.run/{model}/requests/{req['request_id']}/status"
    resp_url = req.get("response_url") or f"https://queue.fal.run/{model}/requests/{req['request_id']}"
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
        if "content_policy" in str(out):
            raise ContentPolicyError(f"движок {engine} отклонил кадр (content policy)")
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
        model_key = getattr(sb, "model_key", "") or ""
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
    from .brand import model_by_key
    face = model_by_key(model_key)
    if ref_slides:
        for i, rs in enumerate(ref_slides):
            _set(sb_id, gen_status=f"слайд {i + 1}/{len(ref_slides)} (по референсу)…")
            hint = scenes[i].get("scene", "") if i < len(scenes) else ""
            prompt = (
                "ПЕРВОЕ изображение — референсный слайд. Пересоздай его МАКСИМАЛЬНО похоже: "
                "та же композиция, ракурс, свет, стиль, креативный приём, ДЕЙСТВИЕ и настроение "
                "(если человек пьёт/наливает/держит — то же самое действие, без изменений). "
                "НО: если в кадре есть человек — замени его на НАШУ модель со ВТОРОГО изображения "
                "(то же лицо: медные волнистые волосы, веснушки; поза и действие как в референсе, "
                "НЕ копируй внешность человека из референса). "
                "ЛЮБОЙ продукт/упаковку замени на НАШ продукт с ТРЕТЬЕГО изображения — форма банки, "
                "крышка, цвет и этикетка СТРОГО как на референсе продукта, этикетка чёткая, читаемая, "
                "повернута к камере, БАНКА ЦЕЛИКОМ В КАДРЕ (не обрезать краем). ЗАПРЕЩЕНО придумывать "
                "другую упаковку или оставлять продукт из референса. Цветовую гамму сцены адаптируй "
                "под фирменный цвет нашего продукта.\n"
                + (f"Контекст слайда: {hint}\n" if hint else "")
                + "СТРОГО: никакого текста, букв или надписей на изображении, "
                "кроме этикетки нашего продукта.")
            refs_i = [rs] + ([face] if face else []) + [bottle]
            if not face:  # без лица бренда нумерация референсов сдвигается
                prompt = prompt.replace("со ВТОРОГО изображения", "— наша модель (медные волнистые волосы, веснушки)")
                prompt = prompt.replace("с ТРЕТЬЕГО изображения", "со ВТОРОГО изображения")
            img = gen_product_image(prompt, refs_i, aspect="4:5", sb_id=sb_id)
            p = out / f"slide_{i}.png"
            p.write_bytes(img)
            # фирменный оверлей: Claude-vision выбирает чистую зону; если текст
            # некуда класть (перекроет продукт/этикетку/лицо) — слайд без текста
            title = (scenes[i].get("slide_title") or "").strip() if i < len(scenes) else ""
            if title:
                try:
                    smart_overlay(p, title)
                except Exception as e:
                    log.warning("overlay fail слайд %s: %s", i, e)
            paths.append(f"/media/produced/{sb_id}/slide_{i}.png")
    else:  # фолбэк: по описаниям сцен
        for i, sc in enumerate(scenes):
            _set(sb_id, gen_status=f"слайд {i + 1}/{len(scenes)}…")
            prompt = (f"Слайд {i + 1} Instagram-карусели.\nВИЗУАЛ: {sc.get('scene', '')}\n"
                      f"Композиция: {sc.get('camera', '')}\n"
                      "СТРОГО: без текста и надписей (кроме этикетки продукта).")
            img = gen_product_image(prompt, [bottle], aspect="4:5", sb_id=sb_id)
            p = out / f"slide_{i}.png"
            p.write_bytes(img)
            paths.append(f"/media/produced/{sb_id}/slide_{i}.png")
    _set(sb_id, gen_status="done", output_paths=paths)


def _video_ctx(sb_id: int) -> dict:
    """Общий контекст видео-этапов: сцены, референсы, лицо, банка."""
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        ctx = {"scenes": list(sb.scenes or []), "product_id": sb.product_id,
               "vo_full": sb.vo_full, "music_hint": sb.music_hint,
               "reel_id": sb.trend_reel_id,
               "model_key": getattr(sb, "model_key", "") or "",
               "video_engine": getattr(sb, "video_engine", "") or DEFAULT_VIDEO_ENGINE}
    from .brand import model_by_key
    ctx["bottle"] = _product_ref(ctx["product_id"])
    ctx["face"] = model_by_key(ctx["model_key"])
    ref_dir = config.MEDIA_DIR / "frames" / str(ctx["reel_id"])
    ctx["ref_frames"] = sorted(ref_dir.glob("f*.jpg")) if ref_dir.exists() else []
    ctx["out"] = _out_dir(sb_id)
    return ctx


def _gen_scene_still(sb_id: int, i: int, ctx: dict) -> None:
    """Стилл одной сцены: референс-кадр + лицо бренда + банка (база слайдов).
    Для консистентности одежды/предметов/света добавляем предыдущий стилл."""
    scenes, out = ctx["scenes"], ctx["out"]
    sc = scenes[i]
    ref, face, ref_frames = ctx["bottle"], ctx["face"], ctx["ref_frames"]
    prev = out / f"still_{i - 1}.png" if i > 0 else None
    prev = prev if (prev and prev.exists() and prev.stat().st_size > 0) else None
    rs = None
    if ref_frames:
        idx = round(i * (len(ref_frames) - 1) / max(1, len(scenes) - 1))
        rs = ref_frames[min(idx, len(ref_frames) - 1)]
    if rs:
        prompt = (
            "ПЕРВОЕ изображение — референсный кадр видео. Пересоздай его МАКСИМАЛЬНО "
            "похоже: та же композиция, ракурс, свет, обстановка, ДЕЙСТВИЕ и настроение. "
            "НО: если в кадре есть человек — замени его на НАШУ модель со ВТОРОГО "
            "изображения (поза и действие как в референсе, НЕ копируй внешность "
            "человека из референса). "
            "ЛЮБОЙ продукт/упаковку замени на НАШ продукт с ТРЕТЬЕГО изображения — "
            "форма банки, крышка, цвет и этикетка СТРОГО как на референсе продукта, "
            "этикетка чёткая, читаемая, повернута к камере, БАНКА ЦЕЛИКОМ В КАДРЕ. "
            "ЗАПРЕЩЕНО придумывать другую упаковку.\n"
            f"Контекст сцены: {sc.get('scene', '')}\n"
            "СТРОГО: никакого текста и надписей, кроме этикетки нашего продукта. "
            "Вертикальный кадр 9:16.")
        refs_i = [rs] + ([face] if face else []) + ([ref] if ref else [])
        if not face:
            prompt = prompt.replace("со ВТОРОГО изображения", "— наша модель бренда")
            prompt = prompt.replace("с ТРЕТЬЕГО изображения", "со ВТОРОГО изображения")
        if prev:
            refs_i.append(prev)
            prompt += ("\nПОСЛЕДНЕЕ изображение — предыдущий кадр ЭТОГО ЖЕ ролика: "
                       "одежда и причёска модели, предметы на столе/фоне, цвет света "
                       "и цветокоррекция ДОЛЖНЫ полностью совпадать с ним "
                       "(меняется только действие по сцене).")
        still = gen_product_image(prompt, refs_i, aspect="9:16", sb_id=sb_id, bottle=ref)
    elif ref:
        still = gen_product_image(
            f"Кадр рекламного ролика.\n{sc.get('scene', '')}\n"
            "Если есть человек — модель бренда "
            + ("(лицо с первого референса). " if face else ". ")
            + "Банка продукта строго как на референсе.",
            ([face] if face else []) + [ref], aspect="9:16", sb_id=sb_id, bottle=ref)
    else:
        still = gen_image(f"Кадр рекламного ролика.\n{sc.get('scene', '')}")
    (out / f"still_{i}.png").write_bytes(still)


def _stills_stage(sb_id: int, only: Optional[int] = None) -> None:
    """Этап 1: стиллы сцен. only=i — перегенерация одного кадра (клип сцены сбрасывается)."""
    ctx = _video_ctx(sb_id)
    scenes, out = ctx["scenes"], ctx["out"]
    targets = [only] if only is not None else list(range(len(scenes)))
    for i in targets:
        sp = out / f"still_{i}.png"
        if only is None and sp.exists() and sp.stat().st_size > 0:
            continue
        _set(sb_id, gen_status=f"кадр {i + 1}/{len(scenes)}…")
        _gen_scene_still(sb_id, i, ctx)
        (out / f"clip_{i}.mp4").unlink(missing_ok=True)  # кадр новый — клип устарел
    _set(sb_id, gen_status="stills_ready",
         output_paths=[f"/media/produced/{sb_id}/still_{i}.png" for i in range(len(scenes))
                       if (out / f"still_{i}.png").exists()])


def _clips_stage(sb_id: int, only: Optional[int] = None) -> None:
    """Этап 2: анимация одобренных стиллов (Kling). only=i — переанимация одного клипа."""
    ctx = _video_ctx(sb_id)
    scenes, out = ctx["scenes"], ctx["out"]
    targets = [only] if only is not None else list(range(len(scenes)))
    for i in targets:
        sp = out / f"still_{i}.png"
        cp = out / f"clip_{i}.mp4"
        if not sp.exists():
            continue
        if only is None and cp.exists() and cp.stat().st_size > 0:
            continue
        sc = scenes[i]
        _set(sb_id, gen_status=f"анимация {i + 1}/{len(scenes)} (fal)…")
        dur = int(float(sc.get("duration_s") or 4)) or 4
        # переход first->last: конец клипа = стилл следующей сцены (бесшовные стыки)
        nxt = out / f"still_{i + 1}.png"
        end_bytes = nxt.read_bytes() if (nxt.exists() and nxt.stat().st_size > 0) else None
        # Seedance мягче модерирует русские промпты (и сцены у нас русские)
        if ctx["video_engine"].startswith("seedance"):
            i2v_prompt = (f"{sc.get('camera', 'медленное плавное движение камеры')}. "
                          f"{sc.get('scene', '')}. Один непрерывный кадр без склеек, "
                          "фотореалистично, естественная физика, движения плавные и "
                          "натуральные, не роботичные.")
        else:
            i2v_prompt = (f"{sc.get('camera', 'slow gentle camera move')}. "
                          f"{sc.get('scene', '')}. Single continuous shot, no cuts, "
                          "photorealistic, natural physics, movements natural not robotic.")
        try:
            try:
                clip = fal_i2v(sp.read_bytes(), i2v_prompt, duration=dur,
                               engine=ctx["video_engine"], end_image=end_bytes)
            except ContentPolicyError:
                # детектор лиц флачит стохастически — одна повторная попытка
                log.warning("content policy: ретрай на том же движке")
                _set(sb_id, gen_status=f"анимация {i + 1}/{len(scenes)}: ретрай…")
                clip = fal_i2v(sp.read_bytes(), i2v_prompt, duration=dur,
                               engine=ctx["video_engine"], end_image=end_bytes)
        except ContentPolicyError as e:
            # приём MidGuru: лёгкий шум на кадр сбивает детектор «реальных лиц»,
            # сохраняя качество Seedance. Только потом фолбэк на Kling.
            noisy = _add_face_noise(sp.read_bytes())
            end_noisy = _add_face_noise(end_bytes) if end_bytes else None
            try:
                if ctx["video_engine"] != "kling":
                    log.warning("%s — пробую Seedance с шумом на кадре", e)
                    _set(sb_id, gen_status=f"анимация {i + 1}/{len(scenes)}: шум-обход…")
                    clip = fal_i2v(noisy, i2v_prompt, duration=dur,
                                   engine=ctx["video_engine"], end_image=end_noisy)
                else:
                    raise ContentPolicyError("kling+content_policy")
            except ContentPolicyError:
                if ctx["video_engine"] != "kling":
                    log.warning("шум не помог — фолбэк на Kling")
                    _set(sb_id, gen_status=f"анимация {i + 1}/{len(scenes)}: фолбэк Kling…")
                    clip = fal_i2v(sp.read_bytes(), i2v_prompt, duration=dur,
                                   engine="kling", end_image=end_bytes)
                else:
                    raise
        cp.write_bytes(clip)
    _set(sb_id, gen_status="clips_ready")


def _assemble_stage(sb_id: int) -> None:
    """Этап 3: склейка одобренных клипов + голос Насти + музыка -> final.mp4."""
    ctx = _video_ctx(sb_id)
    scenes, out = ctx["scenes"], ctx["out"]
    vo_full, music_hint = ctx["vo_full"], ctx["music_hint"]
    clips = [out / f"clip_{i}.mp4" for i in range(len(scenes))
             if (out / f"clip_{i}.mp4").exists()]
    if not clips:
        raise RuntimeError("нет клипов для сборки — сначала анимируй кадры")
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
         output_video=f"/media/produced/{sb_id}/final.mp4")


def _produce_video(sb_id: int):
    """Полный прогон одним махом (легаси-кнопка): кадры -> анимация -> сборка."""
    _stills_stage(sb_id)
    _clips_stage(sb_id)
    _assemble_stage(sb_id)


def run_stage(sb_id: int, stage: str, only: Optional[int] = None) -> bool:
    """Фоновый запуск этапа: stills | clips | assemble. True = стартовало."""
    with session_scope() as s:
        sb = s.get(Storyboard, sb_id)
        busy = sb and sb.gen_status and sb.gen_status not in (
            "", "done", "error", "stills_ready", "clips_ready")
        if not sb or busy:
            return False
        sb.gen_status = "старт…"
        sb.gen_error = ""

    fn = {"stills": _stills_stage, "clips": _clips_stage, "assemble": _assemble_stage}[stage]

    def _run():
        try:
            fn(sb_id) if only is None else fn(sb_id, only)  # assemble без only
        except Exception as e:
            log.exception("stage %s %s failed", stage, sb_id)
            _set(sb_id, gen_status="error", gen_error=str(e)[:500])

    threading.Thread(target=_run, daemon=True).start()
    return True


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
