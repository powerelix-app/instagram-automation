"""Генератор шаблона поста POWERELIX (Pillow) — светлый стиль, Inter, фирстиль.

Вырезает реальную банку (белый фон → прозрачность) и ставит на кремовый холст,
поэтому этикетка остаётся чёткой. Заголовок — Inter ExtraBold, акцент = цвет продукта,
фирменные фигурные скобки { } для плашки.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import ROOT

FONTS = Path.home() / "Library" / "Fonts"
INTER_XB = str(FONTS / "Inter-ExtraBold.otf")
INTER_R = str(FONTS / "Inter-Regular.otf")
LOGO = ROOT / "assets" / "brand" / "logo_full.png"

CREAM = (244, 241, 234)
INK = (20, 20, 20)
GREY = (120, 120, 120)


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _whiten_to(img: Image.Image, color=CREAM) -> Image.Image:
    """Белый фон → заданный цвет (для логотипа на кремовом)."""
    a = np.array(img.convert("RGB"))
    w = (a[:, :, 0] > 238) & (a[:, :, 1] > 238) & (a[:, :, 2] > 238)
    a[w] = color
    return Image.fromarray(a)


def _cutout(path: str | Path) -> Image.Image:
    """Вырез объекта с белого фона → RGBA по bbox."""
    a = np.array(Image.open(path).convert("RGB"))
    white = (a[:, :, 0] > 236) & (a[:, :, 1] > 236) & (a[:, :, 2] > 236)
    alpha = np.where(white, 0, 255).astype("uint8")
    img = Image.fromarray(np.dstack([a, alpha]), "RGBA")
    return img.crop(img.getbbox())


def _wrap(draw, text, font, maxw) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render_post(
    headline: str,
    pill_text: str,
    product_path: str | Path,
    accent_hex: str,
    out_path: str | Path,
) -> Path:
    W, H = 1080, 1350
    M = 90
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    accent = _hex(accent_hex)

    # — логотип сверху-слева —
    logo = _whiten_to(Image.open(LOGO))
    lw = 360
    lh = int(logo.height * lw / logo.width)
    img.paste(logo.resize((lw, lh)), (M - 10, 55))

    # — банка справа-снизу (вырез, чёткая этикетка) —
    prod = _cutout(product_path)
    ph = int(H * 0.52)
    pw = int(prod.width * ph / prod.height)
    img.paste(prod.resize((pw, ph)), (W - pw - 30, H - ph - 30), prod.resize((pw, ph)))

    # — заголовок (Inter ExtraBold, UPPERCASE) —
    f = ImageFont.truetype(INTER_XB, 92)
    lines = _wrap(d, headline.upper(), f, int(W * 0.62))
    y = 300
    for ln in lines:
        d.text((M, y), ln, font=f, fill=INK)
        y += 104

    # — плашка в фирменных скобках, акцентным цветом —
    fp = ImageFont.truetype(INTER_XB, 40)
    d.text((M, y + 24), "{ " + pill_text + " }", font=fp, fill=accent)

    # — хэндл внизу —
    fh = ImageFont.truetype(INTER_R, 32)
    d.text((M, H - 66), "@powerelix", font=fh, fill=GREY)

    img.save(out_path)
    return Path(out_path)
