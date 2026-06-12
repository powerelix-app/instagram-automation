"""Наложение текста на сгенерированную картинку (Pillow) — чёткие плашки с правильной
кириллицей. AI-модель текст рисовать не умеет (коверкает), поэтому текст рисуем сами."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from . import config

FONTS = config.ROOT / "assets" / "fonts"
_XB = str(FONTS / "Inter-ExtraBold.otf")
_SB = str(FONTS / "Inter-SemiBold.otf")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, maxw: float) -> List[str]:
    lines, cur = [], ""
    for w in (text or "").split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def render(bg_path, points: List[str], headline: str = "", disclaimer: str = "",
           out_path: Optional[str] = None) -> Path:
    """Накладывает заголовок (вверху) + плашки-пункты (низ-центр) + дисклеймер (низ)."""
    im = Image.open(bg_path).convert("RGB")
    W, H = im.size
    draw = ImageDraw.Draw(im, "RGBA")
    pad = int(W * 0.06)

    # Заголовок сверху (с тенью для читаемости на любом фоне)
    if headline:
        fh = _font(_XB, max(28, int(W * 0.072)))
        y = int(H * 0.055)
        for ln in _wrap(draw, headline.upper(), fh, W - 2 * pad):
            tw = draw.textlength(ln, font=fh)
            x = (W - tw) // 2
            draw.text((x + 3, y + 3), ln, font=fh, fill=(0, 0, 0, 130))
            draw.text((x, y), ln, font=fh, fill=(255, 255, 255, 255))
            y += int(fh.size * 1.14)

    # Плашки-пункты в нижней половине, по центру
    fp = _font(_XB, max(24, int(W * 0.052)))
    bpx, bpy = int(W * 0.045), int(W * 0.026)
    gap = int(W * 0.022)
    rows = []
    for p in [p for p in points if p][:4]:
        plines = _wrap(draw, p.upper(), fp, int(W * 0.76))
        h = len(plines) * int(fp.size * 1.12) + 2 * bpy
        w = max(draw.textlength(l, font=fp) for l in plines) + 2 * bpx
        rows.append((plines, int(w), int(h)))
    total = sum(h for _, _, h in rows) + gap * max(0, len(rows) - 1)
    y = int(H * 0.92) - total if rows else 0  # прижимаем к низу
    y = max(int(H * 0.52), y)
    for plines, w, h in rows:
        x0 = (W - w) // 2
        draw.rounded_rectangle((x0, y, x0 + w, y + h), radius=int(h * 0.24), fill=(255, 255, 255, 240))
        ty = y + bpy
        for l in plines:
            tw = draw.textlength(l, font=fp)
            draw.text(((W - tw) // 2, ty), l, font=fp, fill=(28, 28, 38, 255))
            ty += int(fp.size * 1.12)
        y += h + gap

    # Дисклеймер внизу на тёмной полосе
    if disclaimer:
        fd = _font(_SB, max(14, int(W * 0.026)))
        bar_h = int(H * 0.052)
        draw.rectangle((0, H - bar_h, W, H), fill=(0, 0, 0, 150))
        dw = draw.textlength(disclaimer, font=fd)
        draw.text(((W - dw) // 2, H - bar_h + (bar_h - fd.size) // 2), disclaimer, font=fd,
                  fill=(255, 255, 255, 235))

    out = Path(out_path) if out_path else Path(bg_path).with_name("overlay.png")
    im.save(out)
    return out
