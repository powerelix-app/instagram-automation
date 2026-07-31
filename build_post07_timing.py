"""Карусель №7 «Когда пить каждую добавку» (6 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay (как посты №1-6).
Акцент — фирменная мята #16FFB3 (тема общая, не про один продукт).
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
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p07"
OUT = "output/Карусели/post07_время_приёма"
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
      "Пьёшь добавки, но не чувствуешь разницы?",
      "Половина эффекта — во времени приёма. Разбираем по часам")

time_slide(f"{OUT}/02.png", "07:00", "УТРО", "натощак и с завтраком",
           [("Хлорофилл", "за 30 минут до еды, в стакане воды"),
            ("Витаминные комплексы", "с завтраком — витамины группы B бодрят, вечером могут помешать сну")])

time_slide(f"{OUT}/03.png", "13:00", "ДЕНЬ", "обязательно с едой",
           [("Омега-3", "только с приёмом пищи, где есть жир — иначе почти не усвоится"),
            ("Морской коллаген + Q10", "тоже жирорастворимый — с обедом"),
            ("Пиколинат хрома", "перед приёмом пищи")])

time_slide(f"{OUT}/04.png", "21:00", "ВЕЧЕР", "за час-два до сна",
           [("Магний + B6", "помогает мышцам и нервной системе расслабиться"),
            ("Комплекс для нервной системы", "мелисса, ромашка, 5-HTP — работают на спокойный вечер")])

rules_slide(f"{OUT}/05.png", "Четыре правила:",
            ["Жирорастворимое — только с едой",
             "Кофе снижает усвоение — разнеси на час",
             "Не пихай всё в один приём",
             "B-витамины утром, магний вечером"],
            note="И главное: регулярность важнее идеального расписания. Лучше пить не в тот "
                 "час, чем через день.")

final_slide(f"{OUT}/06.png", f"{SRC}/final.png",
            "Собери своё расписание",
            ["Хлорофилл со вкусом мяты — арт. WW621785",
             "Магний цитрат + B6, 120 капсул — арт. WW621739",
             "Полный состав и артикулы — в закреплённом посте"],
            disclaimer="БАД. Не является лекарственным средством. Имеются противопоказания.")

print("готово →", OUT)
