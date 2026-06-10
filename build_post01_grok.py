"""Пост №1 «Устаёшь не от лени» — все 7 слайдов на Grok-фонах (xAI).

Цель: «живая, красочная, сочная» карусель уровня WB-карточек хлорофилла.
Каждый слайд — отдельная Grok-сцена в единой изумрудно-мятной гамме, текст
поверх фото с лёгким тёмно-изумрудным градиентом (не глухой чёрный скрим, чтобы
фон оставался сочным). Слайд 06 — правильная банка «ХЛОРОФИЛЛ» (вырез в кэше 1.png).
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import (
    W, H, M, _font, _cover, brand_mark, _spaced,
    MONT_BLACK, INTER_SB, INTER_MED, INTER_XB, WHITE, _hex, ARCHIVE, _load_assets,
)
from ig_automation.scenes import generate_scene

GROK = "grok-imagine-image-quality"
ACCENT = _hex("#16E0A6")   # бирюза бренд-ДНК
DGREEN = (6, 16, 11)       # тёмно-изумрудный для затемнения (не чёрный — фон живёт)
GREY = (210, 214, 210)
OUT = "output/post01_grok"
SC = "output/scenes"
os.makedirs(OUT, exist_ok=True)
os.makedirs(SC, exist_ok=True)


# ── сцены Grok (кэш: повторный запуск не тратит генерации) ──
SCENES = {
    "g1": "vibrant emerald and deep green gradient background, fresh mint leaves and a "
          "dramatic clean water splash frozen mid-air in the upper area, glistening water "
          "droplets, glossy reflections, cinematic studio rim light, richly saturated juicy "
          "green tones, calm darker empty space in the lower third, premium advertising photo",
    "g2": "moody deep emerald green gradient background, a few soft mint leaves in the corners, "
          "scattered delicate water droplets, dim cinematic light, lots of calm empty dark "
          "green space in the center for text, minimal, premium, atmospheric",
    "g3": "deep dark emerald gradient, one single soft beam of light, a couple of fresh mint "
          "leaves, abundant empty negative space, very minimal clean premium, cinematic, "
          "richly saturated green",
    "g4": "dark moody emerald green background, scattered water droplets, faint mint leaves at "
          "the edges, low dramatic light, large calm empty dark green center for text, minimal "
          "premium",
    "g5": "fresh bright vibrant emerald green background, lush mint leaves and sparkling clean "
          "water droplets at the edges, energetic clean daylight, glossy, juicy saturated, calm "
          "open space in the center, premium advertising photo",
    "g6": "premium emerald and dark green gradient backdrop, a smooth flat solid wet black stone "
          "podium in the lower center, fresh vibrant mint leaves and a dynamic water splash "
          "around it, glistening droplets, glossy reflections, dramatic rim light, richly "
          "saturated juicy green, clear empty space on the podium for a product bottle, "
          "commercial advertising quality",
    "g7": "bright uplifting vibrant emerald green gradient, fresh mint leaves and a sparkling "
          "energetic water splash, glossy glistening droplets, juicy saturated, cinematic light, "
          "calm open lower area for text, premium advertising photo",
}


def scene(key):
    p = f"{SC}/grok_{key}.png"
    if os.path.exists(p):
        return p
    return str(generate_scene(SCENES[key], ratio="4:5", model=GROK, out_name=f"grok_{key}.png"))


def _readable(img, base=70, top=130, bottom=240):
    """Тёмно-изумрудное затемнение: равномерный лёгкий dim + усиление сверху/снизу.

    base — общий уровень (чем меньше, тем сочнее фон). Текст живёт в нижней зоне.
    """
    ys = np.arange(H)[:, None].astype(float)
    da = (base
          + np.where(ys < top, (top - ys) / top * 90, 0)
          + np.where(ys > H - bottom, (ys - (H - bottom)) / bottom * 150, 0))
    da = np.clip(da, 0, 232).astype("uint8")
    ovL = Image.fromarray(np.repeat(da, W, axis=1).reshape(H, W))
    return Image.composite(Image.new("RGB", (W, H), DGREEN), img.convert("RGB"), ovL)


def _wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _mark(img, d):
    mk = brand_mark(40)
    img.paste(mk, (M, 54), mk)
    _spaced(d, (M + mk.width + 16, 62), "POWERELIX", _font(INTER_XB, 26), WHITE, 3)


# ── слайды ──
def cover(path, scn, hook, sub, tag):
    img = _readable(_cover(Image.open(scn)), base=55, top=120, bottom=540)
    d = ImageDraw.Draw(img)
    _mark(img, d)
    fh = _font(MONT_BLACK, 104)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 44)
    y = H - 160 - len(lines) * 110 - 70
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 110
    d.rectangle([M, y + 6, M + 120, y + 16], fill=ACCENT)
    d.text((M, y + 32), sub, font=fs, fill=WHITE)
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path)
    return path


def text_slide(path, scn, heading, bullets=None, note=None, big=None, cta=None, base=78):
    img = _readable(_cover(Image.open(scn)), base=base)
    d = ImageDraw.Draw(img)
    _mark(img, d)
    y = 270
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 80
    y += 30
    if big:
        fb = _font(MONT_BLACK, 84)
        for ln in _wrap(d, big, fb, W - 2 * M):
            d.text((M, y), ln, font=fb, fill=ACCENT)
            y += 94
        y += 20
    if bullets:
        fb = _font(INTER_SB, 44)
        for b in bullets:
            d.ellipse([M, y + 16, M + 20, y + 36], fill=ACCENT)
            for ln in _wrap(d, b, fb, W - 2 * M - 52):
                d.text((M + 44, y), ln, font=fb, fill=WHITE)
                y += 58
            y += 20
    if note:
        y += 10
        fn = _font(INTER_MED, 36)
        for ln in _wrap(d, note, fn, W - 2 * M):
            # лёгкая подложка-тень под строкой → читаемо даже поверх яркого всплеска
            d.text((M + 2, y + 2), ln, font=fn, fill=(0, 0, 0))
            d.text((M, y), ln, font=fn, fill=WHITE)
            y += 48
    if cta:
        fc = _font(INTER_SB, 32)
        clines = _wrap(d, cta, fc, W - 2 * M)
        yy = H - 110 - len(clines) * 42
        d.rectangle([M, yy - 26, M + 110, yy - 18], fill=ACCENT)
        for ln in clines:
            d.text((M, yy), ln, font=fc, fill=WHITE)
            yy += 42
    img.save(path)
    return path


def product_slide(path, scn, pid, heading, benefit, disclaimer=None):
    img = _readable(_cover(Image.open(scn)), base=48, top=120, bottom=360)
    d = ImageDraw.Draw(img)
    _mark(img, d)
    y = 250
    fh = _font(MONT_BLACK, 64)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 72
    d.rectangle([M, y + 8, M + 110, y + 16], fill=ACCENT)
    y += 32
    fb = _font(INTER_MED, 38)
    for ln in _wrap(d, benefit, fb, W - 2 * M):
        d.text((M, y), ln, font=fb, fill=WHITE)
        y += 50
    # банка по центру снизу (правильная этикетка, кэш output/cutouts/1.png)
    cache = f"output/cutouts/{pid}.png"
    prod = Image.open(cache).convert("RGBA") if os.path.exists(cache) else None
    if prod is None:
        from rembg import remove
        a = _load_assets()[str(pid)]
        prod = remove(Image.open(ARCHIVE / a["image"]).convert("RGBA"))
        prod = prod.crop(prod.getbbox())
    ph = int(H * 0.46)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    px, py = (W - pw) // 2, H - ph - 110
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([px + pw * 0.15, py + ph - 28, px + pw * 0.85, py + ph + 42],
                               fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    img.paste(sh, (0, 0), sh)
    img.paste(prod, (px, py), prod)
    if disclaimer:
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=GREY)
    img.save(path)
    return path


# ── генерация сцен + сборка ──
print("сцены Grok…")
s = {k: scene(k) for k in SCENES}

cover(f"{OUT}/01.png", s["g1"], "Устаёшь не от лени",
      "5 причин, почему к вечеру ноль сил", "СОХРАНИ  →")
text_slide(f"{OUT}/02.png", s["g2"], "Знакомо?", bullets=[
    "Просыпаешься разбитым, будто не спал",
    "К обеду — как выжатый",
    "Кофе уже не бодрит",
    "Вечером сил только лежать",
])
text_slide(f"{OUT}/03.png", s["g3"], "Дело не в характере.",
           big="Телу не хватает ресурса.",
           note="Усталость — это сигнал, а не лень.", base=58)
text_slide(f"{OUT}/04.png", s["g4"], "Что съедает твой ресурс:", bullets=[
    "Хронический стресс",
    "Недосып",
    "Мало зелени и овощей",
    "Обезвоживание",
    "Вечная спешка",
])
text_slide(f"{OUT}/05.png", s["g5"], "Что реально помогает:", bullets=[
    "Сон 7–8 часов",
    "Вода в течение дня",
    "Движение каждый день",
    "Больше зелени в тарелке",
])
product_slide(f"{OUT}/06.png", s["g6"], 1, "Хлорофилл — концентрат зелени",
              "Зелёная перезагрузка: свежесть, бодрость и иммунитет каждый день.",
              disclaimer="БАД. Не является лекарственным средством. Есть противопоказания.")
text_slide(f"{OUT}/07.png", s["g7"], "Хочешь больше энергии?",
           note="Хлорофилл POWERELIX — по ссылке в профиле. "
                "А какой из 5 сигналов про тебя? Пиши в комментариях.",
           cta="Сохрани · Подписывайся — разбираем здоровье по-простому", base=98)

# превью-контактка
prev = Image.new("RGB", (W // 3 * 4 + 50, H // 3 * 2 + 30), (255, 255, 255))
for i in range(1, 8):
    im = Image.open(f"{OUT}/{i:02d}.png").resize((W // 3, H // 3))
    r, c = divmod(i - 1, 4)
    prev.paste(im, (10 + c * (W // 3 + 10), 10 + r * (H // 3 + 10)))
prev.save(f"{OUT}/_sheet.jpg", quality=82)
print("готово:", OUT)
