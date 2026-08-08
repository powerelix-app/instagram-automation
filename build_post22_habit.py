"""Карусель №22 «Купил. Попил неделю. Забыл» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — глубокая мята #0E9E78:
пост про всю линейку, а не про один товар.
Заход: лайфхаки, как дожить до конца курса. Продолжает мысль постов №19-20 —
эффект накопительный, но до него надо дойти.
Hero-кадр: обложка — Seedream 5 Pro (наша банка на полке; ProxyAPI на момент
сборки отдавал 402, поэтому не gemini flash-image).
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
OUT = "output/Карусели/post22_привычка"
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
    # фон светлый (полка) — затемняем сильнее под белый текст
    img = _darken(_cover(Image.open(scene)), base=74, top=140, bottom=660)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 126)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 132 - 30 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 132
    d.rectangle([M, y + 6, M + 120, y + 16], fill=LIGHT)
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), LIGHT, 4)
    img.save(path); return path


def trick_slide(path, num, title, main, why, why_label="ПОЧЕМУ РАБОТАЕТ"):
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
cover(f"{OUT}/01.png", f"{SRC}/covG.png",
      "Деньги в шкафу",
      "Почему банку не допивают и как это чинится")

list_slide(f"{OUT}/02.png", "Почему бросают",
           ["Это не лень и не память: приём добавки — новая привычка "
            "без немедленной награды",
            "Мозгу нечего закрепить: эффект накопительный, а подкрепление "
            "нужно сразу",
            "Поэтому она отваливается первой, как только сбился обычный день"],
           note="Значит, чинить надо не силу воли, а то, что вокруг привычки.")

trick_slide(f"{OUT}/03.png", "ПРИЁМ 1", "Привязать к якорю",
            "Не «утром», а «сразу после того, как включил чайник».",
            "Новая привычка не держится сама по себе — её тянет за собой уже "
            "существующее действие. Чем конкретнее якорь, тем выше шанс.")

trick_slide(f"{OUT}/04.png", "ПРИЁМ 2", "Поставить на пути",
            "Банка в шкафу проигрывает банке на столе.",
            "Мы не забываем то, что видим. Убрать «чтобы не мешало» — самый "
            "частый способ незаметно закончить курс на второй неделе.")

trick_slide(f"{OUT}/05.png", "ПРИЁМ 3", "Таблетница на неделю",
            "Сразу видно, пил сегодня или нет.",
            "Убирает вопрос «я уже принял?» — из-за него либо пропускают "
            "на всякий случай, либо пьют дважды.")

trick_slide(f"{OUT}/06.png", "ПРИЁМ 4", "Напоминание на действие",
            "«В 9:00» смахивают не глядя. «Когда сядешь завтракать» — срабатывает.",
            "Время — плохой триггер: оно наступает, когда ты занят чем-то другим. "
            "Действие — хороший: оно уже есть в твоём дне.")

trick_slide(f"{OUT}/07.png", "ПРИЁМ 5", "Правило пропуска",
            "Пропустил день — просто продолжай. Не начинай заново и не пей двойную.",
            "Курс держится не идеальностью, а возвращением. Двойная доза пропуск "
            "не догоняет, а у части веществ она ещё и лишняя.")

list_slide(f"{OUT}/08.png", "И главное",
           ["Курс удобно считать банками: 60 капсул — это месяц",
            "Смотреть на результат имеет смысл по итогу курса, а не через неделю",
            "Если банка стоит наполовину полная — вывод «не работает» "
            "просто не на чем построить"],
           note="Допитый курс честнее любого отзыва: он про тебя, а не про чужой опыт.")

print("готово →", OUT)
