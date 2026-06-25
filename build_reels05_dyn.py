"""Reels №5-DYN «Динамичный коллаген» — быстрый монтаж из УЖЕ готовых клипов.

Переиспользует output/reels05/raw_*.mp4 (Grok-видео) — новой генерации видео НЕТ.
Формат-эксперимент: быстрые склейки (~1.8с), крупный хук-текст по центру, лого только
в финале, бодрая озвучка (vo_dyn.mp3, MiniMax Lively_Girl). 1080×1920, ~11.6с.
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, MONT_BLACK, INTER_SB, INTER_MED

W, H, M = 1080, 1920, 90
OUT = "output/reels05"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
ACCENT = (70, 210, 222)
DDARK = (8, 20, 22)
VO = f"{OUT}/vo_dyn.mp3"

# (raw-клип, длительность, хук-текст, финал?)
SEG = [
    ("raw_0", 1.8, "Кожа потускнела?", False),
    ("raw_4", 1.6, "Это не возраст.", False),
    ("raw_2", 1.8, "А коллаген.", False),
    ("raw_3", 1.8, "Кожа · Волосы · Ногти", False),
    ("raw_1", 1.8, "Работает изнутри —\nне кремом", False),
    ("raw_5", 2.8, "ТВОЯ ФОРМУЛА\nМОЛОДОСТИ", True),
]


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


def overlay(path, text, final):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fh = _font(MONT_BLACK, 96 if not final else 104)
    lines = _wrap(d, text.upper(), fh, W - 2 * M)
    lh = 112 if not final else 120
    block_h = len(lines) * lh
    y0 = (H - block_h) // 2 - 60
    # тёмная плашка-подложка под текст (читаемость + «панч»)
    pad = 34
    top = y0 - pad
    bot = y0 + block_h + pad
    strip = Image.new("RGBA", (W, bot - top), (8, 20, 22, 150))
    ov.paste(strip, (0, top), strip)
    y = y0
    for ln in lines:
        tw = d.textlength(ln, font=fh)
        d.text(((W - tw) / 2, y), ln, font=fh, fill=WHITE)
        y += lh
    # акцентная черта под блоком
    d.rectangle([(W - 120) // 2, bot + 6, (W + 120) // 2, bot + 16], fill=ACCENT)
    if final:
        # лого по центру сверху
        fw = _font(MONT_BLACK, 50)
        lw = d.textlength("POWERELIX", font=fw) + 9 * 8
        _spaced(d, ((W - lw) / 2, 120), "POWERELIX", fw, WHITE, 8)
        # CTA снизу
        cta = "Ищи в профиле →"
        fc = _font(INTER_SB, 44)
        d.text(((W - d.textlength(cta, font=fc)) / 2, H - 300), cta, font=fc, fill=ACCENT)
        d.rectangle([0, H - 60, W, H], fill=DDARK)
        d.text((M, H - 46), "БАД. Не является лекарственным средством. Есть противопоказания.",
               font=_font(INTER_MED, 24), fill=(215, 228, 230))
    ov.save(path)
    return path


def build():
    segs = []
    for i, (clip, dur, text, final) in enumerate(SEG):
        ov = overlay(f"{OUT}/dov_{i}.png", text, final)
        seg = f"{OUT}/dseg_{i}.mp4"
        run(["ffmpeg", "-y", "-t", str(dur), "-i", f"{OUT}/{clip}.mp4", "-i", ov,
             "-filter_complex",
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
             f"setpts=PTS-STARTPTS[v];[v][1:v]overlay=0:0,format=yuv420p[o]",
             "-map", "[o]", "-an", "-t", str(dur), *ENC, seg])
        segs.append(seg)
    lst = f"{OUT}/_concat_dyn.txt"
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{os.path.basename(s)}'\n")
    silent = f"{OUT}/reels05_dyn_silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, *ENC, silent])
    out = f"{OUT}/reels05_dynamic.mp4"
    run(["ffmpeg", "-y", "-i", silent, "-i", VO, "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", out])
    for s in segs:
        os.remove(s)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", out], capture_output=True, text=True).stdout.strip()
    print(f"OK {out} ({float(d):.1f}s)")


if __name__ == "__main__":
    build()
