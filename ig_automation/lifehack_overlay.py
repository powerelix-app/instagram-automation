"""Тёмный стиль для лайфхак-каруселей POWERELIX.

Зачем отдельный модуль. `brand_overlay` даёт бежевый холст — на нём фирменная
яркая мята #16FFB3 кислотит, поэтому во всех образовательных постах мы вынуждены
брать приглушённые акценты. Здесь фон графитовый, и мята работает в полную силу.
Побочный эффект полезный: в ленте лайфхаки визуально отделяются от образовательных
каруселей.

Ключевые решения:
  • фото вставляется КАРТОЧКОЙ со скруглением и НЕ затемняется — насыщенный цвет
    снимка и есть главный акцент, тёмный фон вокруг работает как паспарту;
  • один акцентный цвет на всю серию (мята), никаких продуктовых цветов;
  • крупная мятная цифра приёма + мятная линейка у пояснения — структура читается
    с одного взгляда.

Образец: output/Концепции/лайфхак-тёмная/
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .brand_overlay import (
    W, H, M, _font, _cover, _spaced, _hex,
    MONT_BLACK, INTER_SB, INTER_MED,
)

BG = (16, 19, 20)            # глубокий графит, намеренно не чистый чёрный
GLOW = (14, 60, 48)          # мятное свечение из угла
MINT = _hex("#16FFB3")       # яркая фирменная мята — живёт только на тёмном
INK = (255, 255, 255)
GREY = (150, 158, 156)


def bg() -> Image.Image:
    """Графит с мягким мятным свечением из верхнего правого угла."""
    ys, xs = np.mgrid[0:H, 0:W]
    d = np.sqrt((xs - W * 0.88) ** 2 + (ys - H * 0.08) ** 2) / (W * 1.0)
    a = np.clip((1 - d) * 46, 0, 46).astype("uint8")
    return Image.composite(Image.new("RGB", (W, H), GLOW),
                           Image.new("RGB", (W, H), BG), Image.fromarray(a))


def wrap(d, text: str, font, maxw: int) -> list[str]:
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


def mark(d) -> None:
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 48), INK, 3)


def photo_card(img: Image.Image, path, top: int, height: int, radius: int = 28) -> None:
    """Фото карточкой со скруглением. Цвет НЕ приглушаем — он и есть акцент."""
    ph = _cover(Image.open(path)).resize((W - 2 * M, height), Image.LANCZOS)
    mask = Image.new("L", ph.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ph.width, ph.height], radius, fill=255)
    img.paste(ph, (M, top), mask)


def cover(path, photo, hook: str, sub: str, tag: str = "СОХРАНИ  →"):
    """Обложка: фото-карточка сверху, крупный заголовок и подзаголовок снизу."""
    img = bg()
    d = ImageDraw.Draw(img)
    mark(d)
    photo_card(img, photo, 140, 540)
    y = 740
    fh = _font(MONT_BLACK, 92)
    for ln in wrap(d, hook.upper(), fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 98
    d.rectangle([M, y + 14, M + 140, y + 26], fill=MINT)
    y += 56
    for ln in wrap(d, sub, _font(INTER_SB, 38), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_SB, 38), fill=GREY); y += 48
    _spaced(d, (M, H - 92), tag, _font(INTER_MED, 28), MINT, 4)
    img.save(path)
    return path


def step(path, num: str, title: str, main: str, why: str):
    """Слайд приёма: крупная цифра, заголовок, суть и пояснение с линейкой."""
    img = bg()
    d = ImageDraw.Draw(img)
    mark(d)
    y = 230
    d.text((M, y), num, font=_font(MONT_BLACK, 150), fill=MINT)
    y += 190
    fh = _font(MONT_BLACK, 78)
    for ln in wrap(d, title, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 88
    y += 24
    fm = _font(INTER_SB, 44)
    for ln in wrap(d, main, fm, W - 2 * M):
        d.text((M, y), ln, font=fm, fill=INK); y += 56
    y += 34
    fw = _font(INTER_MED, 34)
    why_lines = wrap(d, why, fw, W - 2 * M - 40)
    d.rectangle([M, y, M + 6, y + 46 * len(why_lines)], fill=MINT)
    for ln in why_lines:
        d.text((M + 34, y), ln, font=fw, fill=GREY); y += 46
    img.save(path)
    return path


def bullets(path, heading: str, items: list[str], note: str | None = None):
    """Слайд-список: заголовок и пункты с мятными маркерами."""
    img = bg()
    d = ImageDraw.Draw(img)
    mark(d)
    y = 250
    fh = _font(MONT_BLACK, 78)
    for ln in wrap(d, heading, fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += 88
    d.rectangle([M, y + 16, M + 140, y + 28], fill=MINT)
    y += 72
    fb = _font(INTER_SB, 42)
    for b in items:
        d.ellipse([M, y + 16, M + 18, y + 34], fill=MINT)
        for ln in wrap(d, b, fb, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fb, fill=INK); y += 54
        y += 26
    if note:
        y += 18
        fn = _font(INTER_MED, 32)
        for ln in wrap(d, note, fn, W - 2 * M):
            d.text((M, y), ln, font=fn, fill=GREY); y += 42
    img.save(path)
    return path
