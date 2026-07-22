"""Стадия 3 — Генерация: визуал с лицом бренда (Grok) + текст поста (Claude)."""
from __future__ import annotations

import logging
import re
import shutil
from typing import List, Optional

import anthropic
from pydantic import BaseModel, Field

from .. import config, overlay, products, scenes
from . import brand, catalog, compliance
from ..db.base import session_scope
from ..db.models import Post, PostAsset

log = logging.getLogger(__name__)

# Стилевая подпись бренда в каждый визуал-промпт — чтобы кадр был «в духе» POWERELIX.
# Пол/возраст берём из выбранной модели ростера (см. brand.list_models), а не зашиваем —
# иначе текст «девушка» конфликтует с мужским референсом лица и модель начинает
# фантазировать случайных людей вместо привязки к фото.
_STYLE_TAIL = "естественный свет, чистая современная эстетика здоровья и энергии"


def _person_phrase(model_key: str) -> str:
    if (model_key or "").startswith("man_"):
        return "мужчина — то же лицо что на референсе лица, та же внешность"
    return "девушка — то же лицо что на референсе лица, та же внешность"


def _brand_style(model_key: str = "") -> str:
    return f"{_person_phrase(model_key)}; {_STYLE_TAIL}"


# ── Визуал ──

# Убираем из сцены упоминания текста/надписей и CAPS-блоки (это контент плашек —
# AI всё равно рисует его коряво; настоящий текст накладываем оверлеем отдельно).
_TEXT_HINT_RE = re.compile(
    r"(текст на экране|надпис\w*|плашк\w*|кодовое слово|дисклеймер|заголов\w*|субтитр\w*|"
    r"caption|on-?screen)[^.;]*[.;]?", re.IGNORECASE)
_CAPS_RE = re.compile(r"[А-ЯЁA-Z]{3,}(?:[\s,«»\"'–-]+[А-ЯЁA-Z]{2,})*")


def _clean_scene(text: str) -> str:
    text = _TEXT_HINT_RE.sub("", text or "")
    text = _CAPS_RE.sub("", text)
    text = re.sub(r"[«»\"']", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()[:200]


# Claude превращает сценарий-идею (с репликами/тезисами/CTA) в чистое описание ФОТО-КАДРА.
# Регексы _clean_scene не справляются: всё содержание visual_idea — текст-инструкция,
# и модель рисует «ролик с подписями». Поэтому извлекаем только физический кадр.
_SCENE_SYSTEM = """Ты — фотограф. Преврати идею поста в КОРОТКОЕ описание ОДНОГО ФОТО-КАДРА для
нейросети-генератора. Опиши ТОЛЬКО что физически видно в кадре: кто (внешность/поза/эмоция),
где (обстановка/свет), что делает, какой предмет в руках.
СТРОГО НЕЛЬЗЯ упоминать: текст на экране, надписи, заголовки, плашки, реплики/слова героя,
призывы, комментарии, хэштеги, кодовые слова, названия брендов, дисклеймеры, цифры-списки.
Это статичное ФОТО без единой буквы в кадре. Одно-два предложения на русском, без кавычек."""


def _scene_description(visual_idea: str, hook: str, product: str) -> str:
    """Claude → чистая визуальная сцена (без текста/реплик/бренда). Фолбэк — регекс-чистка."""
    raw = (visual_idea or hook or "").strip()
    if not config.ANTHROPIC_API_KEY or not raw:
        return _clean_scene(raw)
    try:
        msg = f"Идея поста: {raw}"
        if product and product not in ("", "—"):
            msg += f"\nВ кадре уместна баночка добавки: {product}"
        resp = anthropic.Anthropic().messages.create(
            model=config.CLAUDE_MODEL, max_tokens=220, system=_SCENE_SYSTEM,
            messages=[{"role": "user", "content": msg}],
        )
        txt = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return _clean_scene(txt) or _clean_scene(raw)
    except Exception as e:
        log.warning("scene description fallback (%s)", e)
        return _clean_scene(raw)


def _visual_prompt(scene: str, product: str, with_product_ref: bool, model_key: str = "") -> str:
    parts: List[str] = ["профессиональная чистая лайфстайл-фотография для Instagram, фотореализм, реалистичная"]
    if scene:
        parts.append(scene)
    if with_product_ref:
        parts.append(
            "на прикреплённом референсе — реальная банка добавки; в кадре ТА ЖЕ банка в руках у "
            f"{_person_phrase(model_key).split(' — ')[0]} с референса лица, "
            "повтори форму, ЦВЕТ СТЕКЛА/крышки и этикетку точно как на референсе, не искажай и "
            "не дорисовывай текст на этикетке; НЕ перекрашивай банку под цвет темы или содержимого "
            "(зелёный продукт ≠ зелёная/прозрачная банка — стекло остаётся как на референсе)"
        )
    elif product and product not in ("", "—"):
        parts.append(f"уместно показать баночку добавки {product}")
    parts.append(_brand_style(model_key))
    parts.append(
        "КАТЕГОРИЧЕСКИ БЕЗ ТЕКСТА В КАДРЕ: никаких букв, цифр, слов, надписей, плашек, подписей, "
        "логотипов, заголовков, субтитров, водяных знаков; no text, no letters, no numbers, no words, "
        "no captions, no labels, no logo, no watermark anywhere; единственный допустимый текст — "
        "этикетка банки и только как на референсе; оставь чистое пространство для наложения текста потом"
    )
    return ". ".join(parts)


# Соотношение сторон по формату: вертикальное видео 9:16, лента 4:5.
_FORMAT_RATIO = {"reels": "9:16", "stories": "9:16", "carousel": "4:5", "photo": "4:5"}


def _apply_logo(image_path) -> None:
    """Накладывает логотип бренда (если загружен в /brand) в правый нижний угол."""
    logo = brand.logo_ref()
    if not logo:
        return
    try:
        from PIL import Image
        base = Image.open(image_path).convert("RGBA")
        lg = Image.open(logo).convert("RGBA")
        w = int(base.width * 0.18)
        h = max(1, int(lg.height * w / lg.width))
        lg = lg.resize((w, h), Image.LANCZOS)
        m = int(base.width * 0.04)
        base.alpha_composite(lg, (base.width - w - m, base.height - h - m))
        base.convert("RGB").save(image_path)
    except Exception as e:
        log.warning("logo overlay failed: %s", e)


def generate_post_assets(post_id: int, ratio: Optional[str] = None, extra: str = "") -> Optional[int]:
    """Генерит визуал с лицом бренда, кладёт в data/media, пишет PostAsset.
    ratio=None → по формату поста; extra → доп. подсказка к промпту (для слайдов карусели).
    Возвращает id ассета."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product, hook, visual_idea = post.product, post.hook, post.visual_idea
        product_id = getattr(post, "product_id", "") or ""
        model_key = getattr(post, "model_key", "") or ""
        ratio = ratio or _FORMAT_RATIO.get(post.format, "4:5")
        ord_ = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image").count()
        # пользовательские референсы поста (банка/сцена) — kind="ref"
        user_refs = [
            config.MEDIA_DIR / a.path.replace("/media/", "", 1)
            for a in s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "ref").all()
        ]
        # последний ЧИСТЫЙ визуал (без наложенного текста) — если он уже есть и это не слайд
        # карусели (extra задан для слайдов не-героя), берём его за референс и просто пересобираем
        # под новый формат/ракурс — как в разведке, вместо случайной генерации с нуля.
        clean = (
            s.query(PostAsset)
            .filter(PostAsset.post_id == post_id, PostAsset.kind == "image", PostAsset.model != "overlay")
            .order_by(PostAsset.ord.desc()).first()
        ) if not extra else None
        clean_ref = (config.MEDIA_DIR / clean.path.replace("/media/", "", 1)) if clean else None
        post.status = "generating"

    prod_ref = None
    if product_id:
        from . import producer as _producer  # та же полка, что у раскадровок (data/product_refs/<id>)
        prod_ref = _producer._product_ref(product_id)
    if not prod_ref:
        prod_ref = brand.product_ref(product)  # фолбэк по имени, если product_id не привязан
    face_ref = brand.model_by_key(model_key)
    existing_user_refs = [p for p in user_refs if p.exists()]

    strict_mode = bool(existing_user_refs and not extra and prod_ref)
    if existing_user_refs and not extra:
        # НАСТОЯЩИЙ внешний референс (скачан по ссылке или загружен вручную) — как в разведке:
        # это реальное фото с чужим человеком/продуктом, композицию/позу берём с него,
        # человека и продукт ПОЛНОСТЬЮ заменяем на наши.
        scene_ref = existing_user_refs[0]
        refs = [scene_ref, face_ref] + ([prod_ref] if prod_ref else [])
        prompt = (
            "ПЕРВОЕ изображение — референсный кадр. Пересоздай его МАКСИМАЛЬНО похоже: та же "
            "композиция, ракурс, свет, стиль, креативный приём, действие и настроение "
            "(если человек пьёт/наливает/держит — то же самое действие, без изменений). "
            "НО: если в кадре есть человек — замени его на НАШУ модель со ВТОРОГО изображения "
            "(то же лицо, та же внешность; поза и действие как в референсе, НЕ копируй внешность "
            "человека из референса). Одежда — ТА ЖЕ, что на референсе (тип, цвет, фасон, посадка), "
            "просто на нашей модели."
            + (" ЛЮБОЙ продукт/упаковку замени на НАШ продукт с ТРЕТЬЕГО изображения — форма банки, "
               "крышка, цвет и этикетка СТРОГО как на референсе продукта, этикетка чёткая, читаемая, "
               "повёрнута к камере, банка целиком в кадре (не обрезать краем). ЗАПРЕЩЕНО придумывать "
               "другую упаковку или оставлять продукт из референса."
               if prod_ref else "")
            + f" Формат кадра: {ratio}. СТРОГО: без текста, букв и надписей на изображении, "
              "кроме этикетки нашего продукта."
        )
    elif clean_ref and clean_ref.exists() and not extra:
        # нет внешнего референса, но есть наш собственный прошлый удачный кадр — слабее, чем
        # реальное фото (наш кадр сам мог быть неидеальным), но лучше, чем рандом с нуля.
        refs = [clean_ref, face_ref] + ([prod_ref] if prod_ref else [])
        prompt = (
            "ПЕРВОЕ изображение — наш предыдущий кадр. Пересоздай его МАКСИМАЛЬНО похоже: та же "
            "композиция, поза, ракурс, действие, свет, стиль. Человек — ТА ЖЕ модель со ВТОРОГО "
            "изображения (то же лицо, не меняй внешность)."
            + (" Продукт в руках — банка СТРОГО как на ТРЕТЬЕМ изображении (это настоящий продукт "
               "POWERELIX, самый достоверный референс из всех): форма, крышка, цвет и ЭТИКЕТКА "
               "СТРОГО как на референсе, этикетка чёткая, читаемая, с текстом POWERELIX и названием "
               "продукта, повёрнута к камере, банка целиком в кадре. ЗАПРЕЩЕНО придумывать другой "
               "бренд, другой текст на этикетке или другую упаковку — если сомневаешься, ориентируйся "
               "на ТРЕТЬЕ изображение, а не на первое."
               if prod_ref else "")
            + f" НОВОЕ соотношение сторон кадра: {ratio} — адаптируй композицию под этот формат "
              "(для вертикали 9:16 удлини сцену вверх/вниз, а не просто обрежь по бокам). "
              "СТРОГО: без текста, букв и надписей на изображении, кроме этикетки продукта."
        )
    else:
        # первая генерация без референсов или слайд карусели — сцена из идеи/хука
        refs = [face_ref] + existing_user_refs + ([prod_ref] if prod_ref else [])
        scene = _scene_description(visual_idea, hook, product)
        prompt = _visual_prompt(scene, product, with_product_ref=bool(prod_ref) or bool(existing_user_refs),
                                model_key=model_key)
        if extra:
            prompt += ". " + extra

    try:
        from . import producer
        img = producer.gen_product_image(prompt, refs, aspect=ratio, bottle=prod_ref, strict=strict_mode)
        dest = config.MEDIA_DIR / f"post_{post_id}_{ord_}.png"
        dest.write_bytes(img)
        _apply_logo(dest)
    except Exception:
        with session_scope() as s:  # вернуть статус, не оставлять в «generating»
            p = s.get(Post, post_id)
            if p and p.status == "generating":
                p.status = "draft"
        raise

    with session_scope() as s:
        asset = PostAsset(post_id=post_id, kind="image", path=f"/media/{dest.name}",
                          model="img-chain", prompt=prompt, ord=ord_)
        s.add(asset)
        p = s.get(Post, post_id)
        if p and p.status == "generating":
            p.status = "review"
        s.flush()
        asset_id = asset.id

    if not extra:  # не для слайдов карусели (extra) — там на разных слайдах нужен разный текст
        try:
            apply_text_overlay(post_id, source_asset_id=asset_id)
        except Exception as e:
            log.warning("auto-overlay после генерации visual не удался: %s", e)
    return asset_id


_SLIDE_HINTS = [
    "",  # слайд 1 — герой: лицо бренда + продукт
    "крупный план продукта на чистом светлом столе, мягкий студийный свет, минимализм",
    "лайфстайл: модель использует продукт в повседневной обстановке, естественно",
    "макро-детали продукта и текстуры, свежесть, аппетитный кадр",
    "продукт рядом с натуральными ингредиентами (фрукты, зелень), чистая эстетика",
]


def generate_carousel(post_id: int, slides: int = 4) -> int:
    """Генерит N слайдов карусели (герой + контент-кадры в стиле бренда). Каждый слайд
    добавляется как PostAsset (ord по порядку). Возвращает кол-во созданных слайдов."""
    slides = max(2, min(slides, 8))
    made = 0
    for i in range(slides):
        hint = _SLIDE_HINTS[i] if i < len(_SLIDE_HINTS) else "ещё один кадр в фирменном стиле бренда"
        try:
            if generate_post_assets(post_id, extra=hint):
                made += 1
        except Exception as e:
            log.warning("carousel slide %d failed: %s", i, e)
    return made


# ── Текст (если у черновика нет подписи — напр. пришёл из идеи) ──

class TextOut(BaseModel):
    caption: str = Field(description="Готовая подпись к посту на русском, с эмодзи и абзацами, без хэштегов в конце")
    hashtags: List[str] = Field(description="РОВНО 5 самых релевантных хэштегов на русском без "
                                "решёток — Instagram сейчас режет охват по большему числу тегов, "
                                "меньше и точнее работает лучше, чем длинный список")
    cta: str = Field(description="Короткий призыв к действию")


_TEXT_SYSTEM = """Ты — SMM-копирайтер бренда БАД POWERELIX (РФ). По хуку/идее напиши подпись поста.
ЖЁСТКО: БАД — не лекарство; нельзя «лечит/вылечивает/диагностирует/гарантирует результат»;
формулировки мягкие («поддерживает», «способствует», «помогает восполнить»); для продуктовых
постов добавь короткую плашку «БАД. Не является лекарственным средством». Пиши живо, на «ты».
НЕ пиши СПОСОБ ПРИМЕНЕНИЯ и дозировку: сколько капсул, когда/как принимать, длительность курса,
сколько штук в упаковке — этого в тексте поста быть НЕ должно (фокус на пользе, эмоции, результате).
Верни строго структуру по схеме."""


def set_post_product(post_id: int, product_id: str) -> None:
    """Привязывает пост к конкретному товару каталога (id + каноничное название)."""
    p = products.product_by_id(product_id)
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return
        post.product_id = str(product_id) if p else ""
        if p:
            post.product = p.get("full_name", p.get("name", ""))


def set_post_blogger(post_id: int, blogger_id: str) -> None:
    """Привязывает пост к блогеру (контент для него) или к своему аккаунту (пусто)."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return
        post.blogger_id = int(blogger_id) if blogger_id else None


def generate_post_text(post_id: int) -> Optional[int]:
    """Догенерирует подпись/хэштеги/CTA через Claude под конкретный товар (если привязан),
    с вставкой артикула/ссылки WB. Возвращает post_id."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        pid = post.product_id
        brief = (
            f"Рубрика: {post.rubric or '—'}\nФормат: {post.format}\n"
            f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}"
        )
    if pid:
        ctx = products.one_context(pid)
        link = catalog.link_line(pid)
        if ctx:
            brief += "\n\n" + ctx
        if link:
            brief += (
                f"\n\nГДЕ КУПИТЬ ({link}). В конце подписи добавь призыв с этим артикулом/ссылкой "
                "(в Instagram ссылка некликабельна — пиши «ищи на Wildberries, артикул XXXX» "
                "или «ссылка в шапке профиля»)."
            )
    else:
        brief = f"Продукт: {post.product or '—'}\n" + brief
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=2000, system=_TEXT_SYSTEM,
        messages=[{"role": "user", "content": f"Напиши текст поста под этот товар:\n\n{brief}"}],
        output_format=TextOut,
    )
    out = resp.parsed_output
    caption = out.caption
    # Гарантируем артикул/ссылку WB В САМОЙ подписи (Claude иногда кладёт в CTA).
    if pid:
        lk = catalog.get_link(pid)
        if lk and lk.get("nmid") and lk["nmid"] not in caption:
            buy = f"\n\n🛒 На Wildberries — артикул {lk['nmid']}"
            if lk.get("wb_url"):
                buy += f"\n{lk['wb_url']}"
            caption = caption.rstrip() + buy
    with session_scope() as s:
        post = s.get(Post, post_id)
        post.caption = caption
        post.hashtags = out.hashtags
        post.cta = out.cta
        return post_id


# ── Reels: сценарий + раскадровка + видео ──

class ReelsScene(BaseModel):
    visual: str = Field(description="что в кадре — раскадровка сцены")
    onscreen: str = Field(description="текст на экране для этой сцены (рус.)")
    voiceover: str = Field(description="закадровый текст/реплика (рус.)")


class ReelsScript(BaseModel):
    hook: str = Field(description="хук первых 0-3 секунд")
    scenes: List[ReelsScene] = Field(description="3-5 сцен — раскадровка по порядку")
    cta: str = Field(description="призыв в конце (с упоминанием WB-артикула, если есть)")
    duration_sec: int = Field(description="рекомендованная длина, сек (15-45)")
    audio: str = Field(description="идея звука/музыки/тренда")


_REELS_SYSTEM = """Ты — сценарист коротких вертикальных видео (Reels) для бренда БАД POWERELIX,
аудитория РУССКОЯЗЫЧНАЯ. По идее поста напиши СЦЕНАРИЙ Reels: хук 0-3 сек, 3-4 сцены
(раскадровка: что в кадре + текст на экране + закадровый текст), CTA, длину, идею звука.
ВАЖНО — динамика Reels: закадровый текст (voiceover) КАЖДОЙ сцены ОЧЕНЬ короткий — ОДНА
фраза, максимум 10-12 слов (это ~4-6 сек речи); хук и cta тоже короткие. Весь ролик 20-35 сек.
Юр-правила рекламы БАД РФ: без «лечит/диагностирует/гарантирует», мягкие формулировки,
в конце дисклеймер «не является лекарственным средством». Пиши живо, на «ты», по-русски.
Верни строго структуру по схеме."""


def generate_reels_script(post_id: int) -> Optional[int]:
    """Claude пишет сценарий+раскадровку Reels по идее поста. Сохраняет в post.reels_script."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        brief = f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}\nРубрика: {post.rubric or '—'}"
        pid = post.product_id
    if pid:
        ctx = products.one_context(pid)
        if ctx:
            brief += "\n\n" + ctx
        link = catalog.link_line(pid)
        if link:
            brief += f"\n\nГде купить (упомяни в CTA): {link}"
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=3000, system=_REELS_SYSTEM,
        messages=[{"role": "user", "content": f"Сценарий Reels по идее:\n\n{brief}"}],
        output_format=ReelsScript,
    )
    with session_scope() as s:
        post = s.get(Post, post_id)
        post.reels_script = resp.parsed_output.model_dump(mode="json")
        return post_id


def generate_reels_video(post_id: int) -> Optional[int]:
    """hero-кадр 9:16 с лицом бренда → image→video (Replicate). PostAsset kind=video."""
    if not config.REPLICATE_API_TOKEN:
        raise RuntimeError("Не задан REPLICATE_API_TOKEN (нужен для видео)")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        product, hook, visual_idea = post.product, post.hook, post.visual_idea
        product_id = getattr(post, "product_id", "") or ""
        model_key = getattr(post, "model_key", "") or ""
        n = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "video").count()
        post.status = "generating"
    refs = [brand.model_by_key(model_key)]
    pr = None
    if product_id:
        from . import producer as _producer
        pr = _producer._product_ref(product_id)
    pr = pr or brand.product_ref(product)
    if pr:
        refs.append(pr)
    scene = _scene_description(visual_idea, hook, product)
    prompt = _visual_prompt(scene, product, with_product_ref=bool(pr), model_key=model_key)
    try:
        hero = scenes.generate_branded(prompt, refs=refs, ratio="9:16", out_name=f"reelhero_{post_id}_{n}.png")
        hero_media = config.MEDIA_DIR / f"reelhero_{post_id}_{n}.png"
        shutil.copy(hero, hero_media)  # в /media → Replicate скачает hero по URL (короткий POST)
        video = scenes.generate_video(hero_media, prompt="natural cinematic motion, soft lighting",
                                      duration=5, aspect_ratio="9:16", out_name=f"reel_{post_id}_{n}.mp4")
        dest = config.MEDIA_DIR / f"reel_{post_id}_{n}.mp4"
        shutil.copy(video, dest)
    except Exception:
        with session_scope() as s:
            p = s.get(Post, post_id)
            if p and p.status == "generating":
                p.status = "review"
        raise
    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="video", path=f"/media/{dest.name}", model="grok-video",
                      prompt=prompt, ord=n)
        s.add(a)
        p = s.get(Post, post_id)
        if p and p.status == "generating":
            p.status = "review"
        s.flush()
        return a.id


# ── Текст-оверлей: чёткие плашки поверх чистой картинки (Pillow) ──

class OverlayText(BaseModel):
    headline: str = Field(description="цепкий заголовок-крючок для обложки, 2-6 слов, БЕЗ кавычек и точки в конце")
    subtitle: str = Field(description="одна короткая строка-подзаголовок (выгода), до 6-7 слов, без точки")
    tag: str = Field(description="короткий тег-призыв капсом, напр 'СОХРАНИ  →' или 'ЛИСТАЙ  →'")
    disclaimer: str = Field(description="для продуктовых постов 'БАД. Не является лекарственным средством', иначе пустая строка")


_OVERLAY_SYSTEM = """Ты — дизайнер-копирайтер обложек Instagram для бренда БАД POWERELIX (РФ).
Придумай текст для ОБЛОЖКИ поста: цепкий ЗАГОЛОВОК-крючок (крупный, 2-6 слов) + одна строка
ПОДЗАГОЛОВКА (короткая выгода) + короткий ТЕГ-призыв ('СОХРАНИ  →' или 'ЛИСТАЙ  →').
Коротко, на русском, на «ты», без воды и без кавычек. БАД-правила РФ: без «лечит/диагностирует/
гарантирует», мягкие формулировки. Для продуктовых постов дисклеймер заполни, иначе пустым.
Верни строго по схеме."""


def suggest_overlay_text(post_id: int) -> dict:
    """Claude придумывает текст обложки (заголовок + подзаголовок + тег + дисклеймер)."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("Не задан ANTHROPIC_API_KEY в .env")
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"headline": "", "subtitle": "", "tag": overlay.DEFAULT_TAG, "disclaimer": ""}
        is_carousel = post.format == "carousel"
        brief = (
            f"Хук: {post.hook or '—'}\nИдея визуала: {post.visual_idea or '—'}\n"
            f"Рубрика: {post.rubric or '—'}\nПродукт: {post.product or '—'}"
        )
        pid = post.product_id
    if pid:
        ctx = products.one_context(pid)
        if ctx:
            brief += "\n\n" + ctx
    if not is_carousel:
        # одиночная картинка (пост/Reels) — как раньше: ТОЛЬКО жирный заголовок-крючок.
        # Ни подзаголовка, ни тега, ни дисклеймера на самой картинке — дисклеймер
        # и так есть в тексте подписи поста, дублировать на фото не нужно.
        brief += ("\n\nЭто ОДИНОЧНАЯ картинка (не карусель, публикуется как Reels/фото). "
                  "Нужен ТОЛЬКО заголовок-крючок. Подзаголовок, тег и дисклеймер НЕ нужны — "
                  "оставь их пустыми строками.")
    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=config.CLAUDE_MODEL, max_tokens=600, system=_OVERLAY_SYSTEM,
        messages=[{"role": "user", "content": f"Текст обложки поста:\n\n{brief}"}],
        output_format=OverlayText,
    )
    o = resp.parsed_output
    if not is_carousel:
        return {"headline": o.headline, "subtitle": "", "tag": "", "disclaimer": ""}
    return {"headline": o.headline, "subtitle": o.subtitle,
            "tag": o.tag or overlay.DEFAULT_TAG, "disclaimer": o.disclaimer}


def apply_text_overlay(post_id: int, source_asset_id: Optional[int] = None,
                       headline: Optional[str] = None, subtitle: Optional[str] = None,
                       tag: Optional[str] = None, disclaimer: Optional[str] = None) -> Optional[int]:
    """Накладывает фирменную обложку-текст на чистую картинку (источник или последний визуал)
    → новый ассет (model='overlay'). Если текст не передан — придумывает через Claude."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return None
        img_ratio = _FORMAT_RATIO.get(post.format, "4:5")
        q = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image")
        if source_asset_id:
            src = s.get(PostAsset, int(source_asset_id))
        else:  # последний «чистый» визуал (не оверлей)
            src = q.filter(PostAsset.model != "overlay").order_by(PostAsset.ord.desc()).first()
        if not src:
            raise RuntimeError("Нет картинки для наложения — сначала сгенерируй визуал")
        src_path = config.MEDIA_DIR / src.path.replace("/media/", "", 1)
        ord_ = q.count()
    if headline is None and subtitle is None:
        txt = suggest_overlay_text(post_id)
        headline, subtitle, tag, disclaimer = txt["headline"], txt["subtitle"], txt["tag"], txt["disclaimer"]
    dest = config.MEDIA_DIR / f"post_{post_id}_txt{ord_}.png"
    # tag=None (никто не задавал) -> дефолт; tag="" (осознанно пусто, напр. для
    # одиночной картинки без "ЛИСТАЙ/СОХРАНИ") -> оставляем пустым, не подменяем.
    overlay.render_cover(src_path, headline=headline or "", subtitle=subtitle or "",
                         tag=(tag if tag is not None else overlay.DEFAULT_TAG),
                         disclaimer=disclaimer or "",
                         out_path=str(dest), ratio=img_ratio)
    with session_scope() as s:
        a = PostAsset(post_id=post_id, kind="image", path=f"/media/{dest.name}", model="overlay",
                      prompt=((headline or "") + " — " + (subtitle or ""))[:300], ord=ord_)
        s.add(a)
        s.flush()
        return a.id


# ── Аппрув + БАД-комплаенс (Фаза 5) ──

def check_compliance(post_id: int) -> Optional[dict]:
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None
        return compliance.check(p.hook, p.caption, p.visual_idea, p.cta, p.product)


def approve_post(post_id: int, override: bool = False) -> dict:
    """Проверяет комплаенс и одобряет. При нарушениях без override — блок."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return {"ok": False, "error": "пост не найден"}
        chk = compliance.check(post.hook, post.caption, post.visual_idea, post.cta, post.product)
        post.disclaimer_ok = chk["disclaimer_ok"]
        post.compliance_notes = compliance.summary(chk)
        if chk["blocked"] and not override:
            return {"ok": False, "blocked": True, **chk}
        post.status = "approved"
        if chk["blocked"] and override:
            post.compliance_notes = "ОВЕРРАЙД: " + post.compliance_notes
        return {"ok": True, **chk}


def add_disclaimer(post_id: int) -> bool:
    """Дописывает стандартный дисклеймер БАД в конец подписи (если его нет)."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return False
        if "не является лекарственным средством" not in (post.caption or "").lower():
            post.caption = ((post.caption or "").rstrip() + "\n\n" + compliance.DISCLAIMER).strip()
        return True


def back_to_review(post_id: int) -> bool:
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return False
        post.status = "review"
        return True


# ── для UI ──

def list_posts() -> List[dict]:
    with session_scope() as s:
        posts = s.query(Post).order_by(Post.id.desc()).all()
        out = []
        for p in posts:
            first = (
                s.query(PostAsset).filter(PostAsset.post_id == p.id, PostAsset.kind == "image")
                .order_by(PostAsset.ord).first()
            )
            thumb, is_video = (first.path, False) if first else ("", False)
            if not thumb:  # Reels без картинки-превью — берём кадр видео (у видео своя обложка в браузере)
                vid = (
                    s.query(PostAsset).filter(PostAsset.post_id == p.id, PostAsset.kind == "video")
                    .order_by(PostAsset.ord.desc()).first()
                )
                if vid:
                    thumb, is_video = vid.path, True
            out.append({
                "id": p.id, "rubric": p.rubric, "product": p.product, "format": p.format,
                "hook": p.hook, "status": p.status, "thumb": thumb, "thumb_video": is_video,
            })
        return out


def delete_post(post_id: int) -> bool:
    """Удаляет пост со всеми ассетами (файлы на диске + записи в БД)."""
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return False
        assets = s.query(PostAsset).filter(PostAsset.post_id == post_id).all()
        for a in assets:
            fp = config.MEDIA_DIR / a.path.replace("/media/", "", 1)
            fp.unlink(missing_ok=True)
            s.delete(a)
        s.delete(p)
        return True


def get_post(post_id: int) -> Optional[dict]:
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None
        assets = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id)
            .order_by(PostAsset.ord).all()
        )
        images = [a for a in assets if a.kind == "image"]
        # какая картинка РЕАЛЬНО уйдёт в публикацию сейчас (та же логика, что
        # get_publish_assets) — чтобы бейдж «выбрано» в UI не расходился с фактом
        effective_selected_id = None
        if p.format != "carousel" and images:
            sel_id = getattr(p, "selected_asset_id", None)
            if sel_id and any(a.id == sel_id for a in images):
                effective_selected_id = sel_id
            else:
                overlays = [a for a in images if a.model == "overlay"]
                effective_selected_id = (overlays[-1] if overlays else images[-1]).id
        return {
            "id": p.id, "rubric": p.rubric, "product": p.product, "product_id": p.product_id,
            "format": p.format,
            "hook": p.hook, "caption": p.caption, "hashtags": p.hashtags or [],
            "visual_idea": p.visual_idea, "cta": p.cta, "status": p.status,
            "scheduled_at": p.scheduled_at, "ig_media_id": p.ig_media_id,
            "permalink": p.permalink, "error": p.error, "reels_script": p.reels_script,
            "blogger_id": p.blogger_id, "model_key": getattr(p, "model_key", "") or "",
            "assets": [{"id": a.id, "path": a.path, "model": a.model} for a in images],
            "refs": [{"id": a.id, "path": a.path} for a in assets if a.kind == "ref"],
            "videos": [{"id": a.id, "path": a.path} for a in assets if a.kind == "video"],
            "selected_asset_id": getattr(p, "selected_asset_id", None),
            "effective_selected_id": effective_selected_id,
        }


def select_post_image(post_id: int, asset_id: int) -> bool:
    """Помечает конкретную картинку как «ту самую» для публикации (photo/reels —
    когда сгенерировано несколько вариантов, иначе непонятно, какую выкладывать)."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        asset = s.get(PostAsset, asset_id)
        if not post or not asset or asset.post_id != post_id or asset.kind != "image":
            return False
        post.selected_asset_id = asset_id
        return True


def get_publish_assets(post_id: int) -> List[PostAsset]:
    """Единый источник правды для publisher/vk_crosspost/tg_crosspost/manual-pack:
    какие именно картинки идут в публикацию.
    - carousel: ВСЕ картинки по порядку (как и раньше).
    - photo/reels: РОВНО ОДНА — selected_asset_id, если выбрана явно; иначе
      последняя обложка-с-текстом (model='overlay'); иначе последняя чистая.
      Раньше тут брались ВСЕ оставшиеся варианты (включая старые перегенерации),
      и IG получал их как нежданную карусель из мусора — теперь только одна."""
    with session_scope() as s:
        post = s.get(Post, post_id)
        if not post:
            return []
        assets = (
            s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "image")
            .order_by(PostAsset.ord).all()
        )
        if not assets:
            return []
        if post.format == "carousel":
            return assets
        sel_id = getattr(post, "selected_asset_id", None)
        if sel_id:
            picked = next((a for a in assets if a.id == sel_id), None)
            if picked:
                return [picked]
        overlays = [a for a in assets if a.model == "overlay"]
        return [overlays[-1]] if overlays else [assets[-1]]


def add_post_ref(post_id: int, file_bytes: bytes, filename: str) -> Optional[int]:
    """Загружает референс под пост (банка/сцена) — будет добавлен в генерацию."""
    import hashlib
    from pathlib import Path
    ext = Path(filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("формат не поддерживается (PNG/JPG/WEBP)")
    if not file_bytes:
        raise ValueError("пустой файл")
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"ref_{post_id}_{hashlib.md5(file_bytes).hexdigest()[:8]}{ext}"
    (config.MEDIA_DIR / name).write_bytes(file_bytes)
    with session_scope() as s:
        n = s.query(PostAsset).filter(PostAsset.post_id == post_id, PostAsset.kind == "ref").count()
        a = PostAsset(post_id=post_id, kind="ref", path=f"/media/{name}", model="upload", ord=n)
        s.add(a)
        s.flush()
        return a.id


def add_post_ref_by_url(post_id: int, url: str) -> Optional[int]:
    """Тот же механизм, что в разведке: скачивает НАСТОЯЩЕЕ фото по ссылке
    (Pinterest пин / IG-пост) и сохраняет как референс поста kind='ref'."""
    from . import recon
    reel_id = recon.add_reel_by_url(url)
    if not reel_id:
        raise ValueError("не удалось разобрать ссылку — проверь URL Pinterest/IG")
    frames = sorted((config.MEDIA_DIR / "frames" / str(reel_id)).glob("f*.jpg"))
    if not frames:
        raise ValueError("не удалось скачать изображение по ссылке")
    return add_post_ref(post_id, frames[0].read_bytes(), frames[0].name)


def delete_post_asset(asset_id: int) -> None:
    with session_scope() as s:
        a = s.get(PostAsset, asset_id)
        if not a:
            return
        try:
            (config.MEDIA_DIR / a.path.replace("/media/", "", 1)).unlink()
        except OSError:
            pass
        s.delete(a)
