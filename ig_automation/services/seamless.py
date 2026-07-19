"""Бесшовная карусель (техника SYNTX.AI, см. prompt-lab/playbook-carousel.md):
один широкий фон-панорама генерится ОДИН раз и режется на N слайдов — фон
визуально перетекает при свайпе, а не «сменяется». Продукт добавляется
отдельным edit-вызовом поверх КАЖДОГО среза (сам срез — неизменная база,
модель только дорисовывает банку) — так фон гарантированно не плывёт между
слайдами, а не полагаемся на «модель помнит предыдущий кадр».

Честное ограничение: gpt-image-2 отдаёт максимум 1536×1024 за один вызов —
при большом N (6-7) срез приходится ощутимо апскейлить. Для мягких
градиентных/лайфстайл-фонов это не режет глаз, для резкой предметной сцены
на фоне — может."""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import List, Optional

from PIL import Image

from .. import config, overlay
from ..db.base import session_scope
from ..db.models import GenJob, SeamlessCarousel

log = logging.getLogger(__name__)


def create(product_id: str, slides_n: int, theme: str,
          ref_bytes: Optional[bytes] = None, ref_filename: str = "",
          headlines: Optional[List[str]] = None, model_key: str = "",
          slide_scenes: Optional[List[str]] = None) -> int:
    if not (3 <= slides_n <= 7):
        raise ValueError("слайдов должно быть от 3 до 7")
    if not theme.strip() and not ref_bytes:
        raise ValueError("опиши тему фона или приложи референс стиля")
    dest_dir = config.MEDIA_DIR / "seamless"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as s:
        c = SeamlessCarousel(product_id=product_id, slides_n=slides_n, theme=theme.strip(),
                             headlines=headlines or None, model_key=model_key or "",
                             slide_scenes=slide_scenes or None)
        s.add(c)
        s.flush()
        cid = c.id
        if ref_bytes:
            ext = Path(ref_filename or "").suffix.lower() or ".jpg"
            name = f"ref_{cid}{ext}"
            (dest_dir / name).write_bytes(ref_bytes)
            c.ref_path = f"/media/seamless/{name}"
        return cid


def list_all() -> List[dict]:
    with session_scope() as s:
        rows = s.query(SeamlessCarousel).order_by(SeamlessCarousel.id.desc()).all()
        return [{
            "id": r.id, "product_id": r.product_id, "slides_n": r.slides_n,
            "theme": r.theme, "gen_status": r.gen_status,
            "output_paths": r.output_paths or [],
        } for r in rows]


def get(cid: int) -> Optional[dict]:
    with session_scope() as s:
        r = s.get(SeamlessCarousel, cid)
        if not r:
            return None
        return {
            "id": r.id, "product_id": r.product_id, "slides_n": r.slides_n,
            "theme": r.theme, "ref_path": r.ref_path, "headlines": r.headlines or [],
            "model_key": getattr(r, "model_key", "") or "",
            "slide_scenes": getattr(r, "slide_scenes", None) or [],
            "gen_status": r.gen_status, "gen_error": r.gen_error,
            "output_paths": r.output_paths or [],
        }


def delete(cid: int) -> None:
    with session_scope() as s:
        r = s.get(SeamlessCarousel, cid)
        if not r:
            return
        for p in [(r.ref_path or "")] + list(r.output_paths or []):
            if p:
                (config.DATA_DIR / p.lstrip("/")).unlink(missing_ok=True)
        s.delete(r)


def enqueue(cid: int) -> bool:
    with session_scope() as s:
        c = s.get(SeamlessCarousel, cid)
        if not c:
            return False
        if c.gen_status and c.gen_status not in ("", "done", "error"):
            return False
        dup = s.query(GenJob).filter(
            GenJob.seamless_id == cid, GenJob.kind == "seamless",
            GenJob.status.in_(("queued", "running"))).first()
        if dup:
            return False
        s.add(GenJob(seamless_id=cid, kind="seamless", status="queued"))
        c.gen_status = "в очереди…"
        c.gen_error = ""
    return True


def _fail(cid: int, reason: str) -> None:
    log.warning("seamless %s failed: %s", cid, reason)
    with session_scope() as s:
        c = s.get(SeamlessCarousel, cid)
        if c:
            c.gen_status = "error"
            c.gen_error = reason[:500]


def _set(cid: int, **kw) -> None:
    with session_scope() as s:
        c = s.get(SeamlessCarousel, cid)
        if c:
            for k, v in kw.items():
                setattr(c, k, v)


def execute(cid: int) -> None:
    from . import producer  # ленивый импорт, как везде в проекте
    with session_scope() as s:
        c = s.get(SeamlessCarousel, cid)
        if not c:
            return
        product_id, n, theme = c.product_id, c.slides_n, c.theme
        ref_path = (config.DATA_DIR / c.ref_path.lstrip("/")) if c.ref_path else None
        headlines = list(c.headlines or [])
        model_key = getattr(c, "model_key", "") or ""
        slide_scenes = list(getattr(c, "slide_scenes", None) or [])
        c.gen_status = "генерация фона…"

    bottle = producer._product_ref(product_id)
    if not bottle:
        _fail(cid, f"нет фото товара {product_id} в каталоге")
        return

    face = None
    if model_key:
        from . import brand
        face = brand.model_by_key(model_key)

    # дефолтные действия по слайдам, если человек в кадре, а сцены не заданы —
    # разные позы/эмоции одной модели (как в референс-каруселях: живая история)
    _DEFAULT_SCENES = [
        "радостно держит банку двумя руками перед собой, широкая улыбка в камеру",
        "указывает пальцем на банку, приподняв брови — жест «вот оно!»",
        "держит банку у щеки, довольно улыбается с закрытыми глазами",
        "показывает большой палец вверх одной рукой, банка в другой руке",
        "подносит банку ближе к камере на вытянутой руке, этикеткой вперёд",
        "смеётся, слегка запрокинув голову, банка прижата к груди",
        "разводит руки в приглашающем жесте, банка стоит рядом",
    ]

    # ── 1) один широкий фон, без продукта и без текста ──
    bg_prompt = (
        "Широкая панорамная рекламная сцена, минимализм, премиальная эстетика бренда БАД/wellness. "
        f"{theme or 'мягкий градиентный фон в фирменной гамме бренда, лайм и мята, плавные переходы'}. "
        "ОДНА непрерывная сцена без повторяющихся элементов и без швов — свет и цвет меняются "
        "плавно слева направо, единый источник света на всю ширину кадра. "
        "Пустой центр и низ кадра — туда позже добавится продукт, не рисуй никаких предметов, "
        "банок, людей. Без текста, без букв, без надписей, без водяных знаков. Фотореализм, "
        "рекламное качество."
    )
    tmp_dir = config.MEDIA_DIR / "seamless" / f"{cid}_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if ref_path:
        refs = [ref_path]
    else:
        # gen_image_gpt всегда бьёт в images/edits (по всей цепочке фолбэков) —
        # эндпоинту нужна хотя бы одна входная картинка. Без референса стиля
        # подсовываем пустую градиентную затравку — edit-модель дорисует поверх
        # неё полноценную сцену по промпту, как обычный text-to-image.
        seed = Image.new("RGB", (1536, 1024))
        top, bot = (18, 40, 30), (8, 16, 12)
        for y in range(1024):
            t = y / 1024
            seed.paste(tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)), (0, y, 1536, y + 1))
        seed_path = tmp_dir / "seed.png"
        seed.save(seed_path)
        refs = [seed_path]

    try:
        bg_bytes = producer.gen_image_gpt(bg_prompt, refs, aspect="16:9")  # 1536x1024
    except Exception as e:
        _fail(cid, f"генерация фона не удалась: {e}")
        return

    bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
    slide_w, slide_h = 1080, 1350  # 4:5
    strip_w = bg.width // n
    out_paths = []

    for i in range(n):
        _set(cid, gen_status=f"слайд {i + 1}/{n}…")
        # срез фона -> апскейл под целевой холст (cover-fit по высоте)
        strip = bg.crop((i * strip_w, 0, (i + 1) * strip_w, bg.height))
        scale = max(slide_w / strip.width, slide_h / strip.height)
        strip = strip.resize((int(strip.width * scale), int(strip.height * scale)), Image.LANCZOS)
        x0 = (strip.width - slide_w) // 2
        y0 = (strip.height - slide_h) // 2
        strip = strip.crop((x0, y0, x0 + slide_w, y0 + slide_h))
        strip_path = tmp_dir / f"bg_{i}.png"
        strip.save(strip_path)

        if face:
            scene = (slide_scenes[i] if i < len(slide_scenes) and slide_scenes[i].strip()
                     else _DEFAULT_SCENES[i % len(_DEFAULT_SCENES)])
            prev = tmp_dir / f"slide_{i - 1}_clean.png" if i > 0 else None
            chain = prev is not None and prev.exists()
            add_prompt = (
                "ПЕРВОЕ изображение — базовый фон, менять его ЗАПРЕЩЕНО (тот же свет, цвет, "
                "композиция, пиксели фона не трогать). Добавь в кадр НАШУ модель со ВТОРОГО "
                "изображения (то же лицо, та же внешность — не меняй человека) и НАШ продукт "
                "с ТРЕТЬЕГО изображения (форма банки, крышка, цвет и этикетка СТРОГО как на "
                f"референсе, этикетка чёткая и читаемая). ДЕЙСТВИЕ В КАДРЕ: модель {scene}. "
                "ГЕОМЕТРИЯ СТРОГО: человек в кадре по пояс, занимает РОВНО 60% высоты кадра, "
                "стоит по горизонтальному центру, голова не обрезана. "
                + ("ЧЕТВЁРТОЕ изображение — предыдущий слайд этой же серии: одежда, причёска "
                   "и макияж модели ДОЛЖНЫ совпадать с ним точь-в-точь. "
                   if chain else
                   "Одежда модели: однотонный спортивный топ глубокого тёмно-зелёного цвета, "
                   "минимализм, без принтов и логотипов. ")
                + "Свет человека и банки совпадает со светом фона. "
                "Без текста, букв и надписей на изображении, кроме этикетки банки."
            )
            refs_i = [strip_path, face, bottle] + ([prev] if chain else [])
        else:
            add_prompt = (
                "ПЕРВОЕ изображение — базовый фон, менять его ЗАПРЕЩЕНО (тот же свет, цвет, "
                "композиция, пиксели фона не трогать). Добавь ТОЛЬКО наш продукт из ВТОРОГО "
                "изображения — форма банки, крышка, цвет и этикетка СТРОГО как на референсе, "
                "этикетка чёткая и читаемая, банка целиком в кадре. "
                # жёсткая геометрия: одинаковый размер/позиция на ВСЕХ слайдах серии — иначе
                # при свайпе банка «прыгает» (модель сама выбирает масштаб на каждом вызове)
                "РАЗМЕР И ПОЗИЦИЯ СТРОГО: банка занимает РОВНО 45% высоты кадра, "
                "стоит точно по горизонтальному центру, нижний край банки — на 12% выше "
                "нижнего края кадра. Мягкая тень под банкой, свет банки совпадает со светом фона. "
                "Без текста, букв и надписей на изображении, кроме этикетки банки."
            )
            refs_i = [strip_path, bottle]
        try:
            slide_bytes = producer.gen_image_gpt(add_prompt, refs_i, aspect="4:5")
        except Exception as e:
            _fail(cid, f"слайд {i + 1}: продукт не добавился: {e}")
            return

        slide = Image.open(io.BytesIO(slide_bytes)).convert("RGB")
        # чистый слайд (без текста) сохраняем всегда — следующий слайд ссылается
        # на него для консистентности одежды/причёски модели
        clean_path = tmp_dir / f"slide_{i}_clean.png"
        slide.save(clean_path)
        out_path = config.MEDIA_DIR / "seamless" / f"{cid}_{i}.png"
        if i < len(headlines) and headlines[i].strip():
            overlay.render_cover(clean_path, headline=headlines[i].strip(),
                                 subtitle="", tag="", disclaimer="",
                                 out_path=str(out_path), ratio="4:5")
        else:
            slide.save(out_path)
        out_paths.append(f"/media/seamless/{out_path.name}")

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    with session_scope() as s:
        c = s.get(SeamlessCarousel, cid)
        if c:
            c.output_paths = out_paths
            c.gen_status = "done"
            c.gen_error = ""
