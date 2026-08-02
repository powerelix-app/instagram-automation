"""Карусель №12 «Это не возраст и не лень» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — синий Мужского комплекса
#213D87 (из product_assets), на бежевом холсте держит контраст.
Заход: опровержение («это не возраст») + 5 признаков + три причины.
⚠️ Никаких заявлений, что продукт поднимает тестостерон — только «участвует в синтезе».
Hero-кадры: обложка (gemini flash-image, без референса) + финал (Seedream 5 Pro edit).
"""
import os

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#213D87")      # синий Мужского комплекса
DDARK = (10, 14, 24)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p12"
OUT = "output/Карусели/post12_тестостерон"
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
    img = _darken(_cover(Image.open(scene)), base=52, top=120, bottom=700)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 100)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 40)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 106 - 30 - len(sub_lines) * 48
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 106
    d.rectangle([M, y + 6, M + 120, y + 16], fill=_hex("#5C7FE0"))  # светлее — читается на фото
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 48
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), _hex("#5C7FE0"), 4)
    img.save(path); return path


def list_slide(path, heading, bullets, note=None, numbered=False):
    """Слайд-список: заголовок + пункты (точками или цифрами)."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 250
    fh = _font(MONT_BLACK, 74)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 84
    d.rectangle([M, y + 12, M + 130, y + 22], fill=ACCENT)
    y += 68
    fb = _font(INTER_SB, 40)
    for i, b in enumerate(bullets, 1):
        if numbered:
            d.text((M, y - 4), str(i), font=_font(MONT_BLACK, 44), fill=ACCENT)
        else:
            d.ellipse([M, y + 14, M + 20, y + 34], fill=ACCENT)
        for ln in _wrap(d, b, fb, W - 2 * M - 56):
            d.text((M + 48, y), ln, font=fb, fill=INK); y += 52
        y += 26
    if note:
        y += 14
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


def cause_slide(path, num, title, main, why):
    """Слайд причины: номер + заголовок + суть + механизм."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    _spaced(d, (M, y), num, _font(MONT_BLACK, 34), ACCENT, 4)
    y += 58
    fh = _font(MONT_BLACK, 74)
    for ln in _wrap(d, title, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 84
    d.rectangle([M, y + 8, M + 130, y + 18], fill=ACCENT)
    y += 62
    fm = _font(INTER_SB, 42)
    for ln in _wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=INK); y += 54
    y += 32
    _spaced(d, (M, y), "КАК ЭТО РАБОТАЕТ", _font(MONT_BLACK, 26), ACCENT, 3)
    y += 46
    for ln in _wrap(d, why, _font(INTER_MED, 35), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 35), fill=GREY); y += 46
    img.save(path); return path


def final_slide(path, scene, heading, lines_txt):
    img = _darken(_cover(Image.open(scene)), base=48, top=560, bottom=160)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    y = 220
    fh = _font(MONT_BLACK, 62)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=WHITE); y += 70
    d.rectangle([M, y + 8, M + 120, y + 18], fill=_hex("#5C7FE0"))
    y += 42
    fb = _font(INTER_MED, 34)
    for t in lines_txt:
        for ln in _wrap(d, t, fb, int(W * 0.52)):
            d.text((M, y), ln, font=fb, fill=WHITE); y += 44
        y += 14
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/covA.png",
      "Это не возраст и не лень",
      "5 признаков, что тестостерон пошёл вниз")

list_slide(f"{OUT}/02.png", "Сначала — честно",
           ["После 30 тестостерон снижается примерно на 1% в год. Это норма, "
            "так у всех",
            "Вопрос не в самом снижении, а в его скорости",
            "А скорость задаёт образ жизни, а не паспорт"],
           note="Дальше — по каким признакам это видно и что на это влияет.")

list_slide(f"{OUT}/03.png", "5 признаков:",
           ["Пропал драйв: то, что раньше заводило, стало безразлично",
            "После зала восстанавливаешься не два дня, а неделю",
            "Живот растёт при том же питании и тех же тренировках",
            "Сон стал поверхностным, просыпаешься разбитым",
            "Раздражает то, что раньше вообще не задевало"],
           note="Один пункт — ещё ничего. Три и больше — повод разобраться.",
           numbered=True)

cause_slide(f"{OUT}/04.png", "ПРИЧИНА 1", "Сон",
            "Основная часть тестостерона вырабатывается ночью, во сне.",
            "В эксперименте у здоровых молодых мужчин неделя сна по пять часов "
            "уронила уровень на 10–15%. Одна неделя — и как будто прибавилось "
            "десять лет.")

cause_slide(f"{OUT}/05.png", "ПРИЧИНА 2", "Живот",
            "Жир на животе — не просто запас, а активная ткань.",
            "В нём работает фермент, который превращает тестостерон в эстроген. "
            "Чем больше живот — тем ниже тестостерон, а чем ниже тестостерон — "
            "тем легче растёт живот. Круг.")

cause_slide(f"{OUT}/06.png", "ПРИЧИНА 3", "Дефициты",
            "Цинк, витамин D и магний участвуют в синтезе тестостерона.",
            "Цинк заметно теряется с потом, поэтому у тренирующихся расход выше. "
            "Витамина D в наших широтах не хватает большинству просто по факту "
            "географии.")

list_slide(f"{OUT}/07.png", "Что делать:",
           ["Спать 7–8 часов — это не совет про режим, это база выработки",
            "Силовые 2–3 раза в неделю: мышцы поддерживают уровень",
            "Считать алкоголь: он бьёт по выработке напрямую",
            "Сдать анализ утром до 11:00 — позже цифра уже не показательна"],
           note="Начни со сна. Без него остальное работает вполсилы.")

final_slide(f"{OUT}/08.png", f"{SRC}/final.png",
            "И база по дефицитам",
            ["Цинк, селен и витамин D участвуют в синтезе — и именно их "
             "чаще всего не хватает.",
             "Мужской комплекс: цинк 25 мг (167% РСП), селен, D3, ликопин.",
             "60 капсул на 30 дней.",
             "Артикул 980783326"])

print("готово →", OUT)
