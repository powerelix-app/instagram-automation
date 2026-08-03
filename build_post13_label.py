"""Карусель №13 «5 строк на этикетке, которые решают всё» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — приглушённый фиолетовый
#6B5AA0 (магний, он же на hero-кадрах); яркий #8975BF на бежевом кислотит.
Заход: разбор этикетки — по разведке US-контента самый сохраняемый формат ниши.
Hero-кадры: обложка + финал — Seedream 5 Pro edit с защитой этикетки.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex, _place_bottle,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#6B5AA0")      # приглушённый фиолетовый — магний
LIGHT = _hex("#A796D8")       # светлее — для акцентов поверх фото
DDARK = (20, 16, 28)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p13"
OUT = "output/Карусели/post13_этикетка"
BOTTLE_PNG = ("/Users/maksimrogoznikov/Library/CloudStorage/GoogleDrive-powerelix.work@gmail.com/"
              "Мой диск/POWERELIX_материалы_для_магазина/Фото товаров (без фона)/02_Магний+B6.png")
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
    # фон светлый (банка на белом) — затемняем сильнее, иначе белый текст не читается
    img = _darken(_cover(Image.open(scene)), base=76, top=140, bottom=760)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 96)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 40)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 102 - 30 - len(sub_lines) * 48
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 102
    d.rectangle([M, y + 6, M + 120, y + 16], fill=LIGHT)
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 48
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), LIGHT, 4)
    img.save(path); return path


def rule_slide(path, num, title, main, why):
    """Слайд правила: номер + заголовок + суть + почему так."""
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    _spaced(d, (M, y), num, _font(MONT_BLACK, 34), ACCENT, 4)
    y += 58
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, title, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 80
    d.rectangle([M, y + 8, M + 130, y + 18], fill=ACCENT)
    y += 62
    fm = _font(INTER_SB, 42)
    for ln in _wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=INK); y += 54
    y += 32
    _spaced(d, (M, y), "ПОЧЕМУ ЭТО ВАЖНО", _font(MONT_BLACK, 26), ACCENT, 3)
    y += 46
    for ln in _wrap(d, why, _font(INTER_MED, 35), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 35), fill=GREY); y += 46
    img.save(path); return path


def list_slide(path, num, heading, bullets, note=None):
    img = _canvas()
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 235
    if num:
        _spaced(d, (M, y), num, _font(MONT_BLACK, 34), ACCENT, 4)
        y += 58
    else:
        y += 20
    fh = _font(MONT_BLACK, 70)
    for ln in _wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 80
    d.rectangle([M, y + 10, M + 130, y + 20], fill=ACCENT)
    y += 66
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


def _paste_bottle(img, png_path, scale=0.60, cx=0.78, bottom=90):
    """Ставит банку из PNG с собственной альфой (у ассетов «без фона» она есть).
    _place_bottle тут не годится: он режет фон по белому и делает чёрный прямоугольник."""
    prod = Image.open(png_path).convert("RGBA")
    ph = int(H * scale)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    x, y = int(W * cx - pw / 2), H - ph - bottom
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        [x + pw * 0.14, y + ph - 34, x + pw * 0.86, y + ph + 48], fill=(0, 0, 0, 70))
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    img.paste(sh, (0, 0), sh)
    img.paste(prod, (x, y), prod)


def final_slide(path, bottle_png, heading, lines_txt):
    """Финал на фирменном холсте: текст слева, банка справа — без наложений."""
    img = _canvas()
    _paste_bottle(img, bottle_png, scale=0.62, cx=0.78, bottom=90)
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 250
    fh = _font(MONT_BLACK, 62)
    for ln in _wrap(d, heading, fh, int(W * 0.56)):
        d.text((M, y), ln, font=fh, fill=INK); y += 72
    d.rectangle([M, y + 10, M + 120, y + 20], fill=ACCENT)
    y += 52
    fb = _font(INTER_MED, 34)
    for t in lines_txt:
        for ln in _wrap(d, t, fb, int(W * 0.50)):
            d.text((M, y), ln, font=fb, fill=INK); y += 46
        y += 16
    img.save(path); return path


# ── слайды ──
cover(f"{OUT}/01.png", f"{SRC}/cov.png",
      "5 строк на этикетке, которые решают всё",
      "Проверь свою банку прямо сейчас")

rule_slide(f"{OUT}/02.png", "ПРАВИЛО 1", "Процент важнее мг",
           "400 мг магния — это 100% суточной нормы. 400 мг кальция — всего 40%.",
           "У каждого вещества своя норма, поэтому миллиграммы сами по себе ни о чём "
           "не говорят. Крупную цифру в мг любят ставить как раз там, где процент "
           "получается скромный.")

rule_slide(f"{OUT}/03.png", "ПРАВИЛО 2", "«Комплекс» вместо состава",
           "Если дозировка указана одной суммой на всю смесь, а не по каждому "
           "веществу — состав от тебя спрятали.",
           "Это законный способ не показывать, что дорогого компонента внутри на "
           "копейку, а объём добран дешёвым. Когда прятать нечего — пишут по строкам.")

rule_slide(f"{OUT}/04.png", "ПРАВИЛО 3", "Форма важнее дозы",
           "Смотри, что написано в скобках после названия вещества.",
           "Оксид магния усваивается порядка 4%, цитрат — в разы лучше. То есть "
           "400 мг оксида на деле проигрывают 200 мг цитрата. Та же история с "
           "железом, цинком и хромом.")

list_slide(f"{OUT}/05.png", "ПРАВИЛО 4", "Слова, которые ничего не значат:",
           ["«Премиум» и «фарма-качество» — у этих слов нет закреплённого определения",
            "«Натуральный» — маркетинг, а не стандарт качества",
            "«Клинически доказано» без ссылки на конкретное исследование",
            "«Проверено третьей стороной» без имени лаборатории"],
           note="Значит что-то только конкретика: вещество, форма, миллиграммы, процент.")

rule_slide(f"{OUT}/06.png", "ПРАВИЛО 5", "Длинный список ≠ богатый состав",
           "Тридцать компонентов по 5% нормы — это витрина, а не состав.",
           "В капсулу физически влезает ограниченный объём. Чем больше строк в "
           "составе, тем меньше достаётся каждой. Десять веществ в рабочих дозах "
           "полезнее тридцати в следовых.")

list_slide(f"{OUT}/07.png", None, "Проверка за 30 секунд:",
           ["Есть ли % от нормы напротив каждого вещества?",
            "Указана ли форма в скобках?",
            "Нет ли общей суммы вместо построчного состава?",
            "Сколько веществ реально в рабочей дозе, а не для длины списка?"],
           note="Прошла все четыре — с такой банкой уже можно иметь дело.")

final_slide(f"{OUT}/08.png", BOTTLE_PNG,
            "Как это выглядит у нас",
            ["Вещество, миллиграммы и % от нормы — по строкам.",
             "Без общих сумм и «комплексов».",
             "Магний в форме цитрата: 400 мг, 100% нормы.",
             "Витамин B6 — 6 мг.",
             "Проверь сам — состав целиком на банке."])

print("готово →", OUT)
