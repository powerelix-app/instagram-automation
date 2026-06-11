"""Reels №1 «3 ошибки, из-за которых витамины не работают» — ДВА способа.

Способ A (motion): стоп-кадры нашей AI-модели + текст + плавный zoom (ffmpeg).
Способ B (ai-video): Grok image→video оживляет модель по битам + текст + склейка.
Оба — 1080×1920 mp4, ~13 сек. Звук (трендовый) добавляется в приложении IG.

Запуск:  python build_reels01.py motion   |   python build_reels01.py aivideo   |   both
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import _font, _spaced, brand_mark, MONT_BLACK, INTER_SB, INTER_XB, INTER_MED

W, H, M = 1080, 1920, 90
OUT = "output/reels01"
os.makedirs(OUT, exist_ok=True)
# ffmpeg-temp на большой диск (маленький tmpfs сессии переполняется и бьёт вывод)
os.environ["TMPDIR"] = os.path.abspath(OUT)
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p"]
WHITE = (255, 255, 255)
TEAL = (22, 224, 166)
RED = (255, 99, 92)
GREY = (200, 205, 200)

# (имя_стопкадра, верхняя_метка, главный_текст, плохое, хорошее) — None пропускается
BEATS = [
    ("emo_neutral",  None,        "Пьёшь витамины,\nа толку ноль?", None, "3 ошибки ↓"),
    ("emo_calm",     "ОШИБКА 1",  "Магний",            "утром",            "лучше вечером"),
    ("emo_neutral",  "ОШИБКА 2",  "Витамин D",         "запиваешь водой",  "только с жирной пищей"),
    ("emo_energetic","ОШИБКА 3",  "Глотаешь всё разом","в одной горсти",   "разнеси по времени"),
    ("grok_s6_girl", None,        "Сохрани,\nчтобы не забыть", None, "POWERELIX · здоровье по-простому"),
]
DUR = [2.6, 2.7, 2.7, 2.7, 3.2]
SRC = "output/scenes"


def _cover(im):
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _scrim(img, top=320, bottom=760):
    import numpy as np
    ys = np.arange(H)[:, None].astype(float)
    da = (np.where(ys < top, (top - ys) / top * 150, 0)
          + np.where(ys > H - bottom, (ys - (H - bottom)) / bottom * 210, 0))
    da = np.clip(da, 0, 225).astype("uint8")
    ovL = Image.fromarray(np.repeat(da, W, axis=1).reshape(H, W))
    return Image.composite(Image.new("RGB", (W, H), (4, 12, 8)), img.convert("RGB"), ovL)


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


def compose(beat, idx):
    name, tag, main, bad, good = beat
    base = Image.open(f"{SRC}/{name}.png")
    img = _scrim(_cover(base))
    d = ImageDraw.Draw(img)
    # бренд-марк сверху
    mk = brand_mark(48); img.paste(mk, (M, 70), mk)
    _spaced(d, (M + mk.width + 18, 80), "POWERELIX", _font(INTER_XB, 32), WHITE, 3)
    # нижний блок текста
    y = H - 720
    if tag:
        _spaced(d, (M, y), tag, _font(INTER_XB, 40), TEAL, 4); y += 86
    fm = _font(MONT_BLACK, 96)
    for ln in _wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=WHITE); y += 104
    y += 26
    if bad:
        fb = _font(INTER_SB, 54)
        d.text((M, y), "✕  " + bad, font=fb, fill=RED); y += 74
    if good:
        fg = _font(INTER_SB, 54)
        tag_col = TEAL
        prefix = "→  " if (bad or tag) else ""
        d.text((M, y), prefix + good, font=fg, fill=tag_col); y += 74
    if idx == len(BEATS) - 1:
        d.text((M, H - 130), "БАД. Не является лекарственным средством. Есть противопоказания.",
               font=_font(INTER_MED, 26), fill=GREY)
    p = f"{OUT}/beat_{idx}.png"
    img.save(p)
    return p


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build_motion():
    print("motion: компоную стоп-кадры…")
    stills = [compose(b, i) for i, b in enumerate(BEATS)]
    seg_files = []
    for i, (still, dur) in enumerate(zip(stills, DUR)):
        seg = f"{OUT}/seg_{i}.mp4"
        frames = int(dur * 30)
        # медленный zoom-in (Ken Burns)
        vf = (f"scale=1350:2400,zoompan=z='min(zoom+0.0006,1.12)':d={frames}"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,format=yuv420p")
        run(["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", still,
             "-vf", vf, *ENC, "-r", "30", seg])
        seg_files.append(seg)
    # склейка с быстрым кроссфейдом через concat (хард-каты под бит — норм для Reels)
    lst = f"{OUT}/_concat.txt"
    with open(lst, "w") as f:
        for s in seg_files:
            f.write(f"file '{os.path.basename(s)}'\n")
    out = f"{OUT}/reels01_motion.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         *ENC, "-movflags", "+faststart", out])
    for s in seg_files:
        os.remove(s)
    print("OK", out)
    return out


# биты для AI-видео: (стартовый кадр, промт движения, длительность)
AI_CLIPS = [
    ("emo_neutral", "she looks at the camera with a slight questioning concerned expression, "
                    "subtle head tilt, natural micro-movements, gentle slow camera push-in", 4),
    ("emo_energetic", "she shakes her head slightly no, then gives a confident reassuring nod, "
                      "light hand gesture, natural lively motion", 4),
    ("grok_s6_girl", "she smiles warmly holding the chlorophyll bottle, gentle natural motion, "
                     "subtle sparkle on water droplets, slow camera push-in", 5),
]
AI_TEXT = [  # текст-оверлей на каждый клип (главное, плохое, хорошее, tag)
    (None, "Пьёшь витамины, а толку ноль?", None, "3 ошибки ↓", None),
    ("ОШИБКИ", "Магний утром · D без еды · всё разом", None, "→ делай наоборот", None),
    (None, "Сохрани, чтобы не забыть", None, "POWERELIX · здоровье по-простому", "disc"),
]


def build_aivideo():
    from ig_automation.scenes import _call_xai_video
    print("ai-video: генерю клипы Grok…")
    seg_files = []
    for i, (frame, prompt, dur) in enumerate(AI_CLIPS):
        raw = f"{OUT}/ai_raw_{i}.mp4"
        if not os.path.exists(raw):
            data = _call_xai_video(prompt, image=f"{SRC}/{frame}.png", duration=dur,
                                   aspect_ratio="9:16", resolution="720p")
            open(raw, "wb").write(data)
            print(f"  клип {i} готов ({len(data)//1024} KB)")
        # текст-оверлей透明 PNG
        tag, main, bad, good, disc = AI_TEXT[i]
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        # лёгкая тёмная подложка снизу для читаемости
        import numpy as np
        ys = np.arange(H)[:, None].astype(float)
        a = np.clip(np.where(ys > H - 720, (ys - (H - 720)) / 720 * 200, 0), 0, 200).astype("uint8")
        shade = Image.fromarray(np.repeat(a, W, axis=1).reshape(H, W))
        ov.paste(Image.new("RGBA", (W, H), (4, 12, 8, 255)), (0, 0), shade)
        d = ImageDraw.Draw(ov)
        mk = brand_mark(48); ov.paste(mk, (M, 70), mk)
        _spaced(d, (M + mk.width + 18, 80), "POWERELIX", _font(INTER_XB, 32), WHITE, 3)
        y = H - 640
        if tag:
            _spaced(d, (M, y), tag, _font(INTER_XB, 40), TEAL, 4); y += 86
        fm = _font(MONT_BLACK, 92)
        for ln in _wrap(d, main, fm, W - 2 * M):
            d.text((M, y), ln, font=fm, fill=WHITE); y += 100
        y += 20
        if good:
            d.text((M, y), good, font=_font(INTER_SB, 50), fill=TEAL); y += 70
        if disc:
            d.text((M, H - 130), "БАД. Не является лекарственным средством. Есть противопоказания.",
                   font=_font(INTER_MED, 26), fill=GREY)
        ovp = f"{OUT}/ai_ov_{i}.png"; ov.save(ovp)
        seg = f"{OUT}/ai_seg_{i}.mp4"
        run(["ffmpeg", "-y", "-i", raw, "-i", ovp, "-filter_complex",
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[v];"
             f"[v][1:v]overlay=0:0,format=yuv420p[o]",
             "-map", "[o]", "-an", *ENC, seg])
        seg_files.append(seg)
    lst = f"{OUT}/_concat_ai.txt"
    with open(lst, "w") as f:
        for s in seg_files:
            f.write(f"file '{os.path.basename(s)}'\n")
    out = f"{OUT}/reels01_aivideo.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         *ENC, "-movflags", "+faststart", out])
    print("OK", out)
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("motion", "both"):
        build_motion()
    if mode in ("aivideo", "both"):
        build_aivideo()
