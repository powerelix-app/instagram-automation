"""«Сделай похожий» для сравнительных инфографик (N товаров в одном кадре).

Пайплайн: референс (напр. с Pinterest) + N наших реальных банок → gpt-image-2
рисует чистую фото-сцену под референс → поверх НЕ AI-текстом, а Pillow
накладываются чек-листы пользы (утверждённые формулировки бренда из
product_assets.json/brand_powerelix.json), дозировка и жирная строка артикулов
WB. AI на мелком многоколоночном тексте коверкает буквы — поэтому текст всегда
отдельным слоем, как и во всём остальном контент-заводе."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from .. import config, products
from ..db.base import session_scope
from ..db.models import Comparison, GenJob
from . import catalog

log = logging.getLogger(__name__)

FONTS = config.ROOT / "assets" / "fonts"
DARK = (30, 34, 45)
GREY = (75, 78, 88)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _load_assets() -> dict:
    from .. import brand_overlay as bo
    return bo._load_assets()


def _clog(cid: int, msg: str, reset: bool = False) -> None:
    """Строка в лог генерации сравнения → раздаётся как /media/comparisons/<cid>_gen.log
    (страница опрашивает его каждые 3с, как у раскадровок)."""
    from datetime import datetime
    try:
        p = config.MEDIA_DIR / "comparisons" / f"{cid}_gen.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w" if reset else "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')}  {msg}\n")
    except Exception:
        pass


def auto_pick_products(ref_bytes: bytes) -> List[str]:
    """Claude-vision смотрит на референс-сравнение и подбирает НАШИ товары под то,
    что на картинке (по категории/цели), в порядке слева направо. [] если не смог.
    Нужно, когда пользователь не отметил галочки — 'возьми те, что на картинке'."""
    import base64
    import io

    import anthropic
    from pydantic import BaseModel, Field

    brand = products.load_brand()
    cat_lines = []
    for p in brand["products"]:
        ben = ", ".join(p.get("key_benefits_3", []))
        cat_lines.append(f'#{p["id"]} {p.get("full_name", p["name"])} — {ben}')
    catalog_txt = "\n".join(cat_lines)

    class _Pick(BaseModel):
        product_ids: list[str] = Field(description="id НАШИХ товаров под то, что на картинке, слева направо, 2-6 штук")
        reason: str = ""

    im = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    if im.width > 1024:
        im = im.resize((1024, int(im.height * 1024 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text":
            "Это сравнительная инфографика БАДов/добавок (несколько товаров или целей в одном кадре). "
            "Определи, про какие категории/цели здоровья она (напр. похудение, сон, иммунитет, кожа, "
            "гормоны, энергия). Из НАШЕЙ линейки ниже подбери товары, максимально близкие по ЦЕЛИ к тому, "
            "что на картинке, в том же порядке слева направо. Столько же товаров, сколько на референсе "
            "(но 2-6). Верни только id.\n\nНАША ЛИНЕЙКА:\n" + catalog_txt},
    ]
    try:
        client = anthropic.Anthropic()
        resp = client.messages.parse(model=config.CLAUDE_MODEL, max_tokens=400,
                                     messages=[{"role": "user", "content": content}], output_format=_Pick)
        picked = resp.parsed_output.product_ids
        reason = resp.parsed_output.reason
    except Exception as e:
        log.warning("auto-pick сравнение упал: %s", e)
        return []
    valid: List[str] = []
    for pid in picked:
        pid = str(pid).strip().lstrip("#")
        if products.product_by_id(pid) and pid not in valid:
            valid.append(pid)
    log.info("auto-pick сравнение: %s (%s)", valid, (reason or "")[:100])
    return valid[:6]


def analyze_reference(ref_bytes: bytes) -> str:
    """Vision определяет ФОРМАТ инфографики → какой шаблон собирать.
    'symptom' (симптом→продукт) | 'lineup' (товары в ряд + чек-листы). Дефолт 'symptom'."""
    import base64
    import io
    from typing import Literal

    import anthropic
    from pydantic import BaseModel

    class _Fmt(BaseModel):
        format: Literal["symptom", "lineup"]
        reason: str = ""

    im = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    if im.width > 1024:
        im = im.resize((1024, int(im.height * 1024 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text":
            "Определи тип инфографики БАДов:\n"
            "- 'symptom' — формат «симптом → продукт»: слева боль/состояние (живот, отёки, лицо, "
            "усталость, туман), стрелка, справа товар. Часто подписи «ЕСЛИ У ТЕБЯ… ТОГДА ПЕЙ».\n"
            "- 'lineup' — товары стоят в один ряд рядом, сверху/сбоку колонки пользы (чек-листы), "
            "сравнение нескольких продуктов в одном кадре.\n"
            "Верни format."},
    ]
    try:
        client = anthropic.Anthropic()
        resp = client.messages.parse(model=config.CLAUDE_MODEL, max_tokens=150,
                                     messages=[{"role": "user", "content": content}], output_format=_Fmt)
        log.info("analyze reference: %s (%s)", resp.parsed_output.format, resp.parsed_output.reason[:80])
        return resp.parsed_output.format
    except Exception as e:
        log.warning("analyze reference fail: %s — дефолт symptom", e)
        return "symptom"


def create(ref_bytes: bytes, ref_filename: str, product_ids: List[str], title: str = "",
           style: str = "lineup") -> int:
    """Сохраняет референс и список товаров, статус пустой (не в очереди).
    style='auto' → формат определяется по картинке; product_ids пуст → авто-подбор товаров."""
    ext = Path(ref_filename or "").suffix.lower() or ".jpg"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("формат не поддерживается (PNG/JPG/WEBP)")
    if style == "auto":
        style = analyze_reference(ref_bytes)
    product_ids = [str(p).strip() for p in (product_ids or []) if str(p).strip()]
    if not product_ids:  # галочки не стоят — берём те, что на картинке
        product_ids = auto_pick_products(ref_bytes)
        if not product_ids:
            raise ValueError("не смог распознать товары на картинке — отметь их галочками вручную")
    if not (2 <= len(product_ids) <= 6):
        raise ValueError("нужно 2–6 товаров (авто-подбор нашёл меньше — выбери вручную)"
                         if len(product_ids) < 2 else "не больше 6 товаров")
    dest_dir = config.MEDIA_DIR / "comparisons"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as s:
        c = Comparison(title=title.strip(), product_ids=list(product_ids),
                       style=style if style in ("lineup", "symptom") else "lineup")
        s.add(c)
        s.flush()
        cid = c.id
        ref_name = f"ref_{cid}{ext}"
        (dest_dir / ref_name).write_bytes(ref_bytes)
        c.ref_path = f"/media/comparisons/{ref_name}"
    stored_style = style if style in ("lineup", "symptom") else "lineup"
    fmt_ru = {"symptom": "симптом → продукт", "lineup": "банки в ряд + чек-листы"}[stored_style]
    _clog(cid, "референс принят", reset=True)
    _clog(cid, f"формат макета: {fmt_ru}")
    names = ", ".join((products.product_by_id(p) or {}).get("name", p) for p in product_ids)
    _clog(cid, f"товары в колонки: {names}")
    _clog(cid, "поставлено в очередь генерации…")
    return cid


def create_by_url(url: str, product_ids: List[str], title: str = "", style: str = "lineup") -> int:
    """Тот же механизм, что в разведке: скачивает референс по ссылке
    (Pinterest пин / IG-пост) вместо загрузки файла руками."""
    from . import recon
    reel_id = recon.add_reel_by_url(url.strip())
    if not reel_id:
        raise ValueError("не удалось разобрать ссылку — проверь URL Pinterest/IG")
    frames = sorted((config.MEDIA_DIR / "frames" / str(reel_id)).glob("f*.jpg"))
    if not frames:
        raise ValueError("не удалось скачать изображение по ссылке")
    return create(frames[0].read_bytes(), frames[0].name, product_ids, title, style)


def list_all() -> List[dict]:
    with session_scope() as s:
        rows = s.query(Comparison).order_by(Comparison.id.desc()).all()
        return [{
            "id": r.id, "title": r.title, "ref_path": r.ref_path,
            "product_ids": r.product_ids or [], "gen_status": r.gen_status,
            "output_path": r.output_path,
        } for r in rows]


def get(comparison_id: int) -> Optional[dict]:
    with session_scope() as s:
        r = s.get(Comparison, comparison_id)
        if not r:
            return None
        return {
            "id": r.id, "title": r.title, "ref_path": r.ref_path,
            "product_ids": r.product_ids or [], "gen_status": r.gen_status,
            "gen_error": r.gen_error, "output_path": r.output_path,
        }


def delete(comparison_id: int) -> None:
    with session_scope() as s:
        r = s.get(Comparison, comparison_id)
        if not r:
            return
        for p in (r.ref_path, r.output_path):
            if p:
                (config.DATA_DIR / p.lstrip("/")).unlink(missing_ok=True)
        s.delete(r)


def enqueue(comparison_id: int) -> bool:
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if not c:
            return False
        if c.gen_status and c.gen_status not in ("", "done", "error"):
            return False
        dup = s.query(GenJob).filter(
            GenJob.comparison_id == comparison_id, GenJob.kind == "comparison",
            GenJob.status.in_(("queued", "running"))).first()
        if dup:
            return False
        s.add(GenJob(comparison_id=comparison_id, kind="comparison", status="queued"))
        c.gen_status = "в очереди…"
        c.gen_error = ""
    return True


def _column_data(pid: str) -> dict:
    p = products.product_by_id(pid) or {}
    assets = _load_assets().get(str(pid), {})
    link = catalog.get_link(str(pid)) or {}
    title = assets.get("title") or (p.get("name") or "").upper()
    accent = assets.get("accent") or "#213D87"
    items = (p.get("key_benefits_3") or [])[:4]
    return {"title": title, "accent": _hex(accent), "items": items,
            "art": link.get("nmid") or ""}


def _wrap(d, text: str, font, maxw: float) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
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


def _render(photo: Image.Image, columns: List[dict]) -> Image.Image:
    """Чек-листы на светлом верхе фото, жирная строка артикулов на низе.
    Рассчитано на референс-стиль «товар на светлой/мраморной поверхности,
    воздух сверху и снизу» — для другой композиции референса может понадобиться
    доводка руками."""
    n = len(columns)
    W = 1080
    scale = W / photo.width
    H = int(photo.height * scale)
    canvas = photo.resize((W, H)).convert("RGB")
    d = ImageDraw.Draw(canvas)

    f_title = _font("montserrat-black.ttf", 42 if n <= 3 else 34)
    f_item = _font("Inter-Medium.otf", 24 if n <= 3 else 20)
    f_article = _font("Inter-ExtraBold.otf", 28 if n <= 4 else 22)

    M, GUTTER = 44, 24
    col_w = (W - 2 * M - (n - 1) * GUTTER) // n

    top_y = 40
    for i, col in enumerate(columns):
        x = M + i * (col_w + GUTTER)
        ty = top_y
        for ln in _wrap(d, col["title"], f_title, col_w):
            d.text((x, ty), ln, font=f_title, fill=DARK)
            ty += f_title.size + 6
        ty += 12
        for item in col["items"]:
            lines = _wrap(d, item, f_item, col_w - 34)
            r = 9
            cy = ty + 10
            d.ellipse([x, cy - r, x + 2 * r, cy + r], outline=col["accent"], width=3)
            d.line([x + 5, cy, x + r, cy + r - 2], fill=col["accent"], width=3)
            d.line([x + r, cy + r - 2, x + 2 * r + 3, cy - r + 3], fill=col["accent"], width=3)
            ix, iy = x + 2 * r + 12, ty
            for ln in lines:
                d.text((ix, iy), ln, font=f_item, fill=GREY)
                iy += f_item.size + 5
            ty = iy + 12

    arts = [c["art"] for c in columns if c["art"]]
    if arts:
        art_y = H - (60 if n <= 4 else 78)
        line = "АРТИКУЛ НА WB: " + "  |  ".join(f"#{a}" for a in arts)
        lw = d.textlength(line, font=f_article)
        if lw > W - 2 * M:  # не влезло в одну строку — переносим
            half = len(arts) // 2
            l1 = "  |  ".join(f"#{a}" for a in arts[:half or 1])
            l2 = "  |  ".join(f"#{a}" for a in arts[half or 1:])
            for k, ln in enumerate((l1, l2)):
                lw = d.textlength(ln, font=f_article)
                d.text(((W - lw) // 2, art_y + k * (f_article.size + 10)), ln, font=f_article, fill=DARK)
        else:
            d.text(((W - lw) // 2, art_y), line, font=f_article, fill=DARK)
    return canvas


# ─────────────────────────────────────────────────────────────────────────
# Стиль «симптом → продукт» (ЕСЛИ У ТЕБЯ … ТОГДА ПЕЙ) — фирменный формат POWERELIX.
# Раскладку и весь текст рисует Pillow (чётко), AI генерит только иллюстрации симптомов.
# ─────────────────────────────────────────────────────────────────────────
_BG = (241, 235, 223)     # бежевый фон
_CARD = (252, 249, 243)   # карточка
_PILL_L = (122, 160, 90)  # плашка «ЕСЛИ У ТЕБЯ»
_PILL_R = (66, 108, 140)  # плашка «ТОГДА ПЕЙ»
_LINE = (150, 150, 155)

_SYMPTOM_MAP = None


def _symptom_for(pid: str) -> dict:
    """Симптом + промпт иллюстрации для продукта (из data/symptom_map.json)."""
    global _SYMPTOM_MAP
    if _SYMPTOM_MAP is None:
        import json
        try:
            _SYMPTOM_MAP = json.loads((config.DATA_DIR / "symptom_map.json").read_text(encoding="utf-8"))
        except Exception:
            _SYMPTOM_MAP = {}
    m = _SYMPTOM_MAP.get(str(pid))
    if m:
        return m
    p = products.product_by_id(str(pid)) or {}
    ben = (p.get("key_benefits_3") or ["поддержка организма"])[0]
    return {"symptom": ben, "illo": f"человек, забота о здоровье, {ben.lower()}"}


def _short_name(pid: str) -> str:
    a = _load_assets().get(str(pid), {})
    if a.get("short"):
        return a["short"].upper()
    p = products.product_by_id(str(pid)) or {}
    return (p.get("name") or "").upper()


def _rrect(d, box, radius, **kw):
    """rounded_rectangle с фолбэком на обычный прямоугольник (старый Pillow)."""
    try:
        d.rounded_rectangle(box, radius=radius, **kw)
    except Exception:
        d.rectangle(box, **kw)


def _pill(d, text, font, x0, x1, y, color):
    tw = d.textlength(text, font=font)
    cx = (x0 + x1) // 2
    px, py = 28, 13
    h = font.size + 2 * py
    _rrect(d, [cx - tw // 2 - px, y, cx + tw // 2 + px, y + h], radius=h // 2, fill=color)
    d.text((cx - tw // 2, y + py), text, font=font, fill=(255, 255, 255))


def _bottle_cutout(path: Path, target_h: int) -> Image.Image:
    """Реальная банка с белого фона → вырез (белое в прозрачность) нужной высоты.
    Уменьшаем СРАЗУ (исходники ~12МП — попиксельный цикл на полном разрешении съест память)."""
    im = Image.open(path).convert("RGBA")
    work_h = target_h * 2  # рабочее разрешение для чистого выреза, но не 12МП
    if im.height > work_h:
        im = im.resize((max(1, int(im.width * work_h / im.height)), work_h), Image.LANCZOS)
    data = [(r, g, b, 0) if (r > 242 and g > 242 and b > 242) else (r, g, b, a)
            for r, g, b, a in im.getdata()]
    im.putdata(data)
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w = max(1, int(im.width * target_h / im.height))
    return im.resize((w, target_h), Image.LANCZOS)


def _draw_glass(canvas, x, y, w, h, accent):
    """Простой стакан с жидкостью акцентного цвета (Pillow)."""
    d = ImageDraw.Draw(canvas)
    bl, br = x + int(w * 0.12), x + int(w * 0.88)
    lh = int(h * 0.58)
    ly = y + h - lh
    frac = (ly - y) / h
    fl = x + int((bl - x) * frac)
    fr = (x + w) - int((x + w - br) * frac)
    d.polygon([(fl, ly), (fr, ly), (br, y + h), (bl, y + h)], fill=tuple(accent))
    d.line([(x, y), (bl, y + h)], fill=_LINE, width=4)
    d.line([(x + w, y), (br, y + h)], fill=_LINE, width=4)
    d.line([(bl, y + h), (br, y + h)], fill=_LINE, width=4)
    d.ellipse([x, y - 7, x + w, y + 7], outline=_LINE, width=4)


def _beige_base() -> Path:
    """Бежевая подложка 1024² — вход для fal edit-эндпоинта (он перерисует по промпту)."""
    import tempfile
    base = Image.new("RGB", (1024, 1024), _BG)
    tf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    base.save(tf.name)
    return Path(tf.name)


# Единый рисованный стиль иллюстраций симптомов (как в фирменном референсе POWERELIX).
_ILLO_STYLE = ("плоская минималистичная векторная иллюстрация flat illustration, тёплая "
               "бежево-пастельная палитра, мягкие простые формы, единый нежный стиль, это РИСУНОК "
               "(не фотография, без фотореализма, без 3d), без текста и букв")


def _symptom_illo(prompt: str, cid: int, idx: int):
    """AI-иллюстрация симптома (рисованный flat-стиль, бежевые тона, без текста). Path или None.
    gemini (ProxyAPI, если есть баланс) → фолбэк fal-seedream по бежевой подложке."""
    from . import producer
    full = _ILLO_STYLE + ": " + prompt
    out = config.MEDIA_DIR / "comparisons" / f"{cid}_sym{idx}.png"
    try:
        img = producer.gen_image(full, ref=None, aspect="1:1", style_suffix=_ILLO_STYLE)
        out.write_bytes(img)
        return out
    except Exception as e1:
        log.warning("symptom illo %s gemini fail (%s) — fal seedream", idx, e1)
    try:
        base = _beige_base()
        img = producer.gen_image_seedream("полностью перерисуй это изображение как " + full,
                                          [base], aspect="1:1")
        try:
            base.unlink()
        except Exception:
            pass
        out.write_bytes(img)
        return out
    except Exception as e2:
        log.warning("symptom illo %s seedream fail: %s", idx, e2)
        return None


def _render_symptom(rows: List[dict], out_path=None) -> Image.Image:
    """Инфографика «ЕСЛИ У ТЕБЯ (симптом) → ТОГДА ПЕЙ (продукт + артикул WB)»."""
    n = len(rows)
    W, HEAD, ROW, FOOT = 1080, 250, 214, 100
    H = HEAD + n * ROW + FOOT
    canvas = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(canvas)

    # header: вордмарк + две плашки
    f_word = _font("montserrat-black.ttf", 60)
    ww = d.textlength("POWERELIX", font=f_word)
    d.text(((W - ww) // 2, 46), "POWERELIX", font=f_word, fill=DARK)
    f_pill = _font("Inter-ExtraBold.otf", 30)
    _pill(d, "ЕСЛИ У ТЕБЯ:", f_pill, 40, 486, 150, _PILL_L)
    _pill(d, "ТОГДА ПЕЙ:", f_pill, 590, 1040, 150, _PILL_R)

    LX0, LX1, RX0, RX1 = 40, 486, 590, 1040
    f_sym = _font("Inter-ExtraBold.otf", 31)
    f_name = _font("montserrat-black.ttf", 33)
    f_art = _font("Inter-ExtraBold.otf", 25)

    for i, row in enumerate(rows):
        band = HEAD + i * ROW
        y0, y1 = band + 12, band + ROW - 12
        accent = row["accent"]
        cy = (y0 + y1) // 2

        # левая карточка: иллюстрация симптома + подпись
        _rrect(d, [LX0, y0, LX1, y1], 26, fill=_CARD)
        sz = (y1 - y0) - 28
        ix, iy = LX0 + 16, y0 + 14
        placed = False
        if row.get("illo"):
            try:
                il = Image.open(row["illo"]).convert("RGB").resize((sz, sz), Image.LANCZOS)
                mask = Image.new("L", (sz, sz), 0)
                _rrect(ImageDraw.Draw(mask), [0, 0, sz, sz], 20, fill=255)
                canvas.paste(il, (ix, iy), mask)
                placed = True
            except Exception as e:
                log.warning("illo paste fail: %s", e)
        if not placed:
            _rrect(d, [ix, iy, ix + sz, iy + sz], 20, fill=tuple(accent))
        tx = ix + sz + 20
        slines = str(row["symptom"]).split("\n")
        ty = cy - len(slines) * (f_sym.size + 6) // 2
        for ln in slines:
            d.text((tx, ty), ln, font=f_sym, fill=DARK)
            ty += f_sym.size + 6

        # стрелка
        d.line([LX1 + 14, cy, RX0 - 26, cy], fill=tuple(accent), width=9)
        d.polygon([(RX0 - 26, cy - 15), (RX0 - 26, cy + 15), (RX0 - 4, cy)], fill=tuple(accent))

        # правая карточка: стакан + банка + название + артикул
        _rrect(d, [RX0, y0, RX1, y1], 26, fill=_CARD)
        bh = (y1 - y0) - 26
        bx = RX1 - 24
        try:
            bottle = _bottle_cutout(row["bottle"], bh)
            bx = RX1 - bottle.width - 20
            canvas.paste(bottle, (bx, y0 + 13), bottle)
        except Exception as e:
            log.warning("bottle cutout fail: %s", e)
        _draw_glass(canvas, RX0 + 24, y0 + 30, 68, bh - 24, accent)
        nx = RX0 + 108
        nlines = _wrap(d, row["title"], f_name, max(140, bx - nx - 14))
        nh = len(nlines) * (f_name.size + 4) + 46
        ny = cy - nh // 2
        for ln in nlines:
            d.text((nx, ny), ln, font=f_name, fill=DARK)
            ny += f_name.size + 4
        if row.get("art"):
            badge = f"#{row['art']}"
            bw = d.textlength(badge, font=f_art)
            _rrect(d, [nx, ny + 6, nx + bw + 26, ny + 6 + 40], 12, fill=DARK)
            d.text((nx + 13, ny + 14), badge, font=f_art, fill=(255, 255, 255))

    # футер
    d.rectangle([0, H - FOOT + 18, W, H], fill=DARK)
    f_foot = _font("montserrat-black.ttf", 33)
    ft = "Ищи артикул на WILDBERRIES"
    fw = d.textlength(ft, font=f_foot)
    d.text(((W - fw) // 2, H - FOOT + 36), ft, font=f_foot, fill=(255, 255, 255))

    if out_path:
        canvas.save(out_path)
    return canvas


def _execute_symptom(comparison_id: int, product_ids: List[str]) -> None:
    """Сборка инфографики «симптом → продукт»: AI-иллюстрации (параллельно) + Pillow-макет."""
    from concurrent.futures import ThreadPoolExecutor

    from . import producer
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.gen_status = f"генерирую {len(product_ids)} иллюстраций…"
    _clog(comparison_id, f"🎨 формат «симптом → продукт», генерирую {len(product_ids)} иллюстраций параллельно…")
    # илло гоняем параллельно (fal медленный, 5 подряд ≈ 10 мин → разом ≈ 2-3 мин)
    syms = [_symptom_for(pid) for pid in product_ids]

    def _gen(i):
        sym_txt = str(syms[i]["symptom"]).replace("\n", " ")
        r = _symptom_illo(syms[i]["illo"], comparison_id, i)
        _clog(comparison_id, (f"  ✓ иллюстрация: {sym_txt}" if r else f"  ⚠ не вышла: {sym_txt}"))
        return i, r

    illos: dict = {}
    with ThreadPoolExecutor(max_workers=min(6, len(product_ids))) as ex:
        for i, path in ex.map(_gen, range(len(product_ids))):
            illos[i] = path

    _clog(comparison_id, "🖼 собираю макет (банки, стаканы, текст, артикулы)…")
    rows = []
    for idx, pid in enumerate(product_ids):
        col = _column_data(pid)
        rows.append({
            "symptom": syms[idx]["symptom"], "illo": illos.get(idx),
            "bottle": producer._product_ref(pid),
            "accent": col["accent"], "title": _short_name(pid), "art": col["art"],
        })
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.gen_status = "собираю макет…"
    out_dir = config.MEDIA_DIR / "comparisons"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{comparison_id}_final.png"
    try:
        _render_symptom(rows, out_path)
    except Exception as e:
        _fail(comparison_id, f"сборка макета не удалась: {e}")
        return
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.output_path = f"/media/comparisons/{out_path.name}"
            c.gen_status = "done"
            c.gen_error = ""
    _clog(comparison_id, "✅ готово — инфографика собрана")


def execute(comparison_id: int) -> None:
    from . import producer  # ленивый импорт — тот же паттерн, что в generator.py
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if not c:
            return
        ref_path = config.DATA_DIR / c.ref_path.lstrip("/")
        product_ids = list(c.product_ids or [])
        style = getattr(c, "style", "lineup") or "lineup"
        c.gen_status = "генерация фото…"

    _clog(comparison_id, "▶️ старт генерации")
    if style == "symptom":
        _execute_symptom(comparison_id, product_ids)
        return
    _clog(comparison_id, "🧴 формат «банки в ряд», генерирую фото-сцену (gpt-image-2)…")

    cols = [_column_data(pid) for pid in product_ids]
    refs = [ref_path]
    missing = []
    for pid in product_ids:
        p = producer._product_ref(pid)
        if p:
            refs.append(p)
        else:
            missing.append(pid)
    if missing:
        _fail(comparison_id, f"нет фото товара(ов) в каталоге: {', '.join(missing)}")
        return

    n = len(product_ids)
    slots = ", ".join(
        f"{['ЛЕВАЯ', 'ВТОРАЯ СЛЕВА', 'СРЕДНЯЯ', 'ВТОРАЯ СПРАВА', 'ПРАВАЯ'][i] if n <= 5 else f'{i+1}-я'} "
        f"— строго как на референсе №{i+2} (форма, крышка, цвет и этикетка СТРОГО как на референсе)"
        for i in range(n)
    )
    prompt = (
        f"ПЕРВОЕ изображение — референс стиля и композиции сравнительной инфографики. "
        f"Пересоздай его композицию, свет, поверхность и настроение (товары в ряд на чистой "
        f"светлой/мраморной поверхности, мягкий студийный свет, воздух сверху и снизу под текст). "
        f"В кадре {n} банок нашего бренда POWERELIX слева направо: {slots}. "
        "Этикетки чёткие, читаемые, повёрнуты к камере, каждая банка целиком в кадре, не обрезана. "
        "Рядом с банками — немного капсул/натуральных элементов у подножия, свежая зелень по краям "
        "кадра (мята/лаванда), мягкие естественные тени. "
        "Формат вертикальный портрет, много свободного пространства сверху (под заголовки) и снизу "
        "(под подпись). Фотореализм, рекламное качество. Без текста, букв и надписей на изображении, "
        "кроме этикеток банок."
    )
    try:
        img_bytes = producer.gen_image_gpt(prompt, refs, aspect="4:5")
    except Exception as e:
        _fail(comparison_id, f"генерация фото не удалась: {e}")
        return

    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.gen_status = "накладываю текст…"
    _clog(comparison_id, "🖼 накладываю чек-листы и артикулы (текст — Pillow)…")

    try:
        import io
        photo = Image.open(io.BytesIO(img_bytes))
        final = _render(photo, cols)
    except Exception as e:
        _fail(comparison_id, f"наложение текста не удалось: {e}")
        return

    out_dir = config.MEDIA_DIR / "comparisons"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{comparison_id}_final.png"
    final.save(out_path)
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.output_path = f"/media/comparisons/{out_path.name}"
            c.gen_status = "done"
            c.gen_error = ""
    _clog(comparison_id, "✅ готово — инфографика собрана")


def _fail(comparison_id: int, reason: str) -> None:
    log.warning("comparison %s failed: %s", comparison_id, reason)
    _clog(comparison_id, f"❌ ошибка: {reason}")
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.gen_status = "error"
            c.gen_error = reason[:500]
