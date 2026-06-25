"""Reels №5-TALK «Говорящая голова» (коллаген) — формат-эксперимент.

Модель говорит В камеру (latentsync-липсинк по голосу MiniMax). Сверху хук-текст в
первой секунде, снизу — продукт+CTA в конце, плюс короткий пэк-шот банки. 1080×1920.
Вход: output/reels05/talk/lipsync.mp4 (+ co_6pack.png для пэк-шота).
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, MONT_BLACK, INTER_SB, INTER_MED

W, H, M = 1080, 1920, 90
T = "output/reels05/talk"
OUT = "output/reels05"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
ACCENT = (70, 210, 222)
DDARK = (8, 20, 22)
LS = f"{T}/lipsync.mp4"
PACK = "output/scenes/co_6pack.png"


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


def _wm(d, center_x=False, y=64):
    fw = _font(MONT_BLACK, 44)
    x = M if not center_x else (W - d.textlength("POWERELIX", font=fw) - 8 * 8) / 2
    _spaced(d, (x, y), "POWERELIX", fw, WHITE, 8)


def make_wm():
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); _wm(ImageDraw.Draw(ov)); ov.save(f"{T}/o_wm.png"); return f"{T}/o_wm.png"


def make_hook(text):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    fh = _font(MONT_BLACK, 86)
    lines = _wrap(d, text.upper(), fh, W - 2 * M)
    bh = len(lines) * 100
    y0 = H - 470 - bh
    strip = Image.new("RGBA", (W, bh + 60), (8, 20, 22, 160)); ov.paste(strip, (0, y0 - 30), strip)
    y = y0
    for ln in lines:
        tw = d.textlength(ln, font=fh); d.text(((W - tw) / 2, y), ln, font=fh, fill=WHITE); y += 100
    d.rectangle([(W - 120) // 2, y + 6, (W + 120) // 2, y + 16], fill=ACCENT)
    ov.save(f"{T}/o_hook.png"); return f"{T}/o_hook.png"


def make_prod():
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    ys = np.arange(H)[:, None].astype(float)
    a = np.clip(np.where(ys > H - 560, (ys - (H - 560)) / 560 * 190, 0), 0, 190).astype("uint8")
    sh = Image.fromarray(np.repeat(a, W, axis=1).reshape(H, W))
    ov.paste(Image.new("RGBA", (W, H), (8, 20, 22, 255)), (0, 0), sh)
    d.text((M, H - 420), "Морской коллаген", font=_font(MONT_BLACK, 70), fill=WHITE)
    d.text((M, H - 348), "Пауэрликс", font=_font(MONT_BLACK, 70), fill=ACCENT)
    d.rectangle([M, H - 250, M + 110, H - 242], fill=ACCENT)
    d.text((M, H - 220), "Ищи в профиле →", font=_font(INTER_SB, 46), fill=WHITE)
    d.rectangle([0, H - 60, W, H], fill=DDARK)
    d.text((M, H - 46), "БАД. Не является лекарственным средством. Есть противопоказания.",
           font=_font(INTER_MED, 24), fill=(215, 228, 230))
    ov.save(f"{T}/o_prod.png"); return f"{T}/o_prod.png"


def make_pack_overlay():
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _wm(d, center_x=True, y=130)
    fh = _font(MONT_BLACK, 100)
    for i, ln in enumerate(["ФОРМУЛА", "МОЛОДОСТИ"]):
        d.text(((W - d.textlength(ln, font=fh)) / 2, H - 560 + i * 110), ln, font=fh, fill=WHITE)
    d.rectangle([(W - 120) // 2, H - 330, (W + 120) // 2, H - 320], fill=ACCENT)
    cta = "Ищи в профиле →"; fc = _font(INTER_SB, 46)
    d.text(((W - d.textlength(cta, font=fc)) / 2, H - 290), cta, font=fc, fill=ACCENT)
    d.rectangle([0, H - 60, W, H], fill=DDARK)
    d.text((M, H - 46), "БАД. Не является лекарственным средством. Есть противопоказания.",
           font=_font(INTER_MED, 24), fill=(215, 228, 230))
    ov.save(f"{T}/o_pack.png"); return f"{T}/o_pack.png"


def build():
    ad = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "default=nw=1:nk=1", LS], capture_output=True, text=True).stdout.strip())
    wm, hook, prod = make_wm(), make_hook("Перестань втирать коллаген"), make_prod()
    # говорящая голова с тайм-оверлеями (аудио сохраняем)
    talk = f"{OUT}/_talk_body.mp4"
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[b];"
          f"[b][1:v]overlay=0:0[w];"
          f"[w][2:v]overlay=0:0:enable='between(t,0,2.3)'[h];"
          f"[h][3:v]overlay=0:0:enable='gte(t,{ad-3.5:.2f})'[v]")
    run(["ffmpeg", "-y", "-i", LS, "-i", wm, "-i", hook, "-i", prod,
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a", *ENC, "-c:a", "aac", "-b:a", "160k", talk])
    # пэк-шот банки 2.2с (без голоса → тихая дорожка)
    pov = make_pack_overlay(); pack = f"{OUT}/_talk_pack.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-t", "2.2", "-i", PACK, "-i", pov,
         "-f", "lavfi", "-t", "2.2", "-i", "anullsrc=r=44100:cl=stereo",
         "-filter_complex",
         f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[b];"
         f"[b][1:v]overlay=0:0,format=yuv420p[v]",
         "-map", "[v]", "-map", "2:a", *ENC, "-c:a", "aac", "-b:a", "160k", "-shortest", pack])
    # склейка
    out = f"{OUT}/reels05_talking.mp4"
    run(["ffmpeg", "-y", "-i", talk, "-i", pack, "-filter_complex",
         "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
         "-map", "[v]", "-map", "[a]", *ENC, "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", out])
    for f in (talk, pack):
        os.remove(f)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", out], capture_output=True, text=True).stdout.strip())
    print(f"OK {out} ({d:.1f}s)")


if __name__ == "__main__":
    build()
