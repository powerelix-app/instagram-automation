"""Карусель «5 признаков, что тебе не хватает магния» (6 слайдов, 1080×1350).

Фирменный стиль POWERELIX (как посты №1-4): бежевый холст, чёрный вордмарк,
Montserrat Black заголовки, буллеты с акцентными точками. Акцент магния — #8975BF.
Hero-кадры сгенерированы nano-banana-pro (2K) — обложка и продуктовый слайд.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#8975BF")          # магний — фиолетовый
DDARK = (14, 10, 22)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/mg_frames"
OUT = "output/Карусель_магний"
os.makedirs(OUT, exist_ok=True)


def _mark(d, light=False):
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 52), WHITE if light else INK, 3)


def _wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
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


def cover(path, scene, hook, sub, tag="СОХРАНИ  →"):
    img = _darken(_cover(Image.open(scene)), base=58, top=120, bottom=600)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 96)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 100 - 28 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 100
    d.rectangle([M, y + 6, M + 120, y + 16], fill=ACCENT)
    y += 30
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path); return path


def text_slide(path, heading, bullets=None, note=None, big=None, cta=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 280
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 80
    y += 36
    if big:
        fb = _font(MONT_BLACK, 86)
        for ln in _wrap(d, big, fb, W - 2 * M):
            d.text((M, y), ln, font=fb, fill=ACCENT); y += 96
        y += 24
    if bullets:
        fb = _font(INTER_SB, 44)
        for b in bullets:
            d.ellipse([M, y + 16, M + 20, y + 36], fill=ACCENT)
            for ln in _wrap(d, b, fb, W - 2 * M - 52):
                d.text((M + 44, y), ln, font=fb, fill=INK); y += 58
            y += 20
    if note:
        y += 10
        fn = _font(INTER_MED, 36)
        for ln in _wrap(d, note, fn, W - 2 * M):
            d.text((M, y), ln, font=fn, fill=GREY); y += 48
    if cta:
        fc = _font(INTER_SB, 32)
        clines = _wrap(d, cta, fc, W - 2 * M)
        yy = H - 110 - len(clines) * 42
        d.rectangle([M, yy - 26, M + 110, yy - 18], fill=ACCENT)
        for ln in clines:
            d.text((M, yy), ln, font=fc, fill=INK); yy += 42
    img.save(path); return path


def hero_product_slide(path, scene, heading, benefit, disclaimer=None):
    img = _darken(_cover(Image.open(scene)), base=40, top=420, bottom=140)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    y = 230
    fh = _font(MONT_BLACK, 60)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE); y += 68
    d.rectangle([M, y + 8, M + 110, y + 16], fill=ACCENT)
    y += 32
    fb = _font(INTER_MED, 36)
    for ln in _wrap(d, benefit, fb, int(W * 0.62)):
        d.text((M, y), ln, font=fb, fill=WHITE); y += 48
    if disclaimer:
        d.rectangle([0, H - 64, W, H], fill=DDARK)
        d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(220, 214, 230))
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/01_hook.png",
      "5 признаков, что тебе не хватает магния",
      "Проверь себя — большинство узнаёт минимум три")

text_slide(f"{OUT}/02.png", "Первые три:",
           bullets=["Судороги в икрах по ночам",
                    "Дёргается веко",
                    "Тянет на шоколад"],
           note="Магний участвует в расслаблении мышц и нервно-мышечной передаче — "
                "поэтому тело сигналит именно так.")

text_slide(f"{OUT}/03.png", "И ещё два:",
           bullets=["Долго не можешь уснуть",
                    "«На взводе» без причины"],
           note="Без магния нервной системе сложнее переходить в режим отдыха.")

text_slide(f"{OUT}/04.png", "Что вымывает магний:",
           bullets=["Хронический стресс", "Кофе и сахар", "Спорт и обильный пот",
                    "Недосып", "Алкоголь"])

text_slide(f"{OUT}/05.png", "Что делать по порядку:",
           bullets=["Сдать анализ — магний и B6",
                    "Наладить сон, убрать кофе после 16:00",
                    "И только потом — добавка"],
           note="Добавка не компенсирует недосып и стресс. Она работает как поддержка, "
                "когда база налажена.",
           cta="Листай дальше — что выбрать")

hero_product_slide(f"{OUT}/06.png", f"{SRC}/06_product.png",
                   "Магний цитрат + B6",
                   "Цитрат — хорошо усваиваемая форма. B6 помогает усвоению. "
                   "120 капсул на длительный курс. Артикул WW621739",
                   disclaimer="БАД. Не является лекарственным средством. Имеются противопоказания.")

print("готово →", OUT)
