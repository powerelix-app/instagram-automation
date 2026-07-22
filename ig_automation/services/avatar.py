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


def _veo3(prompt: str, aspect: str = "9:16", duration: str = "8s") -> bytes:
    """Veo 3 fast на fal (text-to-video с речью). Возвращает mp4-байты."""
    r = requests.post("https://fal.run/fal-ai/veo3/fast",
                      headers={"Authorization": f"Key {config.FAL_KEY}", "Content-Type": "application/json"},
                      json={"prompt": prompt, "aspect_ratio": aspect, "duration": duration}, timeout=600)
    r.raise_for_status()
    url = r.json()["video"]["url"]
    try:
        v = requests.get(url, timeout=180)
        v.raise_for_status()
        data = v.content
    except Exception:  # fal.media иногда режется РКН — обход через apify
        from .. import apify
        data = apify.fetch_via_actor(url) or b""
    if not data:
        raise RuntimeError("veo3: видео не скачалось")
    return data


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


def gen_blogger_clip(product_id: str, persona_key: str = "nutri", angle: str = "польза") -> dict:
    """Полная цепочка: сценарий → Veo 3 говорящая голова. -> {video: Path, script: str}."""
    p = products.product_by_id(str(product_id)) or {}
    name = p.get("full_name", p.get("name", "supplement"))
    script = ugc_script(product_id, angle)
    log.info("blogger script (%s): %s", product_id, script)
    prompt = veo_prompt(name, script, persona_key)
    data = _veo3(prompt)
    out_dir = config.MEDIA_DIR / "bloggers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"clip_{product_id}_{int(time.time())}.mp4"
    out.write_bytes(data)
    return {"video": out, "script": script, "prompt": prompt}
