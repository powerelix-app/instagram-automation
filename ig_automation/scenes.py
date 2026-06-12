"""Генерация фоновых сцен через Replicate (фаза 1 плана scene-generation).

Паттерн переиспользован из wb-design/scripts/generate_images.py: call_replicate с
заголовком `Prefer: wait`, sanitize промпта, модели Flux. Текст на сцене НЕ рисуем —
он накладывается нашим бренд-оверлеем (brand_overlay), поэтому в промпт добавляем
«no text/no watermark», а из пользовательского промпта вырезаем hex и закавыченные фразы.
"""
from __future__ import annotations

import base64
import re
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from . import config

SCENES_DIR = config.OUTPUT_DIR / "scenes"
MODEL_HQ = "black-forest-labs/flux-1.1-pro-ultra"  # флаг --hq, проверенная hero-модель
RATIOS = {"4:5": (1080, 1350), "9:16": (1080, 1920), "1:1": (1080, 1080)}

_HEX_RE = re.compile(r"#?\b[0-9A-Fa-f]{6}\b")
_QUOTED_RE = re.compile(r'["«»][^"«»]{1,150}["«»]')
_NO_TEXT = "no text, no words, no letters, no watermark, no logo, no caption"


def sanitize(prompt: str) -> str:
    """Убрать hex-коды и закавыченные фразы — модели печатают их буквами на картинке."""
    return _QUOTED_RE.sub("", _HEX_RE.sub("", prompt or "")).strip()


def _headers() -> dict:
    if not config.REPLICATE_API_TOKEN:
        raise SystemExit(
            "Не задан REPLICATE_API_TOKEN в .env. Скопируй токен из wb-design/.env и повтори."
        )
    return {
        "Authorization": f"Bearer {config.REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }


def _call_replicate(model: str, body: dict, timeout: int = 60, retries: int = 4,
                    poll_tries: int = 90, poll_every: int = 4) -> dict:
    """Запуск модели Replicate с АСИНХРОННЫМ поллингом (без `Prefer: wait`).

    С РФ-VPS длинное wait-соединение к api.replicate.com рвёт РКН (SSLEOFError) —
    поэтому POST мгновенный (короткое соединение), а статус опрашиваем отдельно.
    Возвращает завершённый prediction (с полем output), как раньше."""
    if not config.REPLICATE_API_TOKEN:
        raise SystemExit("Не задан REPLICATE_API_TOKEN в .env.")
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
    last: Exception | None = None
    pred: dict | None = None
    for i in range(retries):
        try:
            r = requests.post(url, headers=h, json={"input": body}, timeout=timeout)
            if r.status_code == 402:
                raise SystemExit("Replicate: недостаточно баланса на аккаунте (HTTP 402).")
            if r.status_code >= 400:
                last = RuntimeError(f"{model} → HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(2 * (i + 1))
                continue
            pred = r.json()
            break
        except requests.RequestException as e:  # сеть/SSL-обрыв (РКН) → backoff и retry
            last = e
            time.sleep(2 * (i + 1))
    if pred is None:
        raise last or RuntimeError("Replicate: старт запроса не удался")
    get_url = (pred.get("urls") or {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            return pred
        if st in ("failed", "canceled"):
            raise RuntimeError(f"Replicate {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        for _a in range(3):  # опрос статуса с ретраем на транзиентные обрывы
            try:
                pred = requests.get(get_url, headers=h, timeout=30).json()
                break
            except requests.RequestException:
                time.sleep(2)
    raise RuntimeError("Replicate: таймаут ожидания рендера")


def _call_xai_image(prompt: str, aspect_ratio: str = "3:4", retries: int = 3) -> bytes:
    """Grok (xAI) image API — не Replicate. Возвращает байты PNG.

    POST https://api.x.ai/v1/images/generations, OpenAI-совместимый. aspect_ratio
    из набора xAI (4:5 нет → ближайший портрет 3:4, потом _fit обрежет до 1080x1350).
    """
    if not config.XAI_API_KEY:
        raise SystemExit("Не задан XAI_API_KEY в .env. Добавь строку XAI_API_KEY=xai-... и повтори.")
    url = "https://api.x.ai/v1/images/generations"
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": "grok-imagine-image-quality", "prompt": prompt, "n": 1,
            "response_format": "url", "aspect_ratio": aspect_ratio, "resolution": "2k"}
    last: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=300)
            if r.status_code >= 400:
                last = RuntimeError(f"xAI → HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(2 * (i + 1))
                continue
            data = r.json()["data"][0]
            if data.get("url"):
                img = requests.get(data["url"], timeout=120)
                img.raise_for_status()
                return img.content
            import base64
            return base64.b64decode(data["b64_json"])
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last or RuntimeError("xAI: запрос не удался")


def _data_url(path: str | Path, max_w: int = 1024) -> str:
    """Локальная картинка → base64 data URL (для image.url в xAI edits)."""
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _xai_bytes(data: dict) -> bytes:
    """data[0] из ответа xAI → байты картинки (url или b64_json)."""
    if data.get("url"):
        img = requests.get(data["url"], timeout=120)
        img.raise_for_status()
        return img.content
    return base64.b64decode(data["b64_json"])


def _call_xai_edit(prompt: str, refs: list[str | Path], aspect_ratio: str = "3:4",
                   retries: int = 3) -> bytes:
    """Grok image-EDIT с одним/несколькими референс-изображениями (character/product).

    POST /v1/images/edits: image (один) или images[] (несколько) как base64 data URL.
    Используется для консистентности персонажа (тот же портрет) + врезки нашей банки.
    """
    if not config.XAI_API_KEY:
        raise SystemExit("Не задан XAI_API_KEY в .env.")
    url = "https://api.x.ai/v1/images/edits"
    headers = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": "grok-imagine-image-quality", "prompt": prompt, "n": 1,
            "response_format": "url", "aspect_ratio": aspect_ratio, "resolution": "2k"}
    if len(refs) == 1:
        body["image"] = {"url": _data_url(refs[0])}
    else:
        body["images"] = [{"url": _data_url(r)} for r in refs]
    last: Exception | None = None
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=300)
            if r.status_code >= 400:
                last = RuntimeError(f"xAI edits → HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(2 * (i + 1))
                continue
            return _xai_bytes(r.json()["data"][0])
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last or RuntimeError("xAI edits: запрос не удался")


def _call_xai_video(prompt: str, image: str | Path | None = None,
                    refs: list[str | Path] | None = None, duration: int = 6,
                    aspect_ratio: str = "9:16", resolution: str = "720p",
                    poll_tries: int = 60, poll_every: int = 8) -> bytes:
    """Grok image→video (xAI). Возвращает байты mp4.

    POST /v1/videos/generations (async) → request_id → poll GET /v1/videos/{id}.
    image=стартовый кадр (data URL), refs=reference_images (например, лицо бренда).
    upload_url НЕ обязателен — xAI хостит результат и отдаёт ссылку.
    """
    if not config.XAI_API_KEY:
        raise SystemExit("Не задан XAI_API_KEY в .env.")
    h = {"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": "grok-imagine-video", "prompt": prompt, "duration": duration,
            "aspect_ratio": aspect_ratio, "resolution": resolution}
    if image:
        body["image"] = {"url": _data_url(image)}
    if refs:
        body["reference_images"] = [{"url": _data_url(r)} for r in refs]
    # старт-запрос с ретраем на транзиентные сетевые/SSL-обрывы
    rid = None
    last: Exception | None = None
    for i in range(4):
        try:
            r = requests.post("https://api.x.ai/v1/videos/generations", headers=h, json=body, timeout=120)
            if r.status_code >= 400:
                raise RuntimeError(f"xAI video → HTTP {r.status_code}: {r.text[:300]}")
            rid = r.json()["request_id"]
            break
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (i + 1))
    if rid is None:
        raise last or RuntimeError("xAI video: старт-запрос не удался")
    for _ in range(poll_tries):
        s = requests.get(f"https://api.x.ai/v1/videos/{rid}", headers={"Authorization": h["Authorization"]}, timeout=60)
        d = s.json()
        if d.get("status") == "done":
            vurl = (d.get("video") or {}).get("url")
            mp4 = requests.get(vurl, timeout=180)
            mp4.raise_for_status()
            return mp4.content
        if d.get("status") in ("failed", "error"):
            raise RuntimeError(f"xAI video failed: {str(d)[:300]}")
        time.sleep(poll_every)
    raise RuntimeError("xAI video: таймаут ожидания рендера")


def _call_replicate_video(prompt: str, image: str | Path, duration: int = 5,
                          aspect_ratio: str = "9:16", resolution: str = "720p",
                          model: str = "xai/grok-imagine-video-1.5",
                          poll_tries: int = 90, poll_every: int = 6) -> bytes:
    """Grok Imagine video через Replicate (image→video). Возвращает байты mp4.

    Используем, когда официальный xAI-баланс пуст, а на Replicate есть кредиты.
    aspect_ratio по умолчанию = формат входной картинки (наши 9:16 → без растяжения).
    """
    body = {"image": _ref_input(image), "prompt": prompt, "duration": duration,
            "aspect_ratio": aspect_ratio, "resolution": resolution}
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(url, headers=h, json={"input": body}, timeout=120)
    if r.status_code == 402:
        raise SystemExit("Replicate: недостаточно баланса (HTTP 402).")
    if r.status_code >= 400:
        raise RuntimeError(f"{model} → HTTP {r.status_code}: {r.text[:300]}")
    pred = r.json()
    get_url = pred.get("urls", {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            out = pred.get("output")
            if isinstance(out, list):
                out = out[0] if out else None
            if not out:
                raise RuntimeError("Replicate video: пустой output")
            mp4 = requests.get(out, timeout=180); mp4.raise_for_status()
            return mp4.content
        if st in ("failed", "canceled"):
            raise RuntimeError(f"Replicate video {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        pred = requests.get(get_url, headers=h, timeout=60).json()
    raise RuntimeError("Replicate video: таймаут ожидания рендера")


def generate_video(image: str | Path, prompt: str = "", duration: int = 5,
                   aspect_ratio: str = "9:16", out_name: str | None = None) -> Path:
    """image→video через Replicate (grok-imagine-video). Сохраняет mp4 в output/scenes,
    возвращает путь. Стартовый кадр image — наш брендовый hero 9:16."""
    content = _call_replicate_video(
        sanitize(prompt) or "subtle natural cinematic motion, soft lighting, no text",
        image, duration=duration, aspect_ratio=aspect_ratio,
    )
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    out = SCENES_DIR / (out_name or "reel.mp4")
    out.write_bytes(content)
    return out


def _call_replicate_image(prompt: str, refs: list[str | Path] | None = None,
                          aspect_ratio: str = "9:16", model: str = "google/nano-banana",
                          poll_tries: int = 60, poll_every: int = 4) -> bytes:
    """Image-генерация через Replicate (nano-banana) с мультиреференсом (image_input[]).

    Запасной путь, когда прямой xAI-баланс пуст (edits/generations → 403). nano-banana
    хорошо держит лицо/продукт по референсам. Короткий негатив (длинный ловит E005).
    """
    body: dict = {"prompt": f"{sanitize(prompt)}. no text, no logo", "aspect_ratio": aspect_ratio}
    if refs:
        body["image_input"] = [_data_url(r) for r in refs]
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json",
         "Prefer": "wait"}
    r = requests.post(url, headers=h, json={"input": body}, timeout=180)
    if r.status_code == 402:
        raise SystemExit("Replicate: недостаточно баланса (HTTP 402).")
    if r.status_code >= 400:
        raise RuntimeError(f"{model} → HTTP {r.status_code}: {r.text[:300]}")
    pred = r.json()
    get_url = pred.get("urls", {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            out = pred.get("output")
            if isinstance(out, list):
                out = out[0] if out else None
            if not out:
                raise RuntimeError("Replicate image: пустой output")
            img = requests.get(out, timeout=120); img.raise_for_status()
            return img.content
        if st in ("failed", "canceled"):
            raise RuntimeError(f"Replicate image {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        pred = requests.get(get_url, headers={"Authorization": h["Authorization"]}, timeout=60).json()
    raise RuntimeError("Replicate image: таймаут ожидания")


def _call_replicate_grok_image(prompt: str, image: str | Path | None = None,
                               aspect_ratio: str = "2:3", resolution: str = "2k",
                               model: str = "xai/grok-imagine-image-quality",
                               poll_tries: int = 60, poll_every: int = 4) -> bytes:
    """Grok image через Replicate (а НЕ прямой xAI — там кончились кредиты).

    Модель `xai/grok-imagine-image-quality` (2k, хороший рендер текста). Принимает ОДНУ
    референс-картинку `image` для редактирования (не массив). При editing aspect_ratio
    игнорируется — выход в пропорциях входной картинки.
    """
    body: dict = {"prompt": sanitize(prompt), "resolution": resolution}
    if image:
        body["image"] = _data_url(image, max_w=1280)
    else:
        body["aspect_ratio"] = aspect_ratio
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json",
         "Prefer": "wait"}
    r = requests.post(url, headers=h, json={"input": body}, timeout=180)
    if r.status_code == 402:
        raise SystemExit("Replicate: недостаточно баланса (HTTP 402).")
    if r.status_code >= 400:
        raise RuntimeError(f"{model} → HTTP {r.status_code}: {r.text[:300]}")
    pred = r.json()
    get_url = pred.get("urls", {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            out = pred.get("output")
            if isinstance(out, list):
                out = out[0] if out else None
            if not out:
                raise RuntimeError("Replicate grok image: пустой output")
            img = requests.get(out, timeout=120); img.raise_for_status()
            return img.content
        if st in ("failed", "canceled"):
            raise RuntimeError(f"Replicate grok image {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        pred = requests.get(get_url, headers={"Authorization": h["Authorization"]}, timeout=60).json()
    raise RuntimeError("Replicate grok image: таймаут")


def _call_replicate_faceswap(swap_image: str | Path, target_image: str | Path,
                             model: str = "cdingram/face-swap",
                             poll_tries: int = 60, poll_every: int = 3) -> bytes:
    """Face-swap через Replicate: лицо `swap_image` → на `target_image`. Возвращает байты.

    Приём для продуктовых кадров: Grok рисует живой хват + сохраняет реальную этикетку
    (но лицо чужое) → face-swap ставит лицо нашей AI-модели (`ai_model.png`), банку не
    трогает. Модель community → запускаем через /v1/predictions с version-хешем.
    """
    h = {"Authorization": f"Bearer {config.REPLICATE_API_TOKEN}", "Content-Type": "application/json",
         "Prefer": "wait"}
    ver = requests.get(f"https://api.replicate.com/v1/models/{model}", headers=h, timeout=40
                       ).json()["latest_version"]["id"]
    body = {"swap_image": _data_url(swap_image, 1024), "input_image": _data_url(target_image, 1280)}
    r = requests.post("https://api.replicate.com/v1/predictions", headers=h,
                      json={"version": ver, "input": body}, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"face-swap → HTTP {r.status_code}: {r.text[:300]}")
    pred = r.json()
    get_url = pred.get("urls", {}).get("get")
    for _ in range(poll_tries):
        st = pred.get("status")
        if st == "succeeded":
            out = pred.get("output")
            if isinstance(out, list):
                out = out[0] if out else None
            if not out:
                raise RuntimeError("face-swap: пустой output")
            img = requests.get(out, timeout=120); img.raise_for_status()
            return img.content
        if st in ("failed", "canceled"):
            raise RuntimeError(f"face-swap {st}: {str(pred.get('error'))[:200]}")
        time.sleep(poll_every)
        pred = requests.get(get_url, headers={"Authorization": h["Authorization"]}, timeout=60).json()
    raise RuntimeError("face-swap: таймаут")


def _output_url(resp: dict) -> str:
    out = resp.get("output")
    if isinstance(out, list):
        out = out[0] if out else None
    if not out:
        raise RuntimeError(f"Replicate: пустой output (status={resp.get('status')!r})")
    return out


def _fit(im: Image.Image, ratio: str) -> Image.Image:
    """Cover-fit к точному размеру под ratio (на случай если модель дала чуть иной)."""
    w, h = RATIOS[ratio]
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


BRAND_FACE = config.ROOT / "assets" / "brand" / "ai_model.png"
_AR = {"4:5": "3:4", "9:16": "9:16", "1:1": "1:1"}


def _public_ref_url(p: str | Path) -> str:
    """Публичная ссылка на референс (Replicate сам скачает его). Пусто — если не под
    /media или /brand-files (тогда придётся base64). Маленький POST вместо большого
    base64 — РКН не рвёт короткие запросы к api.replicate.com."""
    p = Path(p)
    for base, sub in ((config.MEDIA_DIR, "media"), (config.ROOT / "assets" / "brand", "brand-files")):
        try:
            rel = p.resolve().relative_to(base.resolve())
            return f"{config.PUBLIC_BASE}/{sub}/{rel.as_posix()}"
        except (ValueError, OSError):
            continue
    return ""


def _ref_input(r: str | Path) -> str:
    """Референс → публичный URL (предпочтительно) или base64 data-URL (фолбэк)."""
    return _public_ref_url(r) or _data_url(r)


def _call_replicate_edit(model: str, prompt: str, refs: list[str | Path], ratio: str) -> bytes:
    """Брендовый image-edit через Replicate (nano-banana и т.п.) с референс-картинками.
    Референсы передаём публичными URL (короткий POST — РКН не рвёт)."""
    body: dict = {"prompt": prompt, "image_input": [_ref_input(r) for r in refs], "output_format": "png"}
    if "nano-banana" in model:
        body["aspect_ratio"] = ratio
    resp = _call_replicate(model, body)
    url = _output_url(resp)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def generate_branded(
    prompt: str,
    refs: list[str | Path] | None = None,
    ratio: str = "4:5",
    out_name: str | None = None,
) -> Path:
    """Image-edit с референсом постоянного лица бренда → тот же персонаж, сцена по
    промпту. Бэкенд по config.BRANDED_MODEL: Replicate google/nano-banana (дефолт)
    или Grok (CF_BRANDED_MODEL=grok). refs=None → только лицо."""
    if ratio not in RATIOS:
        raise ValueError(f"ratio {ratio!r} не из {list(RATIOS)}")
    refs = refs or [BRAND_FACE]
    full = f"{sanitize(prompt)}. no text, no logo"
    model = config.BRANDED_MODEL
    if "grok" in model:
        content = _call_xai_edit(full, refs, _AR[ratio])
    else:
        content = _call_replicate_edit(model, full, refs, ratio)
    im = _fit(Image.open(BytesIO(content)).convert("RGB"), ratio)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    out = SCENES_DIR / (out_name or "branded.png")
    im.save(out)
    return out


def generate_scene(
    prompt: str,
    ratio: str = "4:5",
    hq: bool = False,
    model: str | None = None,
    out_name: str | None = None,
) -> Path:
    """Промпт → сцена нужного ratio → PNG в output/scenes/. Возвращает путь."""
    if ratio not in RATIOS:
        raise ValueError(f"ratio {ratio!r} не из {list(RATIOS)}")
    mdl = model or (MODEL_HQ if hq else config.IMAGE_MODEL)
    full_prompt = f"{sanitize(prompt)}. {_NO_TEXT}. vertical {ratio} composition"
    if "grok" in mdl:
        # Grok (xAI) — отдельный API, не Replicate. 4:5 → ближайший портрет 3:4.
        ar = {"4:5": "3:4", "9:16": "9:16", "1:1": "1:1"}[ratio]
        content = _call_xai_image(f"{sanitize(prompt)}. no text, no logo", ar)
        im = _fit(Image.open(BytesIO(content)).convert("RGB"), ratio)
        SCENES_DIR.mkdir(parents=True, exist_ok=True)
        out = SCENES_DIR / (out_name or "scene.png")
        im.save(out)
        return out
    if "gpt-image" in mdl:
        # gpt-image-1 поддерживает только 1:1/3:2/2:3 → портретные кадры мапим на 2:3
        ar = {"4:5": "2:3", "9:16": "2:3", "1:1": "1:1"}[ratio]
        if not config.OPENAI_API_KEY:
            raise SystemExit("gpt-image-1 требует OPENAI_API_KEY (.env). Не задан.")
        body = {"prompt": full_prompt, "aspect_ratio": ar, "openai_api_key": config.OPENAI_API_KEY,
                "quality": "high", "output_format": "png", "number_of_images": 1}
    elif "nano-banana" in mdl:
        # nano-banana (Gemini Flash Image): длинный негатив _NO_TEXT детерминированно
        # ловит safety-фильтр (E005) — даём короткий негатив; aspect_ratio поддерживается
        body = {"prompt": f"{sanitize(prompt)}. no text, no logo",
                "aspect_ratio": ratio, "output_format": "png"}
    else:
        body = {"prompt": full_prompt, "aspect_ratio": ratio, "output_format": "png"}
        if "flux-1.1-pro" in mdl:
            body |= {"raw": False, "safety_tolerance": 5}

    resp = _call_replicate(mdl, body)
    img_url = _output_url(resp)
    r = requests.get(img_url, timeout=120)
    r.raise_for_status()
    im = _fit(Image.open(BytesIO(r.content)).convert("RGB"), ratio)

    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    out = SCENES_DIR / (out_name or "scene.png")
    im.save(out)
    return out
