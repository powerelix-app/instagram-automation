"""Наложение фирменного текста на фото поста (Pillow) — стиль обложки POWERELIX:
вордмарк POWERELIX (Montserrat Black, без логотипа) + крупный заголовок Montserrat Black
капсом + акцент-черта #00C29B + подзаголовок (Inter) + тег «СОХРАНИ →» + дисклеймер БАД.

Переиспользует движок brand_overlay (тот же, что делает эталонные карусели build_post01).
AI текст в кадре коверкает (особенно кириллицу), поэтому фото генерим чистым, текст рисуем сами."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw

from . import brand_overlay as bo

ACCENT = bo._hex("#00C29B")
DEFAULT_TAG = "СОХРАНИ  →"


def _wrap(d, text: str, font, maxw: float) -> List[str]:
    lines, cur = [], ""
    for w in (text or "").split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


_CANVAS_BY_RATIO = {"4:5": (1080, 1350), "9:16": (1080, 1920), "1:1": (1080, 1080)}
# Reels/сторис (9:16) поверх нашей картинки рисуется ЧУЖОЙ UI: сверху часы/иконки
# камеры, снизу — имя аккаунта, подпись, значки лайка/шаринга. Наш текст должен
# садиться НИЖЕ верхней плашки и ВЫШЕ нижней, иначе они наезжают друг на друга
# (как на скрине пользователя). Для фида (4:5/1:1) такого чужого UI нет — старые отступы.
_TOP_Y_BY_RATIO = {"9:16": 210}       # y вордмарка POWERELIX; дефолт 60
_BOTTOM_GAP_BY_RATIO = {"9:16": 360}  # отступ снизу под блок текста; дефолт 70


def render_cover(bg_path, headline: str, subtitle: str = "", tag: str = DEFAULT_TAG,
                 disclaimer: str = "", out_path: Optional[str] = None, ratio: str = "4:5") -> Path:
    """Кладёт обложку-текст на фото. Раскладка якорится снизу вверх с явными зазорами:
    [дисклеймер] [тег] [подзаголовок] [акцент] [заголовок] — ничего не слипается.
    ratio: холст движка (bo.W/bo.H) — фиксированный 1080x1350 (4:5) по умолчанию; для
    Reels/сторис (9:16) и квадрата (1:1) временно переключаем на нужные размеры,
    иначе вертикальная картинка сплющивается/обрезается под чужой формат."""
    target = _CANVAS_BY_RATIO.get(ratio, _CANVAS_BY_RATIO["4:5"])
    orig_wh = (bo.W, bo.H)
    bo.W, bo.H = target
    try:
        W, H, M = bo.W, bo.H, bo.M
        top_y = _TOP_Y_BY_RATIO.get(ratio, 60)
        bottom_gap = _BOTTOM_GAP_BY_RATIO.get(ratio, 70)
        scrim_top = 140 + (top_y - 60)      # затемнение растёт вместе с отступом
        scrim_bottom = 660 + (bottom_gap - 70)
        img = bo._scrim(bo._cover(Image.open(bg_path)), top=scrim_top, bottom=scrim_bottom)
        d = ImageDraw.Draw(img)
        bo._spaced(d, (M, top_y), "POWERELIX", bo._font(bo.MONT_BLACK, 52), bo.WHITE, 3)

        fh = bo._font(bo.MONT_BLACK, 104)
        fs = bo._font(bo.INTER_SB, 42)
        ft = bo._font(bo.INTER_MED, 28)
        fd = bo._font(bo.INTER_MED, 24)
        HEAD_LH, SUB_LH = 110, 54

        lines = _wrap(d, (headline or "").upper(), fh, W - 2 * M)
        subl = _wrap(d, subtitle, fs, W - 2 * M) if subtitle else []

        # снизу вверх
        y = H - bottom_gap
        disc_y = tag_y = None
        if disclaimer:
            y -= fd.size
            disc_y = y
            y -= 26
        if tag:
            y -= ft.size
            tag_y = y
            y -= 48
        sub_bottom = y
        sub_top = sub_bottom - len(subl) * SUB_LH
        accent_y = (sub_top - 30) if subl else (sub_bottom - 8)
        head_bottom = accent_y - 22
        hy = head_bottom - len(lines) * HEAD_LH

        for ln in lines:
            d.text((M, hy), ln, font=fh, fill=bo.WHITE)
            hy += HEAD_LH
        d.rectangle([M, accent_y, M + 110, accent_y + 8], fill=ACCENT)
        sy = sub_top
        for ln in subl:
            d.text((M, sy), ln, font=fs, fill=bo.WHITE)
            sy += SUB_LH
        if tag_y is not None:
            bo._spaced(d, (M, tag_y), tag, ft, ACCENT, 4)
        if disc_y is not None:
            d.text((M, disc_y), disclaimer, font=fd, fill=(225, 225, 225))

        out = Path(out_path) if out_path else Path(bg_path).with_name("overlay.png")
        img.convert("RGB").save(out)
        return out
    finally:
        bo.W, bo.H = orig_wh
