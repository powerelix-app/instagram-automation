"""Карусель №19 «Что можно не покупать» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — глубокая мята #0E9E78:
пост про всю линейку, а не про один товар, поэтому берём базовый брендовый.
Заход: сначала честно говорим, что покупать не надо, и только потом — где добавка
осмысленна. Финал без банки: продукт тут не один.
Цифры считаны по нормам РФ (магний 400 мг, железо 18 мг у женщин, витамин С 90 мг,
витамин D 10 мкг) и среднему содержанию в продуктах — округлены в тексте.
Hero-кадр: обложка — gemini flash-image (гора шпината против одной капсулы).
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#0E9E78")      # глубокая мята — базовый брендовый на светлом
LIGHT = _hex("#16FFB3")       # яркая мята — только поверх фото
DDARK = (12, 22, 18)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p19"
OUT = "output/Карусели/post19_еда"
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
    da = np.clip(da, 0, 236).astype("uint8")
    ovL = Image.fromarray(np.repeat(da, W, axis=1).reshape(H, W))
    return Image.composite(Image.new("RGB", (W, H), DDARK), img.convert("RGB"), ovL)


def cover(path, scene, hook, sub, tag="СОХРАНИ  →"):
    # фон уже тёмный (сланец) — хватает лёгкого затемнения снизу
    img = _darken(_cover(Image.open(scene)), base=26, top=100, bottom=620)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 100)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 106 - 30 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 106
    d.rectangle([M, y + 6, M + 120, y + 16], fill=LIGHT)
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), LIGHT, 4)
    img.save(path); return path


def item_slide(path, tag, title, main, why, why_label="ЧТО ЭТО ЗНАЧИТ"):
    """Слайд нутриента: метка «закрывается / почти нет» + цифра в еде."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    _spaced(d, (M, y), tag, _font(MONT_BLACK, 34), ACCENT, 4)
    y += 58
    fh = _font(MONT_BLACK, 72)
    for ln in _wrap(d, title, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 82
    d.rectangle([M, y + 8, M + 130, y + 18], fill=ACCENT)
    y += 62
    fm = _font(INTER_SB, 42)
    for ln in _wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=INK); y += 54
    y += 32
    _spaced(d, (M, y), why_label, _font(MONT_BLACK, 26), ACCENT, 3)
    y += 46
    for ln in _wrap(d, why, _font(INTER_MED, 35), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 35), fill=GREY); y += 46
    img.save(path); return path


def list_slide(path, heading, bullets, note=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 255
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 80
    d.rectangle([M, y + 10, M + 130, y + 20], fill=ACCENT)
    y += 66
    fb = _font(INTER_SB, 40)
    for b in bullets:
        d.ellipse([M, y + 14, M + 20, y + 34], fill=ACCENT)
        for ln in _wrap(d, b, fb, W - 2 * M - 56):
            d.text((M + 48, y), ln, font=fb, fill=INK); y += 52
        y += 26
    if note:
        y += 14
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/covD.png",
      "Что можно не покупать",
      "Что закрывается едой, а что почти нет")

list_slide(f"{OUT}/02.png", "Правило одной цифры",
           ["Норма — это не абстракция, её можно перевести в тарелку",
            "И сразу видно, реально ли закрыть её едой или нет",
            "Дальше считаем в продуктах, а не в миллиграммах"],
           note="Цифры округлённые: содержание зависит от сорта, почвы и способа готовки.")

item_slide(f"{OUT}/03.png", "ЗАКРЫВАЕТСЯ ЛЕГКО", "Витамин С",
           "Два апельсина или 150 г болгарского перца — и норма есть.",
           "Витамин С есть почти во всех свежих овощах и фруктах. Отдельно "
           "покупать его большинству просто незачем.")

item_slide(f"{OUT}/04.png", "ЗАКРЫВАЕТСЯ", "Омега-3",
           "100 г скумбрии дважды в неделю закрывают норму.",
           "Вопрос не в доступности, а в регулярности: ешь ли ты жирную рыбу два "
           "раза в неделю на самом деле. Если да — добавка не нужна.")

item_slide(f"{OUT}/05.png", "ПОЧТИ НЕТ", "Магний",
           "Около полкило шпината или 150 г миндаля. Каждый день.",
           "150 г миндаля — это примерно 900 ккал ради одного минерала. Поэтому "
           "магний оказывается в дефиците даже у людей с нормальным рационом.")

item_slide(f"{OUT}/06.png", "ПОЧТИ НЕТ", "Железо у женщин",
           "18 мг в день — это около 700 г говядины ежедневно.",
           "Из растительной пищи железо усваивается в разы хуже, а чай и кофе с едой "
           "режут усвоение ещё сильнее. При ежемесячных потерях дефицит набирается "
           "быстро.")

item_slide(f"{OUT}/07.png", "ПОЧТИ НЕТ", "Витамин D",
           "С октября по март солнце в наших широтах норму не даёт.",
           "Едой её закрывает только жирная рыба почти каждый день. Это тот случай, "
           "когда дефицит в России считают массовым — и не из-за питания, "
           "а из-за географии.")

list_slide(f"{OUT}/08.png", "Простое правило",
           ["Добавка нужна там, где еда объективно не дотягивает",
            "И не нужна там, где дотягивает: витамин С проще закрыть тарелкой, "
            "чем банкой",
            "Наша линейка построена вокруг первого — магний, железо, D, омега-3"],
           note="Если добавку продают «на всякий случай» — это не про здоровье, это про продажи.")

print("готово →", OUT)
