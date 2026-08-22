"""Карусель №22 «Запил кофе — можно было не пить» (8 слайдов, 1080×1350).

Чем нельзя запивать витамины. Не путать с постом №8 про совместимость: там
вещества конфликтуют между собой, здесь — с напитками.

Фирменный стиль POWERELIX через brand_overlay. Акцент — глубокая мята #0E9E78:
пост про всю линейку, а не про один товар.
Hero-кадр: обложка — gemini flash-image (рука с капсулой над чашкой кофе).
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
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p22"
OUT = "output/Карусели/post22_чем_запивать"
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
    # кадр светлый (кухня в утреннем свете) — затемняем сильнее под белый текст
    img = _darken(_cover(Image.open(scene)), base=72, top=140, bottom=700)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 96)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 102 - 30 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 102
    d.rectangle([M, y + 6, M + 120, y + 16], fill=LIGHT)
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), LIGHT, 4)
    img.save(path); return path


def drink_slide(path, num, title, main, why, why_label="ПОЧЕМУ ТАК"):
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
cover(f"{OUT}/01.png", f"{SRC}/covP.png",
      "Чем нельзя запивать витамины",
      "4 напитка, из-за которых часть дозы уходит впустую")

list_slide(f"{OUT}/02.png", "Почему это важно",
           ["Усвоение решается в первые минуты — в том же желудке, "
            "куда попал напиток",
            "Часть веществ связывается прямо там и до крови просто не доходит",
            "Речь не про «вредно», а про то, что часть дозы уходит впустую"],
           note="Развести приём и напиток на час — самое дешёвое, что можно сделать.")

drink_slide(f"{OUT}/03.png", "НАПИТОК 1", "Кофе и чай",
            "Танины связывают железо ещё в желудке.",
            "Особенно растительное — из круп, зелени и бобовых: оно и так усваивается "
            "хуже мясного. Чашка вместе с едой заметно срезает то, что дойдёт до крови.")

drink_slide(f"{OUT}/04.png", "НАПИТОК 2", "Молоко",
            "Кальций и железо идут одними и теми же путями усвоения.",
            "Молоко, кефир и йогурт вместе с железом или цинком — часть не усвоится. "
            "А вот витамину D наоборот удобно: он жирорастворимый, а жир в молоке есть.")

drink_slide(f"{OUT}/05.png", "НАПИТОК 3", "Газировка",
            "Сладкая и кислая одновременно — худший вариант из всех.",
            "Кислота меняет среду в желудке, пузырьки добавляют газа, а сахар тут "
            "вообще ни к чему. Ничего из этого усвоению не помогает.")

drink_slide(f"{OUT}/06.png", "НАПИТОК 4", "Алкоголь",
            "Мешает усвоению витаминов группы B.",
            "И добавляет работы печени, которая и так занята всем, что ты принял. "
            "Совмещать приём курса с застольем смысла нет — лучше просто пропустить день.")

list_slide(f"{OUT}/07.png", "Чем запивать:",
           ["Обычной водой комнатной температуры — полный стакан",
            "Жирорастворимые A, D, E, K — во время еды, в которой есть жир",
            "Железо — вместе с витамином С: он усвоение наоборот улучшает",
            "Кофе и чай развести с приёмом хотя бы на час"],
           note="Не идеально, а стабильно: один разнесённый приём лучше, чем ни одного.")

list_slide(f"{OUT}/08.png", "Шпаргалка",
           ["Вода — всегда да",
            "Кофе, чай, молоко — развести на час",
            "Газировка и алкоголь — не в один приём",
            "Витамин С рядом с железом — наоборот, полезно"],
           note="Правило запоминается один раз и работает со всеми добавками сразу.")

print("готово →", OUT)
