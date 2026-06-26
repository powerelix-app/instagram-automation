"""Reels «Хлорофилл» (по референсу AG1) — собран из Higgsfield Kling-сцен.

7 живых сцен (output/reels05/hf/chl_*.mp4) в структуре рекламы AG1: хук (хлорофилл
льётся в бутылку) → банка → вода+мята → макро зелени → девушка пьёт → лайфстайл →
пэк-шот. Наш голос MiniMax + минимальный премиум-брендинг. 1080×1920, ~16с.
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, MONT_BLACK, INTER_SB, INTER_MED

W, H, M = 1080, 1920, 90
HF = "output/reels05/hf"
OUT = "output/reels05"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
ACCENT = (0, 210, 160)   # хлорофилл — зелёный
DDARK = (6, 20, 16)
VO = f"{HF}/vo_chl2.mp3"   # озвучка с верным ударением «хлорофи́лл»

# v2 — консистентные сцены (единый изумрудный + гладкий стакан + наша банка):
# хук льётся ИЗ нашей банки → стакан → девушка пьёт → лайфстайл → пэк-шот (запотевшая банка)
SEG = [
    ("chl2_hook", 2.8, "Сила зелени каждый день", False),
    ("chl2_glass", 1.8, None, False),
    ("chl2_drink", 3.0, None, False),
    ("chl2_life", 2.5, None, False),
    ("chl2_bottle", 3.8, None, True),
]


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wrap(d, text, font, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def overlay(path, hook, final):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # лёгкий вордмарк сверху всегда
    _spaced(d, (M, 70), "POWERELIX", _font(MONT_BLACK, 40), WHITE, 4)
    if hook:
        fh = _font(MONT_BLACK, 76)
        lines = _wrap(d, hook.upper(), fh, W - 2 * M)
        y0 = H - 360 - len(lines) * 88
        strip = Image.new("RGBA", (W, len(lines) * 88 + 56), (6, 20, 16, 130))
        ov.paste(strip, (0, y0 - 28), strip)
        y = y0
        for ln in lines:
            tw = d.textlength(ln, font=fh)
            d.text(((W - tw) / 2, y), ln, font=fh, fill=WHITE); y += 88
        d.rectangle([(W - 110) // 2, y + 4, (W + 110) // 2, y + 14], fill=ACCENT)
    if final:
        ys = np.arange(H)[:, None].astype(float)
        a = np.clip(np.where(ys > H - 560, (ys - (H - 560)) / 560 * 200, 0), 0, 200).astype("uint8")
        sh = Image.fromarray(np.repeat(a, W, axis=1).reshape(H, W))
        ov.paste(Image.new("RGBA", (W, H), (6, 20, 16, 255)), (0, 0), sh)
        d.text((M, H - 430), "ХЛОРОФИЛЛ", font=_font(MONT_BLACK, 92), fill=WHITE)
        d.text((M, H - 330), "Обновление каждый день", font=_font(INTER_SB, 44), fill=ACCENT)
        d.rectangle([M, H - 248, M + 110, H - 240], fill=ACCENT)
        d.text((M, H - 218), "Ищи в профиле →", font=_font(INTER_SB, 44), fill=WHITE)
        d.rectangle([0, H - 60, W, H], fill=DDARK)
        d.text((M, H - 46), "БАД. Не является лекарственным средством. Есть противопоказания.",
               font=_font(INTER_MED, 24), fill=(210, 228, 222))
    ov.save(path)
    return path


def build():
    segs = []
    for i, (name, dur, hook, final) in enumerate(SEG):
        ov = overlay(f"{OUT}/_co_{i}.png", hook, final)
        seg = f"{OUT}/_cs_{i}.mp4"
        run(["ffmpeg", "-y", "-t", str(dur), "-i", f"{HF}/{name}.mp4", "-i", ov,
             "-filter_complex",
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
             f"setpts=PTS-STARTPTS[v];[v][1:v]overlay=0:0,format=yuv420p[o]",
             "-map", "[o]", "-an", "-t", str(dur), *ENC, seg])
        segs.append(seg)
    lst = f"{OUT}/_concat_chl.txt"
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{os.path.basename(s)}'\n")
    silent = f"{OUT}/_chl_silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, *ENC, silent])
    vd = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "default=nw=1:nk=1", silent], capture_output=True, text=True).stdout)
    ad = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "default=nw=1:nk=1", VO], capture_output=True, text=True).stdout)
    tempo = min(max(ad / vd, 0.9), 1.5)
    out = f"{OUT}/reels_chlorophyll_ag1.mp4"
    run(["ffmpeg", "-y", "-i", silent, "-i", VO, "-filter:a", f"atempo={tempo:.4f},apad",
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", out])
    for s in segs:
        os.remove(s)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", out], capture_output=True, text=True).stdout)
    print(f"OK {out} ({d:.1f}s)")


if __name__ == "__main__":
    build()
