"""Генератор контент-плана для Instagram POWERELIX через Claude."""
from __future__ import annotations

from enum import Enum

import anthropic
from pydantic import BaseModel, Field

from . import config
from .products import products_context


class PostFormat(str, Enum):
    photo = "Пост (фото)"
    carousel = "Карусель"
    reels = "Reels"
    stories = "Stories"


class Post(BaseModel):
    date: str = Field(description="Дата публикации в формате YYYY-MM-DD")
    weekday: str = Field(description="День недели по-русски, напр. 'понедельник'")
    time: str = Field(default="", description="Время публикации HH:MM по МСК (слот дня)")
    post_type: str = Field(description="'educational' — полезный (миф/признаки/лайфхак/рутина/сравнение/разбор) или 'product' — продуктовый/продающий")
    format: PostFormat
    rubric: str = Field(description="Рубрика/тема, напр. 'Мифы', 'Признаки дефицита', 'Лайфхак', 'Рутина', 'Продуктовый'")
    product: str = Field(description="Какой продукт POWERELIX в фокусе (мостик в финале для полезных постов), или '—' если пост общий")
    hook: str = Field(description="Цепляющий заголовок / первая строка поста (для Reels — текст на обложке)")
    caption: str = Field(description="Готовый текст подписи к посту на русском, с эмодзи и абзацами, БЕЗ хэштегов в конце")
    hashtags: list[str] = Field(description="ровно 5 самых релевантных хэштегов на русском без решёток")
    visual_idea: str = Field(description="Идея визуала: что в кадре, раскадровка для Reels/каруселей, акцентный цвет продукта")
    cta: str = Field(description="Призыв к действию")


class ContentPlan(BaseModel):
    period: str = Field(description="Период плана, напр. 'июнь 2026, недели 1-2'")
    strategy_summary: str = Field(description="Краткое объяснение стратегии плана (2-4 предложения)")
    rubrics_legend: list[str] = Field(description="Список используемых рубрик с короткой расшифровкой")
    posts: list[Post]


SYSTEM = """Ты — опытный SMM-стратег и копирайтер для российского Instagram, специализация — бренды БАДов и нутрицевтики.

Твоя задача — составить продающий, но не «втюхивающий» контент-план для молодого аккаунта (мало подписчиков), который нужно вырастить. Делай упор на пользу, доверие и вовлечение, а не на прямые продажи в каждом посте.

ЖЁСТКИЕ ЮРИДИЧЕСКИЕ ПРАВИЛА (РФ, реклама БАД):
- БАД — НЕ лекарство. Запрещено заявлять, что продукт лечит, предотвращает или диагностирует заболевания.
- Не давать гарантий результата и не создавать впечатление, что без БАД человек заболеет.
- Не использовать образы врачей в белых халатах как рекламу; формулировки о пользе — мягкие («поддерживает», «способствует», «помогает восполнить»).
- Где уместно (особенно в продуктовых постах) добавляй короткую плашку-дисклеймер: «БАД. НЕ является лекарственным средством. Есть противопоказания, проконсультируйтесь со специалистом.»
- Не упоминать конкретные болезни как то, что продукт «вылечит».

ПРИНЦИПЫ КОНТЕНТА:
- РИТМ: полезные (образовательные) посты — основа, продуктовые — вкрапления. Соблюдай заданное соотношение полезное:продуктовое и не ставь два продуктовых подряд.
- ПОЛЕЗНЫЕ посты (post_type='educational') бери ИЗ БАНКА ТЕМ ниже — не выдумывай общее. Тип поста = МИФ (гонит комменты), ПРИЗНАКИ ДЕФИЦИТА (гонит сохранения), ЛАЙФХАК, РУТИНА/ЧЕКЛИСТ, СРАВНЕНИЕ, РАЗБОР. У каждого полезного поста в финале мягкий мостик к товару из его темы (+ упоминание, что товар на WB).
- ПРОДУКТОВЫЕ посты (post_type='product') — прямая подача товара: hero-кадр, польза, оффер.
- Чередуй форматы: Reels (охваты), карусели (сохранения, лучший для «признаков»/чеклистов), фото-посты.
- Учитывай акцентный цвет каждого продукта для визуальной узнаваемости с упаковкой.
- Пиши живо, на «ты» к аудитории, с эмодзи в меру, под российскую аудиторию.
- Reels/карусели: давай раскадровку (сцена/слайд 1, 2…) в visual_idea.

Верни СТРОГО структуру по заданной схеме."""


def _load_bank() -> str:
    from pathlib import Path
    f = Path(__file__).resolve().parent / "data" / "content_bank.md"
    try:
        return f.read_text(encoding="utf-8")
    except Exception:
        return ""


def build_user_prompt(n_posts: int, start_date: str, cadence: str, focus: str | None,
                      rhythm: str = "2:1", slots: str = "") -> str:
    parts = [
        products_context(),
        "",
        "=== БАНК ПОЛЕЗНЫХ ТЕМ (источник для educational-постов) ===",
        _load_bank(),
        "",
        "ЗАДАНИЕ:",
        f"- Составь контент-план на {n_posts} публикаций.",
        f"- Старт: {start_date}. Частота: {cadence}.",
        f"- РИТМ полезное:продуктовое = {rhythm} (напр. 2:1 = на 2 полезных 1 продуктовый). Проставь post_type у каждого поста.",
        "- Полезные посты бери ИЗ БАНКА ТЕМ выше, покрывай РАЗНЫЕ темы здоровья и разные типы (миф/признаки/лайфхак/рутина).",
        "- Проставь конкретные даты и дни недели начиная со старта с учётом частоты.",
    ]
    if slots:
        parts.append(f"- Время публикаций (слоты дня) распределяй по: {slots}.")
    parts += [
        "- Покрой разные продукты линейки (не зацикливайся на одном).",
        "- НЕ ставь два продуктовых поста подряд.",
    ]
    if focus:
        parts.append(f"- Особый акцент: {focus}")
    return "\n".join(parts)


def generate(
    n_posts: int = 15,
    start_date: str = "2026-06-09",
    cadence: str = "5 публикаций в неделю (пн-пт)",
    focus: str | None = None,
    rhythm: str = "2:1",
    slots: str = "",
) -> ContentPlan:
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit(
            "Не задан ANTHROPIC_API_KEY в .env. Вставь ключ Anthropic или ProxyAPI и повтори."
        )
    client = anthropic.Anthropic()  # ключ/base_url берутся из окружения (.env подгружен)
    response = client.messages.parse(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[
            {"role": "user", "content": build_user_prompt(n_posts, start_date, cadence, focus, rhythm, slots)}
        ],
        output_format=ContentPlan,
    )
    return response.parsed_output
