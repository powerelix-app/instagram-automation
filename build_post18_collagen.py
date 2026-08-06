"""Карусель №18 «Коллаген не усваивается?» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — глубокая бирюза #128790
(яркая #2FCDD7 с этикетки коллагена на бежевом холсте кислотит).
Заход: сами называем главный аргумент критиков и отвечаем на него. По разведке
US-контента заявления про коллаген — самая атакуемая зона ниши, поэтому пост
начинается с уступки, а слайды 6-7 честно очерчивают ограничения.
Hero-кадр: обложка — Seedream 5 Pro; финал — банка на холсте (_paste_bottle).
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#128790")      # глубокая бирюза — коллаген
LIGHT = _hex("#5FD8E0")       # светлее — для акцентов поверх фото
DDARK = (10, 24, 26)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p18"
OUT = "output/Карусели/post18_коллаген"
BOTTLE_PNG = ("/Users/maksimrogoznikov/Library/CloudStorage/GoogleDrive-powerelix.work@gmail.com/"
              "Мой диск/POWERELIX_материалы_для_магазина/Фото товаров (без фона)/04_Морской коллаген.png")
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


def _paste_bottle(img, png_path, scale=0.62, cx=0.78, bottom=90):
    """Банка из PNG с родной альфой (ассеты «без фона»). _place_bottle тут
    не годится: он режет фон по белому и даёт чёрный прямоугольник."""
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


def cover(path, scene, hook, sub, tag="СОХРАНИ  →"):
    # фон уже тёмный (макро капсулы) — хватает лёгкого затемнения снизу
    img = _darken(_cover(Image.open(scene)), base=30, top=100, bottom=700)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 98)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 104 - 30 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 104
    d.rectangle([M, y + 6, M + 120, y + 16], fill=LIGHT)
    y += 32
    for sl in sub_lines:
        d.text((M, y), sl, font=fs, fill=WHITE); y += 46
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), LIGHT, 4)
    img.save(path); return path


def rule_slide(path, num, title, main, why, why_label="ПОЧЕМУ ТАК"):
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
    _spaced(d, (M, y), why_label, _font(MONT_BLACK, 26), ACCENT, 3)
    y += 46
    for ln in _wrap(d, why, _font(INTER_MED, 35), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 35), fill=GREY); y += 46
    img.save(path); return path


def list_slide(path, heading, bullets, note=None, numbered=False):
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


def final_slide(path, bottle_png, heading, lines_txt):
    img = _canvas()
    _paste_bottle(img, bottle_png)
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
cover(f"{OUT}/01.png", f"{SRC}/covF.png",
      "«Коллаген не усваивается»",
      "Разбираем главный спор индустрии — честно")

rule_slide(f"{OUT}/02.png", "НАЧНЁМ С ГЛАВНОГО", "Критики правы",
           "Коллаген не попадает из банки прямо в кожу и суставы.",
           "В желудке он распадается на аминокислоты и короткие пептиды — как любой "
           "другой белок. Никакой адресной доставки не существует, и обещать её "
           "нечестно.")

rule_slide(f"{OUT}/03.png", "ЧТО ТОГДА", "Работают пептиды",
           "Часть коротких пептидов доходит до крови целыми.",
           "По имеющимся данным они работают как сигнал: организм считывает их как "
           "признак того, что свой коллаген разрушается, и активнее строит новый. "
           "Не доставка, а команда.")

rule_slide(f"{OUT}/04.png", "УСЛОВИЕ", "Без витамина С бессмысленно",
           "Собственный коллаген без витамина С просто не синтезируется.",
           "Это не маркетинг, а базовая биохимия: витамин С нужен ферментам, которые "
           "собирают коллагеновую спираль. Поэтому смотреть надо не на коллаген "
           "в одиночку.",
           why_label="ЭТО НЕ РЕКЛАМА")

list_slide(f"{OUT}/05.png", "Морской или животный:",
           ["Морской усваивается чуть быстрее — пептиды мельче",
            "У бычьего больше накопленных исследований",
            "«Тип I, II, III» на упаковке — маркетинг: исходный тип до тканей "
            "всё равно не доходит"],
           note="Разница между ними меньше, чем разница между «пью регулярно» и «пью иногда».")

list_slide(f"{OUT}/06.png", "Чего ждать честно:",
           ["Данные по коже и суставам есть, но эффект скромный",
            "Значительная часть исследований оплачена производителями",
            "Раньше 8–12 недель смотреть не на что",
            "Это про поддержку, а не про омоложение"],
           note="Если обещают результат за неделю — это не про коллаген, это про продажи.")

list_slide(f"{OUT}/07.png", "Чему коллаген не замена:",
           ["Белку в рационе — это основа, из которой строится всё",
            "Сну: именно ночью идёт восстановление тканей",
            "Защите от солнца — она влияет на кожу сильнее любой добавки"],
           note="Добавка работает поверх этих трёх, а не вместо них.")

final_slide(f"{OUT}/08.png", BOTTLE_PNG,
            "Что у нас",
            ["Морской коллаген 1000 мг и витамин С 100 мг — в одной капсуле.",
             "Плюс коэнзим Q10 и гиалуроновая кислота.",
             "90 капсул на 30 дней."])

print("готово →", OUT)
