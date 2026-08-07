"""Рич-контент для карточки WB: Берберин с хромом (кабинет Number One).

8 вертикальных блоков 1080×1440 (3:4 — пропорция фото карточки WB).
Оформление под саму банку (красно-чёрная), а не под бежево-мятный POWERELIX.

Данные взяты из карточки nmID 1349759361 (n_Berberine_06): состав, СГР,
количество капсул, срок годности. ⚠️ «500 мг» в описании карточки — это масса
КАПСУЛЫ («капсулы твёрдые желатиновые массой 500 мг±10%»), а не берберина,
поэтому здесь эта цифра не используется как дозировка действующего вещества.

Формулировки намеренно сдержанные: без «нормализует сахар», «сжигает жир»,
без до/после и отзывов — ст. 25 ФЗ «О рекламе» запрещает в рекламе БАД ссылки
на конкретные случаи улучшения состояния.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ig_automation.brand_overlay import _font, _spaced, _hex, MONT_BLACK, INTER_SB, INTER_MED

W, H = 1080, 1440
M = 84
RED = _hex("#E01F28")          # акцент с этикетки
RED_DK = _hex("#8E1219")
INK = (255, 255, 255)
GREY = (168, 170, 176)
BG = (14, 14, 17)
JAR = ("/Users/maksimrogoznikov/Library/Mobile Documents/com~apple~CloudDocs/"
       "Загрузки/Без имени-1.png")
OUT = "output/Рич-контент/berberine_wb"
os.makedirs(OUT, exist_ok=True)


def _bg(glow=True):
    """Тёмный холст с мягким красным свечением из угла."""
    img = Image.new("RGB", (W, H), BG)
    if glow:
        ys, xs = np.mgrid[0:H, 0:W]
        d = np.sqrt((xs - W * 0.85) ** 2 + (ys - H * 0.12) ** 2) / (W * 0.9)
        a = np.clip((1 - d) * 120, 0, 120).astype("uint8")
        ov = Image.fromarray(a)
        img = Image.composite(Image.new("RGB", (W, H), RED_DK), img, ov)
    return img


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


def _mark(d):
    _spaced(d, (M, 62), "BERBERINE", _font(MONT_BLACK, 44), INK, 6)


def _jar(img, scale=0.62, cx=0.72, bottom=90):
    prod = Image.open(JAR).convert("RGBA").crop(Image.open(JAR).getbbox())
    ph = int(H * scale)
    pw = int(prod.width * ph / prod.height)
    prod = prod.resize((pw, ph), Image.LANCZOS)
    x, y = int(W * cx - pw / 2), H - ph - bottom
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([x + pw * .1, y + ph - 40, x + pw * .9, y + ph + 55],
                               fill=(0, 0, 0, 130))
    img.paste(sh.filter(ImageFilter.GaussianBlur(26)), (0, 0),
              sh.filter(ImageFilter.GaussianBlur(26)))
    img.paste(prod, (x, y), prod)


def cover(path):
    img = _bg()
    d = ImageDraw.Draw(img)
    _jar(img, scale=0.60, cx=0.70, bottom=70)
    _mark(d)
    y = 210
    f = _font(MONT_BLACK, 92)
    for ln in ("БЕРБЕРИН", "С ХРОМОМ"):
        d.text((M, y), ln, font=f, fill=INK); y += 98
    d.rectangle([M, y + 14, M + 150, y + 26], fill=RED)
    y += 62
    d.text((M, y), "60 капсул — курс на месяц", font=_font(INTER_SB, 40), fill=GREY)
    y += 88
    for t in ("Контроль аппетита", "Углеводный обмен", "Без кофеина и стимуляторов"):
        d.ellipse([M, y + 12, M + 18, y + 30], fill=RED)
        d.text((M + 40, y), t, font=_font(INTER_SB, 38), fill=INK); y += 62
    img.save(path); return path


def text_slide(path, kicker, title, body, bullets=None, note=None, jar=False):
    img = _bg(glow=not jar)
    d = ImageDraw.Draw(img)
    if jar:
        _jar(img, scale=0.40, cx=0.80, bottom=48)
    _mark(d)
    y = 200
    _spaced(d, (M, y), kicker, _font(MONT_BLACK, 30), RED, 5)
    y += 60
    col = int(W * 0.52) if jar else W - 2 * M
    fh = _font(MONT_BLACK, 68)
    for ln in _wrap(d, title, fh, col):
        d.text((M, y), ln, font=fh, fill=INK); y += 78
    d.rectangle([M, y + 12, M + 130, y + 24], fill=RED)
    y += 62
    if body:
        fb = _font(INTER_SB, 40)
        for ln in _wrap(d, body, fb, col):
            d.text((M, y), ln, font=fb, fill=INK); y += 52
        y += 26
    for b in (bullets or []):
        d.ellipse([M, y + 14, M + 18, y + 32], fill=RED)
        for ln in _wrap(d, b, _font(INTER_MED, 36), col - 46):
            d.text((M + 40, y), ln, font=_font(INTER_MED, 36), fill=GREY); y += 48
        y += 22
    if note:
        y += 16
        for ln in _wrap(d, note, _font(INTER_MED, 32), W - 2 * M):
            d.text((M, y), ln, font=_font(INTER_MED, 32), fill=GREY); y += 42
    img.save(path); return path


def specs_slide(path, rows, note):
    img = _bg(glow=False)
    d = ImageDraw.Draw(img)
    _mark(d)
    y = 200
    _spaced(d, (M, y), "ХАРАКТЕРИСТИКИ", _font(MONT_BLACK, 30), RED, 5)
    y += 66
    d.text((M, y), "Коротко о товаре", font=_font(MONT_BLACK, 68), fill=INK)
    y += 82
    d.rectangle([M, y + 12, M + 130, y + 24], fill=RED)
    y += 66
    fk, fv = _font(INTER_MED, 34), _font(INTER_SB, 36)
    for k, v in rows:
        d.text((M, y), k, font=fk, fill=GREY)
        for i, ln in enumerate(_wrap(d, v, fv, W - 2 * M - 400)):
            d.text((M + 400, y + i * 44), ln, font=fv, fill=INK)
        y += 44 * max(1, len(_wrap(d, v, fv, W - 2 * M - 400))) + 26
        d.line([M, y - 14, W - M, y - 14], fill=(46, 46, 52), width=2)
    y += 20
    for ln in _wrap(d, note, _font(INTER_MED, 30), W - 2 * M):
        d.text((M, y), ln, font=_font(INTER_MED, 30), fill=GREY); y += 40
    img.save(path); return path


# ── блоки ──
cover(f"{OUT}/01.png")

text_slide(f"{OUT}/02.png", "С ЧЕГО ВСЁ НАЧИНАЕТСЯ", "Почему тянет на сладкое",
           "Быстрые углеводы резко поднимают глюкозу, в ответ выбрасывается инсулин "
           "и уводит её вниз — часто ниже, чем было до еды.",
           ["Мозг видит провал и требует быстрых углеводов",
            "Это не слабая воля, а обычная физиология",
            "Чем резче подъём, тем сильнее тяга через пару часов"],
           note="Поэтому «просто меньше есть» работает так плохо: качели никуда не делись.")

text_slide(f"{OUT}/03.png", "СОСТАВ", "Четыре компонента",
           "",
           ["Экстракт плодов барбариса — источник берберина",
            "Экстракт джимнемы",
            "Пиколинат хрома",
            "Витамин B6 (пиридоксина гидрохлорид)"],
           note="Оболочка капсулы — желатин. Наполнитель — МКЦ. Без кофеина "
                "и термогенных стимуляторов.")

text_slide(f"{OUT}/04.png", "ГЛАВНОЕ", "Хром и углеводный обмен",
           "Хром участвует в углеводном обмене — том самом, который стоит за "
           "качелями и тягой к сладкому.",
           ["Витамин B6 участвует в обмене белков и углеводов",
            "Работает мягко и накопительно, а не как разовая встряска",
            "Без кофеина: не мешает сну и не даёт нервозности"],
           jar=True)

text_slide(f"{OUT}/05.png", "КАК ПРИНИМАТЬ", "Схема простая",
           "По 1 капсуле в день во время еды. Банки хватает на месяц.",
           ["Принимать во время еды, а не натощак",
            "Не запивать кофе и крепким чаем",
            "Курс — месяц, дальше перерыв"],
           note="Точную схему смотри на упаковке: она главнее любой картинки.")

text_slide(f"{OUT}/06.png", "ЧЕСТНО", "Когда смотреть на результат",
           "Это добавка накопительного действия, а не разовая встряска.",
           ["Первые изменения по аппетиту — к концу второй-третьей недели",
            "Полный курс — месяц, оценивать имеет смысл по его итогу",
            "Работает вместе с питанием и режимом, а не вместо них"],
           note="Если обещают минус десять килограммов за неделю — это не про добавки.")

text_slide(f"{OUT}/07.png", "ВАЖНО", "Кому не подойдёт",
           "",
           ["Беременным и кормящим",
            "Детям до 18 лет",
            "При индивидуальной непереносимости компонентов",
            "Если принимаете лекарства — сначала посоветуйтесь с врачом"],
           note="БАД не является лекарственным средством и не заменяет "
                "разнообразное питание.")

specs_slide(f"{OUT}/08.png",
            [("Форма выпуска", "капсулы твёрдые желатиновые"),
             ("В упаковке", "60 капсул"),
             ("Курс", "1 месяц"),
             ("Страна производства", "Россия"),
             ("Срок годности", "24 месяца"),
             ("Свидетельство СГР", "AM.01.06.01.003.R.000150.09.25")],
            "Биологически активная добавка к пище «Комплекс Барбариса». "
            "Хранить в сухом месте при температуре не выше 25 °C.")

print("готово →", OUT)
