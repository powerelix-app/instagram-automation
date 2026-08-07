"""Карусель №20 «Сначала анализы, потом банка» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — приглушённый сине-бирюзовый
#1F6F8B: пост про всю линейку, лабораторная тема, поэтому берём холодный, а не
продуктовый цвет.
Заход: пост откладывает покупку и именно поэтому вызывает доверие. Продолжение
поста №19 «Что можно не покупать».
⚠️ Нигде не ставим диагнозов и не назначаем дозы — только «обсудить с врачом».
Hero-кадр: обложка — gemini flash-image (пробирки в штативе).
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#1F6F8B")      # приглушённый сине-бирюзовый — лабораторная тема
LIGHT = _hex("#7FC4DA")       # светлее — для акцентов поверх фото
DDARK = (10, 20, 26)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p20"
OUT = "output/Карусели/post20_анализы"
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
    # фон светлый (лаборатория) — затемняем сильнее под белый текст
    img = _darken(_cover(Image.open(scene)), base=70, top=140, bottom=680)
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


def test_slide(path, num, title, main, why, why_label="ЗАЧЕМ ИМЕННО ОН"):
    """Слайд показателя: номер + название + суть + зачем."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    _spaced(d, (M, y), num, _font(MONT_BLACK, 34), ACCENT, 4)
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
cover(f"{OUT}/01.png", f"{SRC}/covA.png",
      "Сначала анализы, потом банка",
      "Пять показателей, которые стоит знать до покупки")

list_slide(f"{OUT}/02.png", "Зачем вообще",
           ["Добавка вслепую — это лотерея: половину купишь зря",
            "А реальный дефицит при этом так и останется незакрытым",
            "Один разбор анализов стоит дешевле, чем три банки наугад"],
           note="Ниже — минимум, с которого имеет смысл начинать разговор с врачом.")

test_slide(f"{OUT}/03.png", "ПОКАЗАТЕЛЬ 1", "Ферритин, а не гемоглобин",
           "Гемоглобин падает последним — когда запасы железа уже исчерпаны.",
           "Ферритин показывает запас, а не текущий расход. Можно годами ходить "
           "с «хорошим гемоглобином» и пустым складом — отсюда усталость, "
           "выпадение волос и одышка на лестнице.")

test_slide(f"{OUT}/04.png", "ПОКАЗАТЕЛЬ 2", "25(OH)D",
           "Тот самый витамин D — и единственный, где доза зависит от исходного "
           "уровня.",
           "По нему дефицит в России считают массовым, и не из-за питания, "
           "а из-за географии. Пить наугад тут особенно бессмысленно: разброс "
           "между людьми огромный.")

test_slide(f"{OUT}/05.png", "ПОКАЗАТЕЛЬ 3", "Витамин B12",
           "Особенно если мало мяса или есть проблемы с желудком.",
           "Дефицит подкрадывается годами и маскируется под усталость и туман "
           "в голове. А запас в печени держится долго — поэтому симптомы приходят "
           "поздно, когда дефицит уже глубокий.")

test_slide(f"{OUT}/06.png", "ПОКАЗАТЕЛЬ 4", "ТТГ",
           "Щитовидная железа даёт ровно ту же картину, что «нехватка витаминов».",
           "Усталость, набор веса, выпадение волос, зябкость — всё совпадает. "
           "И проверяется одним анализом. Обидно год пить добавки там, где вопрос "
           "был не в них.")

test_slide(f"{OUT}/07.png", "ПОКАЗАТЕЛЬ 5", "Общий анализ крови",
           "Базовая картина: есть ли вообще смысл искать дефициты.",
           "Самый дешёвый и самый недооценённый пункт списка. Иногда он сразу "
           "показывает, что причина в другом — и дальше искать не нужно.")

list_slide(f"{OUT}/08.png", "Как читать результат",
           ["«В пределах нормы» и «оптимально» — не одно и то же",
            "Разбирать с врачом, а не с интернетом и не с продавцом",
            "Повторить через 8–12 недель приёма — иначе непонятно, работает ли"],
           note="Когда цифры на руках, вопрос «что купить» отпадает сам: становится видно, "
                "чего не хватает именно тебе.")

print("готово →", OUT)
