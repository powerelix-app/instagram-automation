"""Reels №2 «Зелёная перезагрузка» — рекламный ролик (AI-видео).

Сюжет-трансформация: усталость (тусклый холод) → ритуал хлорофилла → энергия (сочный
изумруд) → пэк-шот. 6 шотов оживляются Grok (Replicate), текст единым wordmark POWERELIX
(Montserrat Black), русский слоган-голос (OpenAI TTS). 1080×1920, ~16-18 сек.

Запуск: python build_reels02.py
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, MONT_BLACK, INTER_SB, INTER_MED

W, H, M = 1080, 1920, 90
OUT = "output/reels02"
SC = "output/scenes"
os.makedirs(OUT, exist_ok=True)
os.environ["TMPDIR"] = os.path.abspath(OUT)
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
TEAL = (22, 224, 166)
GREY = (205, 210, 205)

# (кадр, промт движения, длительность, главный_текст, слоган_снизу, дисклеймер?)
SHOTS = [
    ("r2_1tired", "subtle weary motion, she slowly blinks and breathes, very slow camera push-in, "
                  "dull cool muted tones", 3, "Утром — как выжатая?", None, False),
    ("r2_2reach", "her hand reaches out and picks up the bottle, gentle natural motion, warm light "
                  "growing", 3, "Дай телу зелёную\nперезагрузку", None, False),
    ("r2_3pour", "the green chlorophyll swirls and blooms into the water, smooth liquid motion, "
                 "sparkling droplets", 3, None, None, False),
    ("r2_4drink", "she drinks slowly with eyes closed, serene, gentle motion, colors turning rich "
                  "and vibrant emerald", 3, "Свежесть.\nБодрость.", None, False),
    ("r2_5energy", "lively energetic walking motion outdoors, hair moving in the breeze, bright "
                   "natural daylight, joyful and alive", 3, "Каждый день.", None, False),
    ("r2_6pack", "slow cinematic push-in on the bottle, water droplets sparkle, gentle", 4, None,
                 "Здоровье · Энергия · Каждый день", True),
]

VO_TEXT = ("Знакомо? Просыпаешься — а сил уже нет. Дай телу зелёную перезагрузку. "
           "Хлорофилл POWERELIX — концентрат свежести изнутри. Чистая кожа, крепкий иммунитет, "
           "лёгкость и энергия. POWERELIX — здоровье и бодрость каждый день.")
VO_VOICE = "shimmer"


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wrap(d, text, font, maxw):
    out = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=font) <= maxw:
                cur = t
            else:
                out.append(cur); cur = w
        out.append(cur)
    return out


def wordmark(d, x, y, size, color):
    _spaced(d, (x, y), "POWERELIX", _font(MONT_BLACK, size), color, 3)


def overlay_png(path, main, slogan, disclaimer):
    """Прозрачный слой: wordmark-бренд-баг сверху + текст шота снизу (+слоган/дисклеймер)."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # лёгкая тёмная подложка снизу для читаемости текста
    if main or slogan:
        ys = np.arange(H)[:, None].astype(float)
        a = np.clip(np.where(ys > H - 720, (ys - (H - 720)) / 720 * 190, 0), 0, 190).astype("uint8")
        shade = Image.fromarray(np.repeat(a, W, axis=1).reshape(H, W))
        ov.paste(Image.new("RGBA", (W, H), (4, 12, 8, 255)), (0, 0), shade)
    d = ImageDraw.Draw(ov)
    wordmark(d, M, 64, 44, WHITE)  # бренд-баг
    if main:
        fm = _font(MONT_BLACK, 92)
        lines = _wrap(d, main, fm, W - 2 * M)
        y = H - 360 - len(lines) * 100
        for ln in lines:
            d.text((M, y), ln, font=fm, fill=WHITE); y += 100
    if disclaimer:
        # финальный пэк-шот: крупный wordmark + слоган по центру снизу
        fw = _font(MONT_BLACK, 110)
        tw = d.textlength("POWERELIX", font=fw) + 8 * 3
        wordmark(d, (W - tw) // 2, H - 560, 110, WHITE)
        fs = _font(INTER_SB, 40)
        sw = d.textlength(slogan, font=fs)
        d.text(((W - sw) // 2, H - 420), slogan, font=fs, fill=TEAL)
        d.text((M, H - 70), "БАД. Не является лекарственным средством. Есть противопоказания.",
               font=_font(INTER_MED, 26), fill=GREY)
    elif slogan:
        fs = _font(INTER_SB, 44)
        d.text((M, H - 320), slogan, font=fs, fill=TEAL)
    ov.save(path)
    return path


def make_voiceover(path=f"{OUT}/voiceover.mp3"):
    if os.path.exists(path):
        return path
    import requests
    from ig_automation import config
    h = {"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": "gpt-4o-mini-tts", "voice": VO_VOICE, "input": VO_TEXT, "response_format": "mp3"}
    r = requests.post("https://api.openai.com/v1/audio/speech", headers=h, json=body, timeout=120)
    r.raise_for_status()
    open(path, "wb").write(r.content)
    return path


def _dur(f):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", f], capture_output=True, text=True)
    return float(o.stdout.strip())


def build():
    from ig_automation.scenes import _call_replicate_video
    seg_files = []
    for i, (frame, motion, dur, main, slogan, disc) in enumerate(SHOTS):
        raw = f"{OUT}/raw_{i}.mp4"
        if not os.path.exists(raw):
            print(f"шот {i} ({frame}) → видео…")
            data = _call_replicate_video(motion, image=f"{SC}/{frame}.png", duration=dur,
                                         aspect_ratio="9:16", resolution="720p")
            open(raw, "wb").write(data)
        ov = overlay_png(f"{OUT}/ov_{i}.png", main, slogan, disc)
        seg = f"{OUT}/seg_{i}.mp4"
        run(["ffmpeg", "-y", "-i", raw, "-i", ov, "-filter_complex",
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[v];"
             f"[v][1:v]overlay=0:0,format=yuv420p[o]", "-map", "[o]", "-an", *ENC, seg])
        seg_files.append(seg)
    lst = f"{OUT}/_concat.txt"
    with open(lst, "w") as f:
        for s in seg_files:
            f.write(f"file '{os.path.basename(s)}'\n")
    silent = f"{OUT}/reels02_silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, *ENC, "-movflags", "+faststart", silent])
    # озвучка должна идти ПОЧТИ во всю длину ролика (слоган ложится на пэк-шот):
    # подгоняем темп голоса ровно под длину видео (atempo, мягкий клэмп).
    vo = make_voiceover()
    vd, ad = _dur(silent), _dur(vo)
    tempo = min(max(ad / vd, 0.9), 1.5)
    out = f"{OUT}/reels02_greenreset.mp4"
    run(["ffmpeg", "-y", "-i", silent, "-i", vo, "-filter:a", f"atempo={tempo:.4f},apad",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", out])
    for s in seg_files:
        os.remove(s)
    print(f"OK {out} (видео {_dur(out):.1f}s)")
    return out


if __name__ == "__main__":
    build()
