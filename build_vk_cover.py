"""Обложка VK-статьи 1920×1080 — версия, читаемая в превью списка.

Что чинит по сравнению с первой версией:
  • заголовок крупнее — в превью ~250 px шириной мелкий текст не читался;
  • блок выровнен по вертикали, без пустой нижней трети;
  • всё содержимое внутри безопасных полей 210 px: VK кропит 16:9 к более
    квадратному превью и срезал бы вордмарк и батарейку по краям.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ig_automation.brand_overlay import _font, _spaced, _hex, MONT_BLACK, INTER_SB, INTER_MED

W, H = 1920, 1080
SAFE = 210                      # безопасное поле: VK кропит края превью
MINT = _hex("#16FFB3")
CORAL = _hex("#FF5A4E")
WHITE = (255, 255, 255)
GREY = (176, 190, 186)


def _bg():
    """Тёмный градиент из угла — фирменный фон статей."""
    ys, xs = np.mgrid[0:H, 0:W]
    t = np.clip((xs / W * 0.6 + (1 - ys / H) * 0.6), 0, 1)[..., None]
    c1, c2 = np.array([8, 18, 16]), np.array([16, 54, 44])
    return Image.fromarray((c1 + (c2 - c1) * t).astype("uint8"), "RGB")


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


def battery(d, cx, cy, w=430, h=220, pct=0.2):
    """Иконка батареи с уровнем заряда."""
    x0, y0 = cx - w // 2, cy - h // 2
    r = 26
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], r, outline=WHITE, width=11)
    d.rounded_rectangle([x0 + w + 14, cy - 34, x0 + w + 40, cy + 34], 12, fill=WHITE)
    pad = 26
    fill_w = int((w - pad * 2) * pct)
    d.rounded_rectangle([x0 + pad, y0 + pad, x0 + pad + fill_w, y0 + h - pad], 14, fill=CORAL)


def build(out, kicker, title_lines, accent_line, sub, pct=0.2):
    img = _bg()
    d = ImageDraw.Draw(img)

    _spaced(d, (SAFE, 84), "POWERELIX", _font(MONT_BLACK, 54), WHITE, 4)

    col_w = 1010                       # левая колонка под текст, справа — иконка
    fs = 128                           # ужимаем заголовок, пока не влезет в колонку
    while fs > 84 and max(d.textlength(l, font=_font(MONT_BLACK, fs))
                          for l in title_lines) > col_w:
        fs -= 4
    f_title = _font(MONT_BLACK, fs)
    lh = int(fs * 1.12)
    f_sub = _font(INTER_MED, 44)
    sub_lines = _wrap(d, sub, f_sub, col_w)

    block_h = 56 + len(title_lines) * lh + 34 + 14 + len(sub_lines) * 58
    y = (H - block_h) // 2 + 20

    _spaced(d, (SAFE, y), kicker, _font(MONT_BLACK, 40), MINT, 6)
    y += 84
    for ln in title_lines:
        d.text((SAFE, y), ln, font=f_title, fill=MINT if ln == accent_line else WHITE)
        y += lh
    d.rectangle([SAFE, y + 10, SAFE + 190, y + 22], fill=MINT)
    y += 58
    for ln in sub_lines:
        d.text((SAFE, y), ln, font=f_sub, fill=GREY); y += 58

    bx, by = W - SAFE - 195, H // 2 - 40
    battery(d, bx, by, w=360, h=185, pct=pct)
    pf = _font(MONT_BLACK, 88)
    pt = f"{int(pct * 100)}%"
    d.text((bx - d.textlength(pt, font=pf) / 2, by + 130), pt, font=pf, fill=CORAL)

    img.save(out, quality=95)
    print("готово →", out, img.size)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "output/VK_статьи/cover_batareyka_1920x1080.jpg"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    build(out, "РАЗБОР",
          ["ПОЧЕМУ К ОБЕДУ", "САДИТСЯ", "БАТАРЕЙКА"], "САДИТСЯ",
          "Сон, сахар, вода и дефициты — что реально стоит за упадком сил")
