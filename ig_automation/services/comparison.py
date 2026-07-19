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


def create(ref_bytes: bytes, ref_filename: str, product_ids: List[str], title: str = "") -> int:
    """Сохраняет референс и список товаров, статус пустой (не в очереди)."""
    ext = Path(ref_filename or "").suffix.lower() or ".jpg"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("формат не поддерживается (PNG/JPG/WEBP)")
    if not (2 <= len(product_ids) <= 6):
        raise ValueError("выбери от 2 до 6 товаров")
    dest_dir = config.MEDIA_DIR / "comparisons"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as s:
        c = Comparison(title=title.strip(), product_ids=list(product_ids))
        s.add(c)
        s.flush()
        cid = c.id
        ref_name = f"ref_{cid}{ext}"
        (dest_dir / ref_name).write_bytes(ref_bytes)
        c.ref_path = f"/media/comparisons/{ref_name}"
        return cid


def create_by_url(url: str, product_ids: List[str], title: str = "") -> int:
    """Тот же механизм, что в разведке: скачивает референс по ссылке
    (Pinterest пин / IG-пост) вместо загрузки файла руками."""
    from . import recon
    reel_id = recon.add_reel_by_url(url.strip())
    if not reel_id:
        raise ValueError("не удалось разобрать ссылку — проверь URL Pinterest/IG")
    frames = sorted((config.MEDIA_DIR / "frames" / str(reel_id)).glob("f*.jpg"))
    if not frames:
        raise ValueError("не удалось скачать изображение по ссылке")
    return create(frames[0].read_bytes(), frames[0].name, product_ids, title)


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


def execute(comparison_id: int) -> None:
    from . import producer  # ленивый импорт — тот же паттерн, что в generator.py
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if not c:
            return
        ref_path = config.DATA_DIR / c.ref_path.lstrip("/")
        product_ids = list(c.product_ids or [])
        c.gen_status = "генерация фото…"

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


def _fail(comparison_id: int, reason: str) -> None:
    log.warning("comparison %s failed: %s", comparison_id, reason)
    with session_scope() as s:
        c = s.get(Comparison, comparison_id)
        if c:
            c.gen_status = "error"
            c.gen_error = reason[:500]
