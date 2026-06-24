"""Сборка карусели Пост №4 «Кожа уже не та?» (Морской коллаген, 7 слайдов, 1080x1350).

Структура как у Постов №1–3, тема — бьюти/молодость (кожа/волосы/ногти): бирюзовый
акцент (#2FCDD7). Hero-кадры — gpt-image-2 (`post04_s1.png`, `post04_s6.png`).
БАД: мягкие формулировки, дисклеймер.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, INTER_XB, WHITE, INK, GREY,
)

ACCENT = _hex("#2FCDD7")  # коллаген — бирюза (формула молодости)
DDARK = (8, 20, 22)       # тёмно-бирюзовый для затемнения фото-слайдов
OUT = "output/post04"
os.makedirs(OUT, exist_ok=True)


def _mark(img, d, light=False):
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 52), WHITE if light else INK, 3)


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


def _darken(img, base=46, top=440, bottom=120):
    ys = np.arange(H)[:, None].astype(float)
    da = (base
          + np.where(ys < top, (top - ys) / top * 90, 0)
          + np.where(ys > H - bottom, (ys - (H - bottom)) / bottom * 150, 0))
    da = np.clip(da, 0, 232).astype("uint8")
    ovL = Image.fromarray(np.repeat(da, W, axis=1).reshape(H, W))
    return Image.composite(Image.new("RGB", (W, H), DDARK), img.convert("RGB"), ovL)


def cover(path, scene, hook, sub, tag):
    img = _darken(_cover(Image.open(scene)), base=58, top=120, bottom=600)
    d = ImageDraw.Draw(img)
    _mark(img, d, light=True)
    fh = _font(MONT_BLACK, 96)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 100 - 28 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 100
    d.rectangle([M, y + 6, M + 120, y + 16], fill=ACCENT)
    y += 30
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE)
        y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path)
    return path


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
            d.text((M, y), ln, font=fb, fill=ACCENT)
            y += 96
        y += 24
    if bullets:
        fb = _font(INTER_SB, 44)
        for b in bullets:
            d.ellipse([M, y + 16, M + 20, y + 36], fill=ACCENT)
            for ln in _wrap(d, b, fb, W - 2 * M - 52):
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


def hero_product_slide(path, scene, heading, benefit, disclaimer=None):
    img = _darken(_cover(Image.open(scene)), base=40, top=420, bottom=140)
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
        d.rectangle([0, H - 64, W, H], fill=DDARK)
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(215, 228, 230))
    img.save(path)
    return path


# ── слайды ──
cover(f"{OUT}/01.png", "output/scenes/post04_s1.png",
      "Кожа уже не та?",
      "Первые признаки возраста — и что реально помогает", "СОХРАНИ  →")
text_slide(f"{OUT}/02.png", "Знакомо?", bullets=[
    "Кожа стала суше и тусклее",
    "Появились первые морщинки",
    "Волосы тусклые и ломкие",
    "Ногти слоятся",
])
text_slide(f"{OUT}/03.png", "Дело не в кремах.",
           big="Коллаген уходит с годами.",
           note="После 25 его становится меньше с каждым годом.")
text_slide(f"{OUT}/04.png", "Что разрушает коллаген:", bullets=[
    "Сахар",
    "Солнце и UV",
    "Хронический стресс",
    "Недосып",
    "Курение",
])
text_slide(f"{OUT}/05.png", "Что сохраняет молодость:", bullets=[
    "Вода и сон",
    "Защита от солнца (SPF)",
    "Меньше сахара",
    "Морской коллаген",
])
hero_product_slide(f"{OUT}/06.png", "output/scenes/post04_s6.png",
                   "Морской коллаген — формула молодости",
                   "Крепкие ногти, красивые волосы, здоровые суставы и упругая кожа.",
                   disclaimer="БАД. Не является лекарственным средством. Есть противопоказания.")
text_slide(f"{OUT}/07.png", "Хочешь сохранить молодость?",
           note="Морской коллаген POWERELIX поддержит кожу, волосы и ногти изнутри — "
                "твоя формула молодости каждый день. Ищи по ссылке в профиле.\n"
                "А какой признак возраста беспокоит тебя? Пиши в комментариях.",
           cta="Сохрани · Подписывайся — про красоту и здоровье по-простому")

prev = Image.new("RGB", (W // 3 * 4 + 50, H // 3 * 2 + 30), (255, 255, 255))
for i in range(1, 8):
    im = Image.open(f"{OUT}/{i:02d}.png").resize((W // 3, H // 3))
    r, c = divmod(i - 1, 4)
    prev.paste(im, (10 + c * (W // 3 + 10), 10 + r * (H // 3 + 10)))
prev.save(f"{OUT}/_sheet.jpg", quality=82)
print("готово:", OUT)
