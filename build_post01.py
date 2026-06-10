"""Сборка карусели Пост №1 «Устаёшь не от лени» (7 слайдов, 1080x1350).

Медиа-стиль, без банки. Фото-сцены — Replicate; текст-слайды — Pillow.
Эмодзи на картинках НЕ используем (шрифты их не рисуют) — только в подписи.
"""
import os
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _scrim, brand_mark, _spaced, _gradient, _hex,
    _cutout, ARCHIVE, _load_assets,
    MONT_BLACK, INTER_SB, INTER_MED, INTER_XB, WHITE, INK, GREY, SLOGAN,
)
from ig_automation.scenes import generate_scene

ACCENT = _hex("#00C29B")  # хлорофилл (мятно-зелёный)
OUT = "output/post01"
os.makedirs(OUT, exist_ok=True)


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


def _mark(img, d, light=False):
    mk = brand_mark(38)
    img.paste(mk, (M, 52), mk)
    _spaced(d, (M + mk.width + 16, 60), "POWERELIX", _font(INTER_XB, 26),
            WHITE if light else INK, 3)


def text_slide(path, heading, bullets=None, note=None, big=None, cta=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(img, d)
    y = 280
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK)
        y += 80
    y += 36
    if big:
        fb = _font(MONT_BLACK, 86)
        for ln in _wrap(d, big, fb, W - 2 * M):
            d.text((M, y), ln, font=fb, fill=INK)
            y += 96
        y += 24
    if bullets:
        fb = _font(INTER_SB, 44)
        for b in bullets:
            d.ellipse([M, y + 16, M + 20, y + 36], fill=ACCENT)
            for i, ln in enumerate(_wrap(d, b, fb, W - 2 * M - 52)):
                d.text((M + 44, y), ln, font=fb, fill=INK)
                y += 58
            y += 20
    if note:
        y += 10
        fn = _font(INTER_MED, 36)
        for ln in _wrap(d, note, fn, W - 2 * M):
            d.text((M, y), ln, font=fn, fill=GREY)
            y += 48
    if cta:
        fc = _font(INTER_SB, 32)
        clines = _wrap(d, cta, fc, W - 2 * M)
        yy = H - 110 - len(clines) * 42
        d.rectangle([M, yy - 26, M + 110, yy - 18], fill=ACCENT)
        for ln in clines:
            d.text((M, yy), ln, font=fc, fill=INK)
            yy += 42
    img.save(path)
    return path


def product_slide(path, pid, heading, benefit, disclaimer=None):
    a = _load_assets()[str(pid)]
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(img, d)
    y = 250
    fh = _font(MONT_BLACK, 66)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK)
        y += 74
    d.rectangle([M, y + 8, M + 110, y + 16], fill=ACCENT)
    y += 34
    fb = _font(INTER_MED, 40)
    for ln in _wrap(d, benefit, fb, W - 2 * M):
        d.text((M, y), ln, font=fb, fill=INK)
        y += 52
    # банка по центру снизу (вырез, мягкая тень)
    prod = _cutout(ARCHIVE / a["image"])
    ph = int(H * 0.46)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    px, py = (W - pw) // 2, H - ph - 120
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([px + pw * 0.15, py + ph - 30, px + pw * 0.85, py + ph + 40],
                               fill=(0, 0, 0, 70))
    from PIL import ImageFilter
    img.paste(sh.filter(ImageFilter.GaussianBlur(20)), (0, 0),
              sh.filter(ImageFilter.GaussianBlur(20)))
    img.paste(prod, (px, py), prod)
    if disclaimer:
        d.text((M, H - 56), disclaimer, font=_font(INTER_MED, 24), fill=GREY)
    img.save(path)
    return path


def product_photo_slide(path, pid, scene, heading, benefit, disclaimer=None):
    a = _load_assets()[str(pid)]
    img = _scrim(_cover(Image.open(scene)), top=470, bottom=320)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
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
    prod = _cutout(ARCHIVE / a["image"])
    ph = int(H * 0.44)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    px, py = (W - pw) // 2, H - ph - 105
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([px + pw * 0.15, py + ph - 28, px + pw * 0.85, py + ph + 42],
                               fill=(0, 0, 0, 95))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    img.paste(sh, (0, 0), sh)
    img.paste(prod, (px, py), prod)
    if disclaimer:
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(228, 228, 228))
    img.save(path)
    return path


def cover(path, scene, hook, sub, tag):
    img = _scrim(_cover(Image.open(scene)), top=140, bottom=620)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
    fh = _font(MONT_BLACK, 104)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 44)
    y = H - 150 - len(lines) * 110 - 70
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 110
    d.rectangle([M, y + 6, M + 110, y + 14], fill=ACCENT)
    d.text((M, y + 30), sub, font=fs, fill=WHITE)
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path)
    return path


def photo_slide(path, scene, heading, body):
    img = _scrim(_cover(Image.open(scene)), top=140, bottom=560)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
    fh = _font(MONT_BLACK, 64)
    fb = _font(INTER_MED, 40)
    hlines = _wrap(d, heading, fh, W - 2 * M)
    blines = _wrap(d, body, fb, W - 2 * M)
    y = H - 130 - len(blines) * 52 - len(hlines) * 72 - 30
    for ln in hlines:
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 72
    d.rectangle([M, y + 4, M + 110, y + 12], fill=ACCENT)
    y += 30
    for ln in blines:
        d.text((M, y), ln, font=fb, fill=WHITE)
        y += 52
    img.save(path)
    return path


# ── сцены (переиспользуем, если уже сгенерены) ──
s1p, s6p = "output/scenes/post01_s1.png", "output/scenes/post01_s6.png"
s1 = s1p if os.path.exists(s1p) else generate_scene(
    "candid documentary lifestyle photo, tired person around 30 sitting on a sofa "
    "at home in the evening, warm dim lamp light, exhausted expression, muted warm "
    "tones, cinematic editorial, shallow depth of field, no product",
    out_name="post01_s1.png")
s6 = s6p if os.path.exists(s6p) else generate_scene(
    "macro nature photo, fresh green leaves with water droplets, soft daylight, "
    "mint green palette, clean minimal, fresh and airy",
    out_name="post01_s6.png")
s6bp = "output/scenes/post01_s6b.png"
s6b = s6bp if os.path.exists(s6bp) else generate_scene(
    "vibrant fresh scene, lush green leaves and splashing water droplets, bright "
    "energetic daylight, emerald and mint palette, clean, lots of freshness, "
    "premium product backdrop",
    out_name="post01_s6b.png")

# ── слайды ──
cover(f"{OUT}/01.png", s1, "Устаёшь не от лени",
      "5 причин, почему к вечеру ноль сил", "СОХРАНИ  →")
text_slide(f"{OUT}/02.png", "Знакомо?", bullets=[
    "Просыпаешься разбитым, будто не спал",
    "К обеду — как выжатый",
    "Кофе уже не бодрит",
    "Вечером сил только лежать",
])
text_slide(f"{OUT}/03.png", "Дело не в характере.",
           big="Телу не хватает ресурса.",
           note="Усталость — это сигнал, а не лень.")
text_slide(f"{OUT}/04.png", "Что съедает твой ресурс:", bullets=[
    "Хронический стресс",
    "Недосып",
    "Мало зелени и овощей",
    "Обезвоживание",
    "Вечная спешка",
])
text_slide(f"{OUT}/05.png", "Что реально помогает:", bullets=[
    "Сон 7–8 часов",
    "Вода в течение дня",
    "Движение каждый день",
    "Больше зелени в тарелке",
])
product_photo_slide(f"{OUT}/06.png", 1, s6b, "Хлорофилл — концентрат зелени",
                    "Зелёная перезагрузка: свежесть, бодрость и иммунитет каждый день.",
                    disclaimer="БАД. Не является лекарственным средством. Есть противопоказания.")
text_slide(f"{OUT}/07.png", "Хочешь больше энергии?",
           note="Хлорофилл POWERELIX — по ссылке в профиле. "
                "А какой из 5 сигналов про тебя? Пиши в комментариях.",
           cta="Сохрани · Подписывайся — разбираем здоровье по-простому")

# превью-контактка
prev = Image.new("RGB", (W // 3 * 4 + 50, H // 3 * 2 + 30), (255, 255, 255))
for i in range(1, 8):
    im = Image.open(f"{OUT}/{i:02d}.png").resize((W // 3, H // 3))
    r, c = divmod(i - 1, 4)
    prev.paste(im, (10 + c * (W // 3 + 10), 10 + r * (H // 3 + 10)))
prev.save(f"{OUT}/_sheet.jpg", quality=80)
print("готово:", OUT)
