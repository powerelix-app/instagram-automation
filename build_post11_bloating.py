"""Карусель №11 «Вздутие к вечеру» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — глубокая мята #0E9E78
(на светлом холсте яркая #16FFB3 кислотит, см. память).
Заход из разведки US-контента: телесный симптом, названный вслух, + разбор по часам.
Hero-кадры: обложка + финал — Seedream 5 Pro edit.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#0E9E78")      # глубокая мята — хлорофилл, читается на бежевом
DDARK = (12, 20, 18)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p11"
OUT = "output/Карусели/post11_вздутие"
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
    """Обложка: хук крупно снизу, подзаголовок под акцент-линией."""
    img = _darken(_cover(Image.open(scene)), base=58, top=120, bottom=700)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 96)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 102 - 28 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 102
    d.rectangle([M, y + 6, M + 120, y + 16], fill=ACCENT)
    y += 30
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(path); return path


def fact_slide(path, heading, bullets, note=None):
    """Слайд-факт: заголовок + маркированные тезисы."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 260
    fh = _font(MONT_BLACK, 74)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 84
    d.rectangle([M, y + 12, M + 130, y + 22], fill=ACCENT)
    y += 68
    fb = _font(INTER_SB, 40)
    for b in bullets:
        d.ellipse([M, y + 14, M + 20, y + 34], fill=ACCENT)
        for ln in _wrap(d, b, fb, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fb, fill=INK); y += 52
        y += 26
    if note:
        y += 14
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


def hour_slide(path, clock, title, main, why):
    """Слайд часа: время мятным + что делаешь + почему это надувает."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    _spaced(d, (M, y), clock, _font(MONT_BLACK, 40), ACCENT, 4)
    y += 62
    fh = _font(MONT_BLACK, 72)
    for ln in _wrap(d, title, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 82
    d.rectangle([M, y + 8, M + 130, y + 18], fill=ACCENT)
    y += 62
    fm = _font(INTER_SB, 42)
    for ln in _wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=INK); y += 54
    y += 32
    _spaced(d, (M, y), "ПОЧЕМУ НАДУВАЕТ", _font(MONT_BLACK, 26), ACCENT, 3)
    y += 46
    for ln in _wrap(d, why, _font(INTER_MED, 35), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 35), fill=GREY); y += 46
    img.save(path); return path


def final_slide(path, scene, heading, lines_txt):
    img = _darken(_cover(Image.open(scene)), base=44, top=560, bottom=160)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    y = 220
    fh = _font(MONT_BLACK, 62)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE); y += 70
    d.rectangle([M, y + 8, M + 120, y + 18], fill=ACCENT)
    y += 42
    fb = _font(INTER_MED, 34)
    for t in lines_txt:
        for ln in _wrap(d, t, fb, int(W * 0.70)):
            d.text((M, y), ln, font=fb, fill=WHITE); y += 44
        y += 14
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/covF.png",
      "К вечеру живот больше на 5 см. И это не жир",
      "Разбираем по часам, где ты его надуваешь")

fact_slide(f"{OUT}/02.png", "Жир не набирается за 12 часов",
           ["Утром живот плоский, к вечеру джинсы не сходятся — за день столько жира "
            "просто не появляется",
            "Это газ и содержимое кишечника: в норме за сутки в ЖКТ образуется около "
            "полутора литров газа",
            "Значит, дело не в весе, а в том, как именно ты ел этот день"],
           note="Дальше — четыре момента дня, когда живот получает свой объём.")

hour_slide(f"{OUT}/03.png", "07:00", "Завтрак на бегу",
           "Ешь за пять минут, стоя у плиты или на ходу по дороге.",
           "Вместе с едой глотается воздух — чем быстрее ешь, тем его больше. Он никуда "
           "не девается и остаётся в желудке и кишечнике.")

hour_slide(f"{OUT}/04.png", "13:00", "Обед и то, что рядом",
           "Газировка к еде, кофе на пустой желудок, жвачка сразу после.",
           "Пузырьки — это готовый углекислый газ прямо в желудок. А жвачка заставляет "
           "глотать воздух вхолостую, без единой калории.")

hour_slide(f"{OUT}/05.png", "20:00", "Главная еда дня — вечером",
           "Днём перекусы, а полноценная тарелка одна и поздно.",
           "Желудок опорожняется два-четыре часа. Большая порция за раз растягивает его "
           "сильнее и уходит дольше, чем два обычных приёма.")

hour_slide(f"{OUT}/06.png", "22:30", "Лёг с полным животом",
           "Ложишься спать через полчаса после ужина.",
           "Лёжа еда дольше остаётся в желудке, а газу труднее выйти. Утром — тяжесть "
           "и отсутствие аппетита, и день начинается с того же круга.")

fact_slide(f"{OUT}/07.png", "Что реально меняет картину:",
           ["Растяни приём пищи до 20 минут — без телефона и не на ходу",
            "Пей воду до еды, а не большими глотками во время",
            "Основной объём еды — на день, ужин за три часа до сна",
            "Убери газировку и жвачку: два самых недооценённых источника газа",
            "10 минут спокойной ходьбы после ужина"],
           note="Не нужно всё сразу — хватит двух пунктов, разница заметна за неделю.")

final_slide(f"{OUT}/08.png", f"{SRC}/final.png",
            "И одна ежедневная привычка",
            ["Живот меняется не от банки, а от того, как ты ешь.",
             "Но зелени в рационе не хватает почти всем — а это как раз про кишечник.",
             "Хлорофилл со вкусом мяты — простой способ добавить её в день.",
             "Хлорофилл, 500 мл — арт. WW621785"])

print("готово →", OUT)
