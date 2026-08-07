"""Карусель №21 «5 признаков, что ребёнку не хватает витаминов» (8 слайдов, 1080×1350).

Фирменный стиль POWERELIX через brand_overlay. Акцент — приглушённая охра #C4870F
(жёлтый #FFDE00 с детской этикетки на бежевом холсте не читается вовсе).
⚠️ Детская тема — формулировки строже обычного: никаких «не будет болеть»,
признаки подаём как повод присмотреться и сходить к педиатру, а не как диагноз.
Hero-кадр: обложка — gemini flash-image; финал — банка на холсте (_paste_bottle).
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import (
    W, H, M, _font, _canvas, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, INK, GREY,
)

ACCENT = _hex("#C4870F")      # приглушённая охра — детская линейка
LIGHT = _hex("#FFD34D")       # светлее — для акцентов поверх фото
DDARK = (26, 20, 10)
SRC = "/private/tmp/claude-501/-Users-maksimrogoznikov-projects/f76aea07-d110-4ec0-ae31-6649558b262e/scratchpad/p21"
OUT = "output/Карусели/post21_дети"
BOTTLE_PNG = ("/Users/maksimrogoznikov/Library/CloudStorage/GoogleDrive-powerelix.work@gmail.com/"
              "Мой диск/POWERELIX_материалы_для_магазина/Фото товаров (без фона)/11_Детские витамины.png")
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
    img = _darken(_cover(Image.open(scene)), base=62, top=130, bottom=740)
    d = ImageDraw.Draw(img)
    _mark(d, light=True)
    fh = _font(MONT_BLACK, 92)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 38)
    sub_lines = _wrap(d, sub, fs, W - 2 * M)
    y = H - 150 - len(lines) * 98 - 30 - len(sub_lines) * 46
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE); y += 98
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
cover(f"{OUT}/01.png", f"{SRC}/covC.png",
      "5 признаков, что ребёнку не хватает витаминов",
      "Проверьте по списку — это займёт минуту")

list_slide(f"{OUT}/02.png", "Сначала честно",
           ["По одному признаку понять нельзя — все они неспецифичны",
            "Смотреть надо на сочетание и на то, что изменилось за последние месяцы",
            "И на возраст: скачок роста сам по себе даёт и усталость, "
            "и качели аппетита"],
           note="Это не диагностика, а повод присмотреться и при случае дойти до педиатра.")

list_slide(f"{OUT}/03.png", "5 признаков:",
           ["Устаёт от обычной нагрузки — от той, что раньше давалась легко",
            "Чаще цепляет простуды и дольше их переносит",
            "Бледность и круги под глазами при нормальном сне",
            "Аппетит пропал или еда стала совсем однообразной",
            "Ломкие ногти, тусклые волосы, заеды в уголках рта"],
           note="Три пункта и больше — стоит сдать общий анализ крови.",
           numbered=True)

rule_slide(f"{OUT}/04.png", "ГЛАВНОЕ", "Рацион редко закрывает всё",
           "Дело не в калориях — их школьнику обычно хватает с запасом.",
           "Недобираются железо, йод и витамин D: они живут в мясе, рыбе и "
           "субпродуктах — ровно в том, что дети едят неохотно. Избирательность "
           "в еде это возрастная норма, а не пробел в воспитании.")

list_slide(f"{OUT}/05.png", "Чего чаще всего не хватает:",
           ["Железо — усталость, бледность, хуже даётся концентрация",
            "Витамин D — в наших широтах не хватает большинству с октября по март",
            "Йод — нужен щитовидной железе, а через неё росту и учёбе"],
           note="Все три проверяются анализом, а не списком признаков из интернета.")

list_slide(f"{OUT}/06.png", "С чего начинать:",
           ["Сон 9–11 часов — это не про строгость, а про восстановление",
            "Завтрак с белком вместо сладкой каши или булки",
            "Час на улице в светлое время: это и про витамин D, и про сон",
            "Общий анализ крови — по назначению педиатра"],
           note="Добавка идёт после этого, а не вместо.")

list_slide(f"{OUT}/07.png", "Когда точно к врачу:",
           ["Резкая бледность, одышка при беге",
            "Ребёнок перестал прибавлять в росте и весе",
            "Аппетит пропал надолго, а не на пару дней",
            "Простуды идут одна за другой и дают осложнения"],
           note="Это к педиатру. Добавки тут не инструмент.")

final_slide(f"{OUT}/08.png", BOTTLE_PNG,
            "Если решили поддержать",
            ["Мультивитамины для детей с 7 лет: A, C, D3, E и группа B.",
             "Плюс железо, цинк, йод и селен.",
             "60 капсул на 30 дней."])

print("готово →", OUT)
