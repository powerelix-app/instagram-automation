"""Сборка карусели Пост №1 «Устаёшь не от лени» (7 слайдов, 1080x1350).

Медиа-стиль, без банки. Фото-сцены — Replicate; текст-слайды — Pillow.
Эмодзи на картинках НЕ используем (шрифты их не рисуют) — только в подписи.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from rembg import remove


def rembg_cut(pid, src):
    """Чистый вырез банки через rembg (AI-маттинг) с кэшем в output/cutouts/."""
    os.makedirs("output/cutouts", exist_ok=True)
    cache = f"output/cutouts/{pid}.png"
    if os.path.exists(cache):
        return Image.open(cache).convert("RGBA")
    out = remove(Image.open(src).convert("RGBA"))
    out = out.crop(out.getbbox())
    out.save(cache)
    return out

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
    """Wordmark POWERELIX (Montserrat Black, без значка) — фирменное начертание.
    Белый на тёмных слайдах, чёрный на кремовых."""
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 52), WHITE if light else INK, 3)


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


DGREEN = (6, 16, 11)  # тёмно-изумрудный для затемнения (не чёрный — фон остаётся сочным)


def _greendim(img, base=48, top=120, bottom=360):
    """Лёгкое тёмно-изумрудное затемнение: фон живой, текст вверху читается."""
    ys = np.arange(H)[:, None].astype(float)
    da = (base
          + np.where(ys < top, (top - ys) / top * 90, 0)
          + np.where(ys > H - bottom, (ys - (H - bottom)) / bottom * 150, 0))
    da = np.clip(da, 0, 232).astype("uint8")
    ovL = Image.fromarray(np.repeat(da, W, axis=1).reshape(H, W))
    return Image.composite(Image.new("RGB", (W, H), DGREEN), img.convert("RGB"), ovL)


def product_photo_slide(path, pid, scene, heading, benefit, disclaimer=None):
    a = _load_assets()[str(pid)]
    img = _greendim(_cover(Image.open(scene)))
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
    prod = rembg_cut(pid, ARCHIVE / a["image"])
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


def product_real_slide(path, scene, pid, heading, benefit, disclaimer=None):
    """Девушка-фон + НАСТОЯЩАЯ банка (вырез cutouts/{pid}.png) на переднем плане —
    этикетка пиксель-в-пиксель, ИИ её не перерисовывает. Банка ставится в нижний центр
    (между раскрытыми ладонями модели)."""
    img = _greendim(_cover(Image.open(scene)), base=46, top=440, bottom=120)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
    y = 230
    fh = _font(MONT_BLACK, 60)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 68
    d.rectangle([M, y + 8, M + 110, y + 16], fill=ACCENT)
    y += 32
    fb = _font(INTER_MED, 36)
    for ln in _wrap(d, benefit, fb, int(W * 0.66)):
        d.text((M, y), ln, font=fb, fill=WHITE)
        y += 48
    prod = Image.open(f"output/cutouts/{pid}.png").convert("RGBA")
    ph = int(H * 0.52)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    px, py = (W - pw) // 2, H - ph - 120
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([px + pw * 0.1, py + ph - 30, px + pw * 0.9, py + ph + 45],
                               fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    img.paste(sh, (0, 0), sh)
    img.paste(prod, (px, py), prod)
    if disclaimer:
        d.rectangle([0, H - 64, W, H], fill=(6, 16, 11))
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(210, 214, 210))
    img.save(path)
    return path


def hero_product_slide(path, scene, heading, benefit, disclaimer=None):
    """Текст поверх hero-фото (девушка с банкой). Банка уже в кадре — композит не нужен.
    Текст слева-сверху, где фон чище; затемнение усилено вверху."""
    img = _greendim(_cover(Image.open(scene)), base=40, top=420, bottom=140)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
    y = 230
    fh = _font(MONT_BLACK, 60)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 68
    d.rectangle([M, y + 8, M + 110, y + 16], fill=ACCENT)
    y += 32
    fb = _font(INTER_MED, 36)
    for ln in _wrap(d, benefit, fb, int(W * 0.62)):
        d.text((M, y), ln, font=fb, fill=WHITE)
        y += 48
    if disclaimer:
        d.rectangle([0, H - 64, W, H], fill=(6, 16, 11))
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(210, 214, 210))
    img.save(path)
    return path


# ── AI-модель бренда: тот же портрет (assets/brand/ai_model.png) на S1 и S6 ──
GIRL_REF, BOTTLE_REF = "assets/brand/ai_model.png", "output/scenes/bottle_ref.jpg"


def _grok_edit(out_name, refs, prompt, ratio="4:5"):
    """Кэш-обёртка над xAI edits: если файл есть — берём его, иначе генерим."""
    p = f"output/scenes/{out_name}"
    if os.path.exists(p):
        return p
    from io import BytesIO
    from ig_automation.scenes import _call_xai_edit, _fit
    c = _call_xai_edit(prompt + ". no extra text, no watermark", refs, "3:4")
    _fit(Image.open(BytesIO(c)).convert("RGB"), ratio).save(p)
    return p


# ультра-реализм: фактура кожи сохраняется и в сценах (edits любит «сглаживать»)
_REAL = (" ultra realistic skin with visible pores and texture, fine flyaway hair strands, "
         "subtle natural imperfections, no skin smoothing, no retouching, hyperrealistic "
         "photograph, subtle film grain")
# слайд 1 — та же девушка, уставшая (вечер, диван)
s1 = _grok_edit("grok_s1_girl.png", [GIRL_REF],
    "Keep the exact same woman face and identity from the reference (auburn wavy hair, "
    "freckles). Full lifestyle photo: she sits tired and exhausted on a sofa at home in the "
    "evening, leaning her head back against the sofa cushion, eyes half-closed, both hands "
    "resting loosely in her lap, relaxed natural weary posture, anatomically correct hands "
    "and arms, low energy mood, warm dim lamp light, muted warm tones, cinematic editorial, "
    "shallow depth of field" + _REAL)
# слайд 6 — та же девушка держит НАШУ банку (мультиреференс: лицо + банка)
s6b = _grok_edit("grok_s6_girl.png", [GIRL_REF, BOTTLE_REF],
    "Keep the exact same woman face and identity from the FIRST reference image (auburn wavy "
    "hair, freckles). She holds in her hand the exact POWERELIX chlorophyll bottle from the "
    "SECOND reference image, presenting it toward the camera, happy healthy and energetic. "
    "Vibrant deep emerald green scene, fresh mint leaves and a dynamic clean water splash, "
    "glistening droplets, glossy, richly saturated juicy green, bright cinematic studio light, "
    "premium commercial photo. Keep the bottle shape and its green label exactly as in the "
    "second reference" + _REAL)

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
hero_product_slide(f"{OUT}/06.png", "output/scenes/s6_grok.png",
                   "Хлорофилл — концентрат зелени",
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
