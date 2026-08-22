"""Вёрстка лайфхак-каруселей POWERELIX (система v4).

Отличается от `brand_overlay` (образовательные посты) четырьмя приёмами:
  • полоса-заряд в шапке — градиент лайм→бирюза, заполняется к последнему слайду;
  • фигурные скобки `{ }` как разметка смысла, а не украшение;
  • снимки показываются ЦЕЛИКОМ, в родных пропорциях (photo_whole), без обрезки;
  • шкалы % от суточной нормы вместо обещаний.

Фон кремовый, как у образовательных постов: лента остаётся единой, лайфхаки
отличаются вёрсткой, а не цветом. Акцент — цвет продукта, о котором пост.

Образцы: output/Концепции/своя-система-v4/
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from .brand_overlay import (
    W, H, M, _font, _hex, _gradient, MONT_BLACK, INTER_SB, INTER_MED,
)

CREAM = (244, 241, 234)
INK = (18, 20, 21)
WHITE = (255, 255, 255)
GREY = (122, 120, 114)
GREY_D = (150, 156, 154)      # серый на тёмном фоне
RAIL = (216, 212, 202)        # незаполненная часть полосы и шкал
LIME = _hex("#B6F000")
TEAL = _hex("#16E0A6")
MONO_PATH = "/System/Library/Fonts/Menlo.ttc"


def mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO_PATH, size)


def wrap(d, text: str, font, maxw: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        s = (cur + " " + w).strip()
        if d.textlength(s, font=font) <= maxw:
            cur = s
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def fit_box(path, bw: int, bh: int) -> Image.Image:
    """ПРАВИЛО: фото НИКОГДА не растягиваем. Масштабируем по большей стороне так,
    чтобы рамка закрылась целиком, и обрезаем лишнее по центру.

    Ловушка, в которую легко попасть: взять уже кадрированный под 4:5 снимок
    (`brand_overlay._cover`) и resize-нуть его в широкую рамку — пропорции поедут.
    Поэтому кадрируем ВСЕГДА под конкретную рамку и только из оригинала."""
    im = Image.open(path).convert("RGB")
    s = max(bw / im.width, bh / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    x, y = (im.width - bw) // 2, (im.height - bh) // 2
    return im.crop((x, y, x + bw, y + bh))


def fit_font(d, text: str, maxw: int, start: int, floor: int = 40):
    """ПРАВИЛО: заголовок никогда не вылезает за поля. Ужимаем кегль, пока самое
    длинное СЛОВО не влезет в колонку (перенос спасает строку, но не слово).

    ⚠️ Ловушка: мерить надо УЖЕ приведённый к .upper() текст. Прописные шире
    строчных, и строка, влезавшая по расчёту, на слайде вылезала за поле."""
    fs = start
    while fs > floor and max(d.textlength(w, font=_font(MONT_BLACK, fs))
                             for w in text.upper().split()) > maxw:
        fs -= 2
    return _font(MONT_BLACK, fs), fs


def header(img, d, idx: int, total: int, light: bool = False) -> None:
    """Логотип слева, под ним полоса-заряд. Справа намеренно пусто."""
    d.text((M, 58), "POWERELIX", font=_font(MONT_BLACK, 42), fill=WHITE if light else INK)
    y, h = 122, 7
    if light:
        bar = Image.new("RGBA", (W - 2 * M, h), (255, 255, 255, 70))
        img.paste(bar, (M, y), bar)
    else:
        d.rectangle([M, y, W - M, y + h], fill=RAIL)
    fw = int((W - 2 * M) * idx / total)
    if fw > 0:
        img.paste(_gradient((fw, h), LIME, TEAL, vertical=False), (M, y))


def photo_whole(img, path, x: int, y: int, max_w: int, max_h: int) -> tuple[int, int]:
    """ПРАВИЛО: снимок показываем ЦЕЛИКОМ, в его собственных пропорциях.
    Вписываем в рамку по меньшему коэффициенту (contain) — ничего не режем и
    ничего не растягиваем. Возвращает фактический размер.

    Почему не cover: вертикальный кадр 4:5, загнанный в широкую полосу, теряет
    две трети картинки и читается как «обрезали». У PWR фото стоят в родных
    пропорциях — именно это и требовалось повторить."""
    im = Image.open(path).convert("RGB")
    s = min(max_w / im.width, max_h / im.height)
    w, h = max(1, int(im.width * s)), max(1, int(im.height * s))
    img.paste(im.resize((w, h), Image.LANCZOS), (x, y))
    return w, h


def braced(d, x, y, text: str, size_t: int, size_b: int, acc, fill=INK) -> None:
    """Текст в фигурных скобках — наша разметка смысла."""
    fb, ft = _font(MONT_BLACK, size_b), _font(INTER_SB, size_t)
    d.text((x, y), "{", font=fb, fill=acc)
    tx = x + d.textlength("{", font=fb) + 14
    d.text((tx, y + (size_b - size_t) // 2 + 4), text, font=ft, fill=fill)
    d.text((tx + d.textlength(text, font=ft) + 14, y), "}", font=fb, fill=acc)


def cover(path, photo, title_lines: list[str], sub: str, acc, total: int = 8):
    """Обложка: фото ЦЕЛЬНЫМ кадром, текст поверх снизу."""
    img = fit_box(photo, W, H)
    ys = np.arange(H)[:, None].astype(float)
    a = np.clip(30 + np.where(ys > H - 760, (ys - (H - 760)) / 760 * 215, 0), 0, 232)
    img = Image.composite(Image.new("RGB", (W, H), (14, 15, 16)), img,
                          Image.fromarray(np.repeat(a.astype("uint8"), W, axis=1).reshape(H, W)))
    d = ImageDraw.Draw(img)
    header(img, d, 1, total, light=True)
    fh, _fs = fit_font(d, " ".join(title_lines), W - 2 * M, 96, floor=56)
    y = H - 280 - len(title_lines) * 102
    for ln in title_lines:
        d.text((M, y), ln.upper(), font=fh, fill=WHITE); y += 102
    braced(d, M, y + 10, sub, 38, 58, acc, fill=WHITE)
    img.save(path); return path


def step(path, idx: int, num: str | None, title: str, body: str, acc,
         photo=None, total: int = 8):
    """Слайд приёма: снимок ЦЕЛИКОМ сверху (в родных пропорциях), под ним
    заголовок и текст. num не рисуется — счётчики отклонены."""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    header(img, d, idx, total)
    y = 200
    if photo:
        pw, ph = photo_whole(img, photo, M, y, W - 2 * M, 620)
        d = ImageDraw.Draw(img)
        y += ph + 60
    fh, fs = fit_font(d, title, W - 2 * M, 76)
    for ln in wrap(d, title.upper(), fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += int(fs * 1.16)
    y += 8
    fb = _font(INTER_MED, 38)
    for ln in wrap(d, body, fb, W - 2 * M):
        d.text((M, y), ln, font=fb, fill=GREY); y += 50
    img.save(path); return path


def bullets(path, idx: int, heading: str, items: list[str], acc,
            note: str | None = None, total: int = 8):
    """Слайд-список с маркерами в цвете продукта."""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    header(img, d, idx, total)
    y = 240
    fh, fs = fit_font(d, heading, W - 2 * M, 76)
    for ln in wrap(d, heading.upper(), fh, W - 2 * M):
        d.text((M, y), ln, font=fh, fill=INK); y += int(fs * 1.16)
    y += 30
    fb = _font(INTER_SB, 40)
    for it in items:
        d.rectangle([M, y + 16, M + 18, y + 34], fill=acc)
        for ln in wrap(d, it, fb, W - 2 * M - 52):
            d.text((M + 44, y), ln, font=fb, fill=INK); y += 52
        y += 26
    if note:
        y += 20
        for ln in wrap(d, note, mono(28), W - 2 * M):
            d.text((M, y), ln, font=mono(28), fill=GREY); y += 42
    img.save(path); return path


def product(path, jar, name: str, art: str, rows: list[tuple], acc,
            note: str = "Цифры с этикетки, а не из рекламы.", total: int = 8):
    """Финал: банка целиком + шкалы % от суточной нормы."""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    header(img, d, total, total)
    # СНАЧАЛА ставим банку — от её реального левого края считаем колонку под имя.
    # Ширина «на глаз» не годится: банки разной формы, и название упирается в неё.
    j = Image.open(jar).convert("RGBA")
    jh = int(H * 0.40)
    j = j.resize((int(j.width * jh / j.height), jh), Image.LANCZOS)
    jar_x = W - M - j.width
    img.paste(j, (jar_x, 210), j)
    d = ImageDraw.Draw(img)
    # Имя рисуется ОДНОЙ строкой без переноса, поэтому меряем строку ЦЕЛИКОМ,
    # а не самое длинное слово: «МАГНИЙ ЦИТРАТ» пословно влезал, а вместе — нет.
    name_w = jar_x - M - 48                                    # 48 px воздуха до банки
    fs = 78
    while fs > 34 and d.textlength(name.upper(), font=_font(MONT_BLACK, fs)) > name_w:
        fs -= 2
    d.text((M, 230 + (78 - fs) // 2), name.upper(),
           font=_font(MONT_BLACK, fs), fill=INK)
    braced(d, M, 330, f"арт. {art}", 30, 46, acc, fill=GREY)
    y = 700
    d.text((M, y), "ЧТО В ПОРЦИИ", font=_font(MONT_BLACK, 40), fill=INK)
    d.text((M, y + 56), "% от суточной нормы", font=mono(26), fill=GREY)
    y += 118
    bw = 700
    for nm, amount, pct in rows:
        d.text((M, y), nm, font=_font(INTER_SB, 34), fill=INK)
        d.text((M + 330, y + 4), amount, font=mono(28), fill=GREY)
        by = y + 48
        d.rectangle([M, by, M + bw, by + 12], fill=RAIL)
        d.rectangle([M, by, M + int(bw * min(pct, 100) / 100), by + 12], fill=acc)
        if pct > 100:                     # засечка нормы: видно, что это больше 100%
            d.rectangle([M + bw - 3, by - 6, M + bw + 3, by + 18], fill=INK)
        d.text((M + bw + 24, by - 10), f"{pct}%", font=_font(MONT_BLACK, 34), fill=acc)
        y = by + 52
    for ln in wrap(d, note, mono(24), W - 2 * M):
        d.text((M, y + 14), ln, font=mono(24), fill=GREY); y += 34
    img.save(path); return path

def trigger(path, idx: int, photo, want: str, need: str, art: str, jar,
            acc, total: int = 8):
    """Слайд «тяга → продукт»: фото слева, продукт справа, деление РОВНО пополам.

    Подписи в фигурных скобках { хочется } / { пью }."""
    img = Image.new("RGB", (W, H), CREAM)
    left = W // 2
    ph = fit_box(photo, left, H)
    img.paste(ph, (0, 0))
    # затемняющий градиент сверху под белые подписи
    ys = np.arange(H)[:, None].astype(float)
    a = np.clip(np.where(ys < 560, (560 - ys) / 560 * 190, 0), 0, 190).astype("uint8")
    ov = Image.fromarray(np.repeat(a, left, axis=1).reshape(H, left))
    img.paste(Image.composite(Image.new("RGB", (left, H), (14, 15, 16)),
                              img.crop((0, 0, left, H)), ov), (0, 0))
    d = ImageDraw.Draw(img)
    # полоса-заряд ЧЕРЕЗ ВЕСЬ слайд, а не по одной колонке. Подложка рисуется
    # двумя кусками: над фото — полупрозрачным белым, над кремом — серым, иначе
    # на тёмной половине её не видно.
    rx = left + 40
    rw = W - rx - M
    bar_y, bar_h = 122, 7
    rail_l = Image.new("RGBA", (left - M, bar_h), (255, 255, 255, 90))
    img.paste(rail_l, (M, bar_y), rail_l)
    d.rectangle([left, bar_y, W - M, bar_y + bar_h], fill=RAIL)
    fw_bar = int((W - 2 * M) * idx / total)
    if fw_bar > 0:
        img.paste(_gradient((fw_bar, bar_h), LIME, TEAL, vertical=False), (M, bar_y))
    braced(d, M, 200, "хочется", 34, 52, acc, fill=WHITE)
    lw = left - M - 30
    fs_w = 64
    while fs_w > 34 and max(d.textlength(w, font=_font(MONT_BLACK, fs_w))
                            for w in want.upper().split()) > lw:
        fs_w -= 2
    fw = _font(MONT_BLACK, fs_w)
    y = 290
    for ln in wrap(d, want, fw, lw):
        d.text((M, y), ln.upper(), font=fw, fill=WHITE); y += int(fs_w * 1.16)
    braced(d, rx, 200, "пью", 34, 52, acc)
    # название ужимаем, пока не влезет в колонку — длинные имена товаров у нас есть
    y = 290
    fs = 54
    while fs > 30 and max(d.textlength(w, font=_font(MONT_BLACK, fs))
                          for w in need.upper().split()) > rw:
        fs -= 2
    fn = _font(MONT_BLACK, fs)
    for ln in wrap(d, need, fn, rw):
        d.text((rx, y), ln.upper(), font=fn, fill=INK); y += int(fs * 1.16)
    d.text((rx, y + 10), f"арт. {art}", font=mono(26), fill=GREY)
    j = Image.open(jar).convert("RGBA")
    jh = int(H * 0.46)
    j = j.resize((int(j.width * jh / j.height), jh), Image.LANCZOS)
    jx = rx + max(0, (rw - j.width) // 2)
    img.paste(j, (jx, H - jh - 130), j)
    img.save(path); return path


def scenarios(path, idx: int, name: str, art: str, jar, cases: list[tuple],
              acc, total: int = 8):
    """Слайд «два сценария»: название крупно, банка слева, справа две ситуации.

    У конкурента к банке идут пунктирные выноски. У нас вместо пунктира под
    каждым сценарием короткая шкала % от нормы — фактура, которой у них нет.
    cases = [(заголовок, текст, (вещество, мг, %)), ...]"""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    header(img, d, idx, total)
    # имя ужимаем под колонку СЛЕВА ОТ БАНКИ, иначе заезжает под неё
    name_w = W - 2 * M - int(W * 0.30)
    fn, fs = fit_font(d, name, name_w, 82, floor=40)
    d.text((M, 210 + (82 - fs) // 2), name.upper(), font=fn, fill=INK)
    braced(d, M, 312, f"арт. {art}", 28, 44, acc, fill=GREY)
    j = Image.open(jar).convert("RGBA")
    jh = int(H * 0.44)
    j = j.resize((int(j.width * jh / j.height), jh), Image.LANCZOS)
    img.paste(j, (M, 430), j)
    d = ImageDraw.Draw(img)
    cx = M + j.width + 50
    cw = W - cx - M
    y = 430
    for title, body, bar in cases:
        d.text((cx, y), title, font=_font(MONT_BLACK, 40), fill=INK); y += 52
        for ln in wrap(d, body, _font(INTER_MED, 34), cw):
            d.text((cx, y), ln, font=_font(INTER_MED, 34), fill=GREY); y += 44
        if bar:
            nm, amount, pct = bar
            y += 12
            d.text((cx, y), f"{nm} · {amount}", font=mono(24), fill=GREY); y += 34
            d.rectangle([cx, y, cx + cw, y + 10], fill=RAIL)
            d.rectangle([cx, y, cx + int(cw * min(pct, 100) / 100), y + 10], fill=acc)
            d.text((cx, y + 22), f"{pct}% от нормы", font=mono(22), fill=acc)
            y += 60
        y += 34 if bar else 56
    img.save(path); return path
