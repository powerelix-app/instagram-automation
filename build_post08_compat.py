"""Карусель №8 «Какие добавки нельзя пить вместе» (6 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay (как посты №1-6).
Акцент — фирменная мята #16FFB3. Тема: совместимость добавок.
Hero-кадры: обложка + финал — Seedream 5 Pro edit.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#0E9E78")      # глубокая мята: #16FFB3 на бежевом кислотит
DDARK = (10, 20, 16)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p08"
OUT = "output/Карусели/post08_совместимость"
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
    img = _darken(_cover(Image.open(scene)), base=58, top=120, bottom=620)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 92)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 98 - 28 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 98
    d.rectangle([M, y + 6, M + 120, y + 16], fill=ACCENT)
    y += 30
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path); return path


def time_slide(path, clock, title, when, items, note=None):
    """Слайд времени приёма: часы мятным + заголовок + пары «продукт → когда»."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 240
    _spaced(d, (M, y), clock, _font(MONT_BLACK, 40), ACCENT, 4)   # 07:00 / 13:00 / 21:00
    y += 58
    d.text((M, y), title, font=_font(MONT_BLACK, 78), fill=INK)
    y += 92
    d.text((M, y), when, font=_font(INTER_MED, 36), fill=GREY)
    y += 66
    d.rectangle([M, y, M + 130, y + 10], fill=ACCENT)
    y += 54
    for name, rule in items:
        d.ellipse([M, y + 14, M + 20, y + 34], fill=ACCENT)
        fn = _font(MONT_BLACK, 46)
        for ln in _wrap(d, name, fn, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fn, fill=INK); y += 54
        fr = _font(INTER_MED, 34)
        for ln in _wrap(d, rule, fr, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fr, fill=GREY); y += 44
        y += 26
    if note:
        y += 8
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


def rules_slide(path, heading, bullets, note=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 270
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 80
    y += 40
    fb = _font(INTER_SB, 42)
    for b in bullets:
        d.ellipse([M, y + 14, M + 20, y + 34], fill=ACCENT)
        for ln in _wrap(d, b, fb, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fb, fill=INK); y += 54
        y += 22
    if note:
        y += 14
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


def final_slide(path, scene, heading, lines_txt, disclaimer):
    img = _darken(_cover(Image.open(scene)), base=44, top=520, bottom=200)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    y = 230
    fh = _font(MONT_BLACK, 62)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE); y += 70
    d.rectangle([M, y + 8, M + 120, y + 18], fill=ACCENT)
    y += 40
    fb = _font(INTER_MED, 34)
    for t in lines_txt:
        for ln in _wrap(d, t, fb, int(W * 0.74)):
            d.text((M, y), ln, font=fb, fill=WHITE); y += 44
        y += 12
    d.rectangle([0, H - 64, W, H], fill=DDARK)
    d.text((M, H - 50), disclaimer, font=_font(INTER_MED, 23), fill=(210, 226, 220))
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/cover.png",
      "Эти добавки нельзя пить вместе",
      "Пьёшь всё горстью за завтраком? Половина мешает друг другу")

def pair_slide(path, num, left, right, why, who, fix):
    """Слайд конфликтующей пары: «А ✕ Б» + три блока — почему / кого касается / что делать."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 210
    _spaced(d, (M, y), num, _font(MONT_BLACK, 36), ACCENT, 4)
    y += 56
    fp = _font(MONT_BLACK, 66)
    d.text((M, y), left, font=fp, fill=INK); y += 78
    # крест рисуем линиями: символ ✕ отсутствует в Montserrat Black
    cx, cy, r, w = M + 24, y + 30, 20, 8
    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=ACCENT, width=w)
    d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=ACCENT, width=w)
    d.text((M + 72, y), right, font=fp, fill=INK); y += 92
    d.rectangle([M, y, M + 130, y + 10], fill=ACCENT)
    y += 56

    blocks = [("ПОЧЕМУ", why), ("КОГО КАСАЕТСЯ", who), ("ЧТО ДЕЛАТЬ", fix)]
    for title, text in blocks:
        _spaced(d, (M, y), title, _font(MONT_BLACK, 27), ACCENT, 3)
        y += 46
        for ln in _wrap(d, text, _font(INTER_MED, 36), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 36), fill=INK); y += 48
        y += 34
    img.save(path); return path


pair_slide(f"{OUT}/02.png", "ПАРА 1", "КАЛЬЦИЙ", "МАГНИЙ",
           "Оба минерала двухвалентные и идут по одним и тем же транспортным путям — "
           "в один приём организм возьмёт в основном тот, которого больше.",
           "Тех, кто пьёт кальций для костей и магний для сна или от судорог — "
           "самая частая связка после 35.",
           "Кальций — днём с едой. Магний — вечером за час до сна. Разрыв минимум 2 часа.")

pair_slide(f"{OUT}/03.png", "ПАРА 2", "ЦИНК", "МЕДЬ",
           "Они используют один белок-переносчик. Высокие дозы цинка длительным курсом "
           "вытесняют медь и со временем роняют её запас.",
           "Тех, кто пьёт цинк курсами для кожи и иммунитета — особенно дозировки "
           "от 25 мг в день дольше месяца.",
           "Не в один приём. Длинный курс цинка — только вместе с медью или в готовом "
           "комплексе, где баланс уже посчитан.")

pair_slide(f"{OUT}/04.png", "ПАРА 3", "ЖЕЛЕЗО", "КОФЕ",
           "Танины из кофе и чая связывают железо прямо в кишечнике, а кальций из молочного "
           "блокирует его всасывание — усвоение падает в разы.",
           "Тех, у кого низкий ферритин: выпадают волосы, к вечеру нет сил, кружится голова. "
           "И тех, кто запивает витамины кофе.",
           "Железо — натощак с витамином C. Кофе, чай и молочное — не раньше чем через час.")

rules_slide(f"{OUT}/05.png", "А эти пары, наоборот, усиливают:",
            ["Железо + витамин C",
             "Магний + витамин B6",
             "Кальций + D3 + K2",
             "Омега-3 + жирорастворимые витамины"],
            note="В наших формулах такие пары уже собраны: магний идёт с B6, "
                 "морской коллаген — с витамином C.")

final_slide(f"{OUT}/06.png", f"{SRC}/final.png",
            "Правило простое",
            ["Дели приём на 2-3 раза в день вместо одного",
             "Магний цитрат + B6 — арт. WW621739",
             "Морской коллаген + витамин C — арт. WW621770"],
            disclaimer="БАД. Не является лекарственным средством. Имеются противопоказания.")

print("готово →", OUT)
