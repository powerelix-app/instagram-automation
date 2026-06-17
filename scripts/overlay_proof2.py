"""Проба: наложение текста на фото поста через НАСТОЯЩИЙ движок brand_overlay.py
(тот, что делает эталонные карусели build_post01). Стиль обложки: вордмарк POWERELIX
(Montserrat Black, без знака) + крупный заголовок Montserrat + акцент-черта + подзаголовок."""
from pathlib import Path

from PIL import Image, ImageDraw

from ig_automation.brand_overlay import (
    W, H, M, _font, _cover, _scrim, _spaced,
    MONT_BLACK, INTER_SB, INTER_MED, WHITE, _hex,
)

ACCENT = _hex("#00C29B")
OUT = Path("output/overlay_styles")
OUT.mkdir(parents=True, exist_ok=True)


def _wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _mark(d):
    _spaced(d, (M, 60), "POWERELIX", _font(MONT_BLACK, 52), WHITE, 3)


def cover(photo, hook, sub, tag, out):
    img = _scrim(_cover(Image.open(photo)), top=140, bottom=620)
    d = ImageDraw.Draw(img)
    _mark(d)
    fh = _font(MONT_BLACK, 104)
    lines = _wrap(d, hook.upper(), fh, W - 2 * M)
    fs = _font(INTER_SB, 44)
    y = H - 150 - len(lines) * 110 - 70
    for ln in lines:
        d.text((M, y), ln, font=fh, fill=WHITE)
        y += 110
    d.rectangle([M, y + 6, M + 110, y + 14], fill=ACCENT)
    ys = y + 30
    for ln in _wrap(d, sub, fs, W - 2 * M):
        d.text((M, ys), ln, font=fs, fill=WHITE)
        ys += 56
    _spaced(d, (M, H - 96), tag, _font(INTER_MED, 28), ACCENT, 4)
    img.save(out)
    return out


if __name__ == "__main__":
    cover("/tmp/post1_check.png",
          "Магний для спокойных нервов",
          "Поддержка нервной системы и лёгкое засыпание",
          "СОХРАНИ  →",
          OUT / "6_engine_cover.png")
    print("ok engine cover")
