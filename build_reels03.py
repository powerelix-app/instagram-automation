"""Reels №3 «Женский ритуал» (Инозитол) — спокойный сенсорный рекламный ролик.

ASMR/self-care стиль: мягкий свет, ритуал, спокойствие → женский баланс. 6 кадров
оживляются Grok (Replicate, медленное нежное движение), минимум текста, мягкая
озвучка (OpenAI TTS). 1080×1920, ~18 сек. Музыку добавить в IG.
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, MONT_BLACK, INTER_SB, INTER_MED

W, H, M = 1080, 1920, 90
OUT = "output/reels03"
SC = "output/scenes"
os.makedirs(OUT, exist_ok=True)
os.environ["TMPDIR"] = os.path.abspath(OUT)
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
PINK = (250, 80, 152)
GREY = (220, 210, 214)

# (кадр, промт движения, длительность, главный_текст, слоган_снизу, дисклеймер?)
SHOTS = [
    ("ri_1calm", "very subtle gentle motion, she breathes slowly, soft hair movement, slow gentle "
                 "camera push-in, serene and calm", 3, "Минута для себя", None, False),
    ("ri_2water", "water pours smoothly into the glass, gentle flowing liquid motion, soft slow", 2,
                  None, None, False),
    ("ri_3capsule", "subtle gentle motion, soft light shifting, petals drift slightly, slow push-in",
                    2, None, None, False),
    ("ri_4take", "she gently sips water with eyes closed, calm serene slow motion", 3,
                 "Мягкий женский баланс", None, False),
    ("ri_5balance", "subtle gentle motion, soft hair movement, a calm gentle smile, slow push-in, "
                    "glowing and balanced", 3, "В балансе", None, False),
    ("ri_6pack", "very slow gentle push-in on the jar, soft light, petals drift gently", 4, None,
                 "Женский баланс · каждый день", True),
]

VO_TEXT = ("Минута для себя. Мягкая поддержка женского баланса. "
           "Инозитол POWERELIX — спокойствие и баланс каждый день.")
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
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if main or slogan or disclaimer:
        ys = np.arange(H)[:, None].astype(float)
        a = np.clip(np.where(ys > H - 700, (ys - (H - 700)) / 700 * 170, 0), 0, 170).astype("uint8")
        shade = Image.fromarray(np.repeat(a, W, axis=1).reshape(H, W))
        ov.paste(Image.new("RGBA", (W, H), (24, 8, 16, 255)), (0, 0), shade)
    d = ImageDraw.Draw(ov)
    wordmark(d, M, 64, 44, WHITE)
    if main:
        fm = _font(MONT_BLACK, 86)
        lines = _wrap(d, main, fm, W - 2 * M)
        y = H - 360 - len(lines) * 96
        for ln in lines:
            d.text((M, y), ln, font=fm, fill=WHITE); y += 96
    if disclaimer:
        fw = _font(MONT_BLACK, 104)
        tw = d.textlength("POWERELIX", font=fw) + 8 * 3
        wordmark(d, (W - tw) // 2, H - 540, 104, WHITE)
        fs = _font(INTER_SB, 40)
        sw = d.textlength(slogan, font=fs)
        d.text(((W - sw) // 2, H - 410), slogan, font=fs, fill=PINK)
        d.text((M, H - 70), "БАД. Не является лекарственным средством. Есть противопоказания.",
               font=_font(INTER_MED, 26), fill=GREY)
    elif slogan:
        d.text((M, H - 320), slogan, font=_font(INTER_SB, 44), fill=PINK)
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
    silent = f"{OUT}/reels03_silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, *ENC, "-movflags", "+faststart", silent])
    vo = make_voiceover()
    vd, ad = _dur(silent), _dur(vo)
    tempo = min(max(ad / vd, 0.9), 1.5)
    out = f"{OUT}/reels03_ritual.mp4"
    run(["ffmpeg", "-y", "-i", silent, "-i", vo, "-filter:a", f"atempo={tempo:.4f},apad",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", out])
    for s in seg_files:
        os.remove(s)
    print(f"OK {out} ({_dur(out):.1f}s)")
    return out


if __name__ == "__main__":
    build()
