"""AI UGC-блогер: говорящий аватар рассказывает про продукт.

Приём из SYNTX (id 2158): Veo 3 с русской речью прямо в промпте генерит говорящую
голову с липсинком и голосом в ОДИН шаг. ChatGPT пишет живой UGC-сценарий, Veo
снимает «селфи-Reels» девушки-нутрициолога с банкой POWERELIX.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

from .. import config, products

log = logging.getLogger(__name__)

# Персоны UGC-блогеров (лицо/типаж). Расширяется; пока текстовые типажи под Veo.
PERSONAS = {
    "nutri": "молодая девушка-нутрициолог 25-30 лет, естественная кожа без ретуши, дружелюбная, "
             "спортивная, светлый верх, минимум макияжа",
    "mom": "обычная мама 30-35 лет, тёплая и искренняя, домашняя обстановка, без гламура",
    "fit": "фитнес-девушка 23-28 лет, спортивная форма, энергичная, утренний свет",
}


def ugc_script(product_id: str, angle: str = "польза") -> str:
    """ChatGPT пишет живой разговорный UGC-монолог на ~8-12 сек (2-3 фразы)."""
    import anthropic
    ctx = products.one_context(str(product_id)) or ""
    prompt = (
        "Ты — UGC-блогер, девушка-нутрициолог, снимаешь селфи-Reels про добавку. "
        "Напиши ЖИВОЙ разговорный монолог на 8-12 секунд (2-3 коротких предложения, ~25-40 слов). "
        "Правила: цепляющий хук в первой фразе; по-человечески, без канцелярита и без впаривания; "
        "мягкая польза; лёгкий призыв в конце (посмотреть/попробовать). БАД — НЕ лекарство: без "
        "обещаний вылечить/гарантий. Верни ТОЛЬКО текст реплики (что говорит девушка), без кавычек и ремарок.\n\n"
        f"ТОВАР:\n{ctx}\nАкцент: {angle}"
    )
    client = anthropic.Anthropic()
    r = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=300,
                               messages=[{"role": "user", "content": prompt}])
    return r.content[0].text.strip().strip('"').strip()


def _veo3(prompt: str, image: Optional[Path] = None, aspect: str = "9:16", duration: str = "8s") -> bytes:
    """Veo 3 fast на fal. image=None → text-to-video; image=старт-кадр → image-to-video
    (сохраняет реальную банку). Речь по-русски прямо в промпте. Возвращает mp4-байты."""
    if image is not None:
        from .. import scenes
        ep = "fal-ai/veo3/fast/image-to-video"
        payload = {"prompt": prompt, "image_url": scenes._data_url(image, 1080),
                   "aspect_ratio": aspect, "duration": duration, "generate_audio": True}
    else:
        ep = "fal-ai/veo3/fast"
        payload = {"prompt": prompt, "aspect_ratio": aspect, "duration": duration}
    r = requests.post(f"https://fal.run/{ep}",
                      headers={"Authorization": f"Key {config.FAL_KEY}", "Content-Type": "application/json"},
                      json=payload, timeout=600)
    r.raise_for_status()
    url = r.json()["video"]["url"]
    data = b""
    for _ in range(2):  # fal.media иногда режется РКН — ретрай, затем обход через apify
        try:
            v = requests.get(url, timeout=180)
            v.raise_for_status()
            data = v.content
            break
        except Exception as e:
            log.warning("veo3 download retry (%s)", e)
    if not data:
        from .. import apify
        data = apify.fetch_via_actor(url) or b""
    if not data:
        raise RuntimeError("veo3: видео не скачалось")
    return data


def _start_frame(product_id: str, persona_key: str = "nutri") -> Path:
    """Старт-кадр для i2v: persona-блогер держит РЕАЛЬНУЮ банку (nano edit по референсу),
    вертикальное селфи 9:16. Так Veo сохранит нашу этикетку (text-to-video её коверкает)."""
    from . import producer
    bottle = producer._product_ref(str(product_id))
    if not bottle:
        raise RuntimeError("нет референса банки в data/product_refs")
    persona = PERSONAS.get(persona_key, PERSONAS["nutri"])
    prompt = (
        "UGC-style vertical selfie photo, handheld, natural warm light, authentic amateur look, real skin texture. "
        f"{persona} holds THIS exact supplement bottle from the reference image at chest height, close to camera "
        "as if filming a selfie review in a cozy home kitchen. Keep the bottle shape, cap and LABEL EXACTLY as in "
        "the reference — do not change or distort the label text. Waist-up, looking into camera. "
        "Vertical 9:16 frame, no text overlays."
    )
    img = producer.gen_image_nano(prompt, [bottle], aspect="9:16")
    out = config.MEDIA_DIR / "bloggers" / f"start_{product_id}_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img)
    return out


def veo_prompt(product_name: str, script: str, persona_key: str = "nutri") -> str:
    persona = PERSONAS.get(persona_key, PERSONAS["nutri"])
    return (
        "UGC-style vertical selfie video, handheld phone, natural warm light, authentic amateur look, "
        "shallow depth, real skin texture. "
        f"{persona} holds a dark amber glass supplement bottle (green mint label) of {product_name}, "
        "looks directly into the camera and speaks in RUSSIAN with clear natural lip-sync and warm intonation: "
        f"\"{script}\". "
        "Casual home/kitchen background, slight handheld movement. No subtitles, no on-screen text, no captions."
    )


# ── Движок «Seedance-спикер» (приём Егора Кузьмина XR, id 22.04.2026) ─────────
# ВАЖНО: это НЕ text-to-speech. Нужен базовый видео-референс (@video_1), где кто-то
# уже говорит нужный текст — Seedance берёт оттуда ГОЛОС и тайминг губ, а лицо — из
# @image_1, и переносит в дорогую студийную сцену. Хак: язык в промпте «украинский»
# (обход запрета русского), а lyrics — русский текст. Доступ: Seedance 2.0 через SYNTX
# (мульти-референс image+video). Полуручной; держим шаблон для премиального спикера.
SEEDANCE_SPOKESPERSON = """@video_1 — base video reference. Master source for lip movements, \
facial articulation, head movements, speech timing, and audio.

@image_1 — exact face and body. Preserve likeness 100% throughout.

LANGUAGE AND VOICE:
Spoken language: Ukrainian. The character speaks Ukrainian throughout with natural \
conversational delivery, medium pace, relaxed tone. Use standard Ukrainian pronunciation.

lyrics: "{script}"

TASK: Relocate the speaker from @video_1 into a new environment, but preserve his speech \
and performance exactly:
— Lip movements and mouth shapes match @video_1 frame-for-frame
— Head movements, facial expressions, eye movements from @video_1
— Speech timing and rhythm from @video_1
— Audio from @video_1 is the final audio — do not regenerate, replace, or modify the voice
— The person in the new video must be @image_1

FORMAT: 9:16 / duration matches @video_1 / cinematic studio portrait
STYLE: High-end commercial studio cinematography. ARRI Alexa, 85mm lens. Ultra-sharp focus \
on face, cinematic shallow depth of field. Subtle film grain. Photorealistic skin texture.
COLOR: Dark moody studio. Deep black background. Single warm key light from above-right \
creating dramatic shadows. Strong contrast, rim light on hair and shoulders.
ENVIRONMENT: Professional photo studio, pure black seamless backdrop, @image_1 on a simple \
stool, plain black fitted t-shirt. Clean, cinematic, editorial feel.
FRAMING: Medium close-up, front-facing, eye level. Camera static, locked off, centered."""


def seedance_spokesperson_prompt(script: str) -> str:
    """Заполняет шаблон Seedance-спикера русским текстом (язык в промпте — «украинский»,
    хак для русской речи). Нужен базовый @video_1 (речь) + @image_1 (лицо)."""
    return SEEDANCE_SPOKESPERSON.format(script=script)


# Голос бренда: ElevenLabs «Nastya POWERELIX» (клон). Финальный рецепт (подтверждён юзером
# 22.07.2026): модель eleven_v3 (v3 держит русский и УДАРЕНИЯ верно, в отличие от multilingual_v2),
# stability 0.75 / similarity 0.25 — как в эталонном файле Nastya_pvc_sp100_s75_sb25_v3.
ELEVEN_MODEL = "eleven_v3"
NASTYA_SETTINGS = {"stability": 0.75, "similarity_boost": 0.25, "style": 0.0, "use_speaker_boost": True}


def _eleven_tts(text: str, out_path: Path, settings: Optional[dict] = None) -> Optional[Path]:
    """Озвучка голосом Насти (ElevenLabs) с настраиваемыми ползунками. Геопрокси внутри."""
    from . import producer
    try:
        data = producer._eleven_post(
            f"/v1/text-to-speech/{producer.NASTYA_VOICE}",
            {"text": text, "model_id": ELEVEN_MODEL, "voice_settings": settings or NASTYA_SETTINGS})
        out_path.write_bytes(data)
        return out_path
    except Exception as e:
        log.warning("eleven tts fail: %s", e)
        return None


def _gen_voice_clip(product_id: str, persona_key: str, script: str, ts: int) -> dict:
    """Движок 'voice': i2v говорящая мимика → озвучка ГОЛОСОМ НАСТИ (ElevenLabs) → липсинк.
    Точная, управляемая, живая русская речь (в отличие от генерённого голоса Veo)."""
    import shutil

    from . import reels
    from .. import scenes
    out_dir = config.MEDIA_DIR / "bloggers"
    start = _start_frame(product_id, persona_key)  # блогер + реальная банка (в bloggers/)
    vprompt = ("person looks into the camera and talks warmly to the viewer, natural mouth and "
               "head movement, handheld UGC selfie; keep the bottle and its label EXACTLY as in "
               "the image; no subtitles, no on-screen text")
    raw = scenes.generate_video(start, prompt=vprompt, duration=8, aspect_ratio="9:16",
                                out_name=f"blogger_{product_id}_{ts}_raw.mp4")
    clip = config.MEDIA_DIR / f"blogger_{product_id}_{ts}_raw.mp4"
    shutil.copy(raw, clip)  # в MEDIA_DIR — нужен публичный URL для липсинка
    audio = _eleven_tts(script, config.MEDIA_DIR / f"blogger_{product_id}_{ts}_vo.mp3")
    final = out_dir / f"clip_{product_id}_{ts}.mp4"
    if audio:
        dur = reels._ffprobe_dur(audio) or 8.0
        ext = reels._seg_video(clip, dur + 0.4, config.MEDIA_DIR / f"blogger_{product_id}_{ts}_ext.mp4")
        try:
            reels._lipsync(ext, audio, final)
        except Exception as e:  # липсинк упал — хотя бы примонтируем голос
            log.warning("blogger lipsync fail (%s) — монтирую аудио без синка", e)
            reels._run(["ffmpeg", "-y", "-i", str(ext), "-i", str(audio), "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-shortest", str(final)])
    else:
        shutil.copy(clip, final)
    return {"video": final, "script": script, "start_frame": str(start), "engine": "voice"}


def gen_blogger_clip(product_id: str, persona_key: str = "nutri", angle: str = "польза",
                     mode: str = "i2v") -> dict:
    """Полная цепочка UGC-блогера. Движки речи:
    'i2v' (реком.) — старт-кадр с РЕАЛЬНОЙ банкой → Veo 3 оживляет+озвучивает (голос Veo);
    't2v' — Veo рисует всё сам (быстрее, банка генерная);
    'voice' — i2v мимика + озвучка КЛОНОМ/MiniMax + липсинк (точная русская речь).
    -> {video, script, start_frame, engine}."""
    p = products.product_by_id(str(product_id)) or {}
    name = p.get("full_name", p.get("name", "supplement"))
    script = ugc_script(product_id, angle)
    log.info("blogger script (%s): %s", product_id, script)
    out_dir = config.MEDIA_DIR / "bloggers"
    out_dir.mkdir(parents=True, exist_ok=True)
    if mode == "voice":
        return _gen_voice_clip(product_id, persona_key, script, int(time.time()))
    start = None
    if mode == "i2v":
        start = _start_frame(product_id, persona_key)
        prompt = (
            "The person looks directly into the camera and speaks in RUSSIAN with clear natural lip-sync and "
            f"warm friendly intonation: \"{script}\". Keep the bottle and its label EXACTLY as in the image. "
            "Handheld UGC selfie, subtle natural movement, authentic amateur vibe. No subtitles, no on-screen text."
        )
        data = _veo3(prompt, image=start)
    else:
        prompt = veo_prompt(name, script, persona_key)
        data = _veo3(prompt)
    out = out_dir / f"clip_{product_id}_{int(time.time())}.mp4"
    out.write_bytes(data)
    return {"video": out, "script": script, "prompt": prompt,
            "start_frame": str(start) if start else None}
