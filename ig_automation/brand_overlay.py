"""POWERELIX-овые брендовые надписи поверх банки (Pillow) — три стиля на пробу.

Не копия PWR: используем СВОЮ бренд-ДНК — вордмарк POWERELIX, фирменную «X»
в градиенте lime→бирюза, фигурные скобки `{ }`, слоган-стрип, Montserrat Black/Inter.

Стили (параметр style):
  • "stamp"  — вордмарк+X в углу, крупный заголовок, акцент-скобка, слоган-стрип снизу
  • "chips"  — фирменные скобки как плавающие инфо-чипы вокруг банки
  • "xmark"  — гигантская полупрозрачная «X» как водяной знак за банкой

Банка вырезается с белого фона (этикетка остаётся чёткой) и ставится на кремовый холст.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT
from .post_template import _cutout, _hex

FONTS = Path.home() / "Library" / "Fonts"
MONT_BLACK = str(FONTS / "montserrat-black.ttf")
INTER_XB = str(FONTS / "Inter-ExtraBold.otf")
INTER_SB = str(FONTS / "Inter-SemiBold.otf")
INTER_MED = str(FONTS / "Inter-Medium.otf")

# Бренд-ДНК POWERELIX
CREAM = (244, 241, 234)
INK = (10, 10, 10)
GREY = (130, 126, 118)
LIME = (182, 240, 0)   # #B6F000  — старт фирменного градиента X
TEAL = (22, 224, 166)  # #16E0A6  — финиш
SLOGAN = "ЗДОРОВЬЕ · ЭНЕРГИЯ · КАЖДЫЙ ДЕНЬ"
TAGLINE = "healthy nutrition"

W, H = 1080, 1350
M = 80


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _gradient(size: tuple[int, int], c1, c2, vertical: bool = True) -> Image.Image:
    """Линейный градиент c1→c2 (по вертикали или горизонтали)."""
    w, h = size
    n = h if vertical else w
    t = np.linspace(0, 1, max(n, 1))[:, None]
    row = (np.array(c1)[None, :] * (1 - t) + np.array(c2)[None, :] * t).astype("uint8")
    arr = np.repeat(row[:, None, :], w, axis=1) if vertical else np.repeat(
        row[None, :, :], h, axis=0
    )
    return Image.fromarray(arr, "RGB")


MARK_PNG = ROOT / "assets" / "brand" / "mark.png"


def _mark_asset() -> Image.Image | None:
    """Настоящий знак из assets/brand/mark.png (белый фон → прозрачность), crop по bbox."""
    if not MARK_PNG.exists():
        return None
    src = Image.open(MARK_PNG).convert("RGBA")
    a = np.array(src.convert("RGB")).astype(int)
    if src.getextrema()[3][0] < 250:  # уже есть альфа — используем её
        out = src
    else:  # белый фон → альфа по «белизне» (min канал), мягкий край
        m = a.min(axis=2)
        alpha = np.clip((238 - m) * (255 / 28), 0, 255).astype("uint8")
        out = Image.fromarray(
            np.dstack([np.array(src.convert("RGB")), alpha]).astype("uint8"), "RGBA"
        )
    return out.crop(out.getbbox())


def _mark_drawn() -> Image.Image:
    """Запасная кодовая версия знака (если нет mark.png) — две ленты, градиент."""
    S = 900
    w = int(0.205 * S)
    top = [(0.13, 0.20), (0.53, 0.45), (0.94, 0.45)]
    bot = [(0.06, 0.62), (0.47, 0.62), (0.87, 0.90)]
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    for pts in (top, bot):
        px = [(int(x * S), int(y * S)) for x, y in pts]
        md.line(px, fill=255, width=w, joint="curve")
        r = w // 2
        for cx, cy in (px[0], px[-1]):
            md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    grad = _gradient((S, S), LIME, TEAL, vertical=True)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out.crop(out.getbbox())


def brand_mark(height: int, opacity: int = 255) -> Image.Image:
    """Фирменный знак POWERELIX, масштабированный к заданной высоте (RGBA).

    Берёт настоящий PNG (assets/brand/mark.png), иначе — кодовую заглушку.
    """
    base = _mark_asset() or _mark_drawn()
    w = max(1, int(base.width * height / base.height))
    out = base.resize((w, height), Image.LANCZOS)
    if opacity < 255:
        out.putalpha(out.getchannel("A").point(lambda v: int(v * opacity / 255)))
    return out


def _grad_text(text: str, font: ImageFont.FreeTypeFont, c1=LIME, c2=TEAL) -> Image.Image:
    """Текст, залитый фирменным градиентом → RGBA по bbox."""
    bb = font.getbbox(text)
    pad = 6
    size = (bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).text((pad - bb[0], pad - bb[1]), text, font=font, fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(_gradient(size, c1, c2), (0, 0), mask)
    return out


def _spaced(draw, pos, text, font, fill, tracking: int):
    """Текст с межбуквенным интервалом (у Pillow нет letter-spacing)."""
    x, y = pos
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def _spaced_width(draw, text, font, tracking: int) -> float:
    return sum(draw.textlength(ch, font=font) + tracking for ch in text) - tracking


def _wrap_upper(draw, text, font, maxw) -> list[str]:
    lines, cur = [], ""
    for word in text.upper().split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _canvas() -> Image.Image:
    """Кремовый холст с лёгким световым центром (премиум-студия)."""
    base = Image.new("RGB", (W, H), CREAM)
    glow = _gradient((W, H), (250, 248, 243), (236, 230, 220))
    return Image.blend(base, glow, 0.6)


def _place_bottle(img: Image.Image, product_path, scale=0.50, cx=0.5, bottom=120):
    """Вырез банки + мягкая контактная тень, по центру снизу."""
    prod = _cutout(product_path)
    ph = int(H * scale)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    x = int(W * cx - pw / 2)
    y = H - ph - bottom

    # мягкая тень-эллипс под банкой
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        [x + pw * 0.12, y + ph - 40, x + pw * 0.88, y + ph + 55], fill=(0, 0, 0, 90)
    )
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    img.paste(sh, (0, 0), sh)
    img.paste(prod, (x, y), prod)
    return x, y, pw, ph


def _header(img, d, wordmark="POWERELIX"):
    """Вордмарк слева + фирменный знак справа, верхняя строка."""
    f = _font(INTER_XB, 30)
    _spaced(d, (M, 58), wordmark.upper(), f, INK, 3)
    mk = brand_mark(60)
    img.paste(mk, (W - M - mk.width, 42), mk)


def _slogan_strip(img, d, text=SLOGAN, y=H - 96):
    """Тонкая линия + слоган с трекингом по центру."""
    f = _font(INTER_MED, 26)
    tw = _spaced_width(d, text, f, 6)
    cx = (W - tw) / 2
    d.line([(M, y - 22), (cx - 24, y - 22)], fill=GREY, width=2)
    d.line([(cx + tw + 24, y - 22), (W - M, y - 22)], fill=GREY, width=2)
    _spaced(d, (cx, y), text, f, GREY, 6)


def _brace(d, pos, text, font, fill, pad_x=18):
    """Текст в фирменных фигурных скобках { text }."""
    x, y = pos
    bopen, bclose = "{", "}"
    fb = font
    d.text((x, y), bopen, font=fb, fill=fill)
    x2 = x + d.textlength(bopen, font=fb) + pad_x
    d.text((x2, y), text, font=font, fill=fill)
    x3 = x2 + d.textlength(text, font=font) + pad_x
    d.text((x3, y), bclose, font=fb, fill=fill)
    return x3 + d.textlength(bclose, font=fb)


def _chip(img, d, pos, text, accent, right=False):
    """Скобка-чип: светлая капсула с тонкой рамкой + { text }.

    right=True → pos[0] трактуется как правый край (чип растёт влево).
    """
    f = _font(INTER_SB, 30)
    inner = "{ " + text + " }"
    tw = d.textlength(inner, font=f)
    px, py = 26, 16
    x, y = pos
    w = tw + px * 2
    h = 30 + py * 2
    if right:
        x = x - w
    card = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(255, 253, 248, 235),
                         outline=accent, width=2)
    cd.text((px, py - 2), inner, font=f, fill=INK)
    img.paste(card, (int(x), int(y)), card)
    return w, h


def render(
    style: str,
    headline: str,
    subtitle: str,
    product_path: str | Path,
    out_path: str | Path,
    accent_hex: str = "#A8324F",
    units: str = "60 капсул",
    days: int = 30,
) -> Path:
    accent = _hex(accent_hex)
    img = _canvas()
    d = ImageDraw.Draw(img)

    if style == "stamp":
        _header(img, d)
        f = _font(MONT_BLACK, 104)
        lines = _wrap_upper(d, headline, f, W - 2 * M)
        y = 150
        for ln in lines:
            d.text((M, y), ln, font=f, fill=INK)
            y += 108
        d.rectangle([M, y + 16, M + 130, y + 24], fill=accent)  # акцент-рула
        fb = _font(INTER_SB, 40)
        _brace(d, (M, y + 44), subtitle, fb, accent)
        _place_bottle(img, product_path, scale=0.48, bottom=150)
        _slogan_strip(img, d)

    elif style == "chips":
        _header(img, d)
        f = _font(MONT_BLACK, 86)
        lines = _wrap_upper(d, headline, f, W - 2 * M)
        y = 150
        for ln in lines:
            d.text((M, y), ln, font=f, fill=INK)
            y += 90
        _place_bottle(img, product_path, scale=0.44, bottom=170)
        # фирменные скобки-чипы по краям, в свободной зоне у банки
        _chip(img, d, (M, y + 60), units, accent)
        _chip(img, d, (W - M, y + 230), subtitle, accent, right=True)
        _chip(img, d, (M, y + 410), f"{days} дней", accent)
        _slogan_strip(img, d, text=TAGLINE)

    elif style == "xmark":
        _header(img, d)
        big = brand_mark(620, opacity=58)
        img.paste(big, (int(W / 2 - big.width / 2), 430), big)
        f = _font(MONT_BLACK, 96)
        lines = _wrap_upper(d, headline, f, W - 2 * M)
        y = 150
        for ln in lines:
            d.text((M, y), ln, font=f, fill=INK)
            y += 100
        d.rectangle([M, y + 14, M + 130, y + 22], fill=accent)
        fb = _font(INTER_SB, 38)
        _brace(d, (M, y + 42), subtitle, fb, accent)
        _place_bottle(img, product_path, scale=0.46, bottom=160)
        _slogan_strip(img, d)

    else:
        raise ValueError(f"unknown style: {style!r} (stamp|chips|xmark)")

    img.save(out_path)
    return Path(out_path)


WHITE = (255, 255, 255)


def _cover(bg: Image.Image) -> Image.Image:
    """Фото под холст 1080×1350 (cover-fit)."""
    bg = bg.convert("RGB")
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * s), int(bg.height * s)), Image.LANCZOS)
    x = (bg.width - W) // 2
    y = (bg.height - H) // 2
    return bg.crop((x, y, x + W, y + H))


def _dark_scene() -> Image.Image:
    """Тёмная синтетическая подложка-заглушка (пока нет реального фото/AI-сцены)."""
    base = _gradient((W, H), (28, 36, 52), (12, 16, 23))
    d = ImageDraw.Draw(base)
    for x in range(0, W, 16):  # вертикальные «рёбра» как студийный фон
        d.line([(x, 0), (x, H)], fill=(255, 255, 255), width=1)
    base = Image.blend(base, _gradient((W, H), (28, 36, 52), (12, 16, 23)), 0.92)
    return base


def _scrim(img: Image.Image, top=140, bottom=460):
    """Затемнение сверху/снизу под читаемость текста."""
    ov = Image.new("L", (W, H), 0)
    da = np.array(ov)
    ys = np.arange(H)[:, None]
    da = np.clip(np.where(ys < top, (top - ys) / top * 150, 0)
                 + np.where(ys > H - bottom, (ys - (H - bottom)) / bottom * 200, 0), 0, 220)
    ov = Image.fromarray(da.astype("uint8").repeat(W, axis=1).reshape(H, W))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, ov)


def _corner_mark(img, d, wordmark="POWERELIX", fill=WHITE):
    """Скромная подпись в углу: знак + вордмарк (не PWR-бар на всю ширину)."""
    mk = brand_mark(44)
    img.paste(mk, (M, 56), mk)
    _spaced(d, (M + mk.width + 18, 64), wordmark.upper(), _font(INTER_XB, 28), fill, 3)


def render_hero(
    style: str,
    title: str,
    out_path: str | Path,
    bg_path: str | Path | None = None,
    accent_hex: str = "#B6F000",
    subtitle: str = "",
    wordmark: str = "POWERELIX",
) -> Path:
    """Hero-оверлей бренда поверх сцены — СВОИ каркасы (не PWR).

    style: block (чистый блок + скобка) | band (градиент-лента) | anchor (знак-якорь).
    """
    accent = _hex(accent_hex)
    img = _cover(Image.open(bg_path)) if bg_path else _dark_scene()

    if style == "block":
        img = _scrim(img, top=150, bottom=560)
        d = ImageDraw.Draw(img)
        _corner_mark(img, d, wordmark)
        ft = _font(MONT_BLACK, 100)
        lines = _wrap_upper(d, title, ft, W - 2 * M)
        y = H - 130 - len(lines) * 104 - (62 if subtitle else 0)
        for ln in lines:
            d.text((M, y), ln, font=ft, fill=WHITE)
            y += 104
        if subtitle:
            d.rectangle([M, y + 8, M + 120, y + 15], fill=accent)
            _brace(d, (M, y + 30), subtitle, _font(INTER_SB, 40), accent)

    elif style == "band":
        bh = 200
        img = _scrim(img, top=150, bottom=bh + 200)
        d = ImageDraw.Draw(img)
        _corner_mark(img, d, wordmark)
        # заголовок на фото, над лентой
        ft = _font(MONT_BLACK, 96)
        lines = _wrap_upper(d, title, ft, W - 2 * M)
        y = H - bh - 60 - len(lines) * 100
        for ln in lines:
            d.text((M, y), ln, font=ft, fill=WHITE)
            y += 100
        # фирменная градиент-лента снизу со слоганом (тёмный текст по светлой ленте)
        img.paste(_gradient((W, bh), LIME, TEAL, vertical=False), (0, H - bh))
        d = ImageDraw.Draw(img)
        fs = _font(INTER_XB, 30)
        sw = _spaced_width(d, SLOGAN, fs, 5)
        _spaced(d, ((W - sw) / 2, H - bh + (bh - 36) // 2), SLOGAN, fs, INK, 5)

    elif style == "anchor":
        img = _scrim(img, top=150, bottom=420)
        d = ImageDraw.Draw(img)
        _corner_mark(img, d, wordmark)
        big = brand_mark(360)  # знак-якорь крупно, нижний-левый угол
        img.paste(big, (M - 20, H - big.height - 230), big)
        ft = _font(MONT_BLACK, 92)
        lines = _wrap_upper(d, title, ft, W - 2 * M)
        y = H - 150 - len(lines) * 96 - (56 if subtitle else 0)
        for ln in lines:
            d.text((M, y), ln, font=ft, fill=WHITE)
            y += 96
        if subtitle:
            _brace(d, (M, y + 18), subtitle, _font(INTER_SB, 38), accent)

    else:
        raise ValueError(f"unknown hero style: {style!r} (block|band|anchor)")

    img.save(out_path)
    return Path(out_path)


ARCHIVE = Path.home() / "Downloads" / "Архив"
_ASSETS_FILE = ROOT / "data" / "product_assets.json"
_CATALOG_FILE = ROOT / "data" / "brand_powerelix.json"


def _load_assets() -> dict:
    import json

    a = json.loads(_ASSETS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in a.items() if not k.startswith("_")}


def _catalog_days() -> dict[str, int]:
    import json

    cat = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    return {str(p["id"]): p.get("duration_days", 30) for p in cat["products"]}


def render_product(pid: int | str, style: str, out_path: str | Path,
                   headline: str | None = None) -> Path:
    """Рендер карточки по id продукта: тянет банку, акцент, подпись, капсулы/дни."""
    a = _load_assets()[str(pid)]
    days = _catalog_days().get(str(pid), 30)
    return render(
        style=style,
        headline=headline or a["short"],
        subtitle=a["subtitle"],
        product_path=ARCHIVE / a["image"],
        out_path=out_path,
        accent_hex=a["accent"],
        units=a["units"],
        days=days,
    )
