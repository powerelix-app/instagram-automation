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
    format: PostFormat
    rubric: str = Field(description="Рубрика, напр. 'Образовательный', 'Продуктовый', 'Вовлекающий', 'Lifestyle', 'Отзыв/UGC'")
    product: str = Field(description="Какой продукт POWERELIX в фокусе, или '—' если пост общий")
    hook: str = Field(description="Цепляющий заголовок / первая строка поста (для Reels — текст на обложке)")
    caption: str = Field(description="Готовый текст подписи к посту на русском, с эмодзи и абзацами, БЕЗ хэштегов в конце")
    hashtags: list[str] = Field(description="8-15 релевантных хэштегов на русском без решёток в начале строки описания")
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
- Соблюдай баланс рубрик (правило ~70/20/10: польза/вовлечение — продукт — продажа).
- Чередуй форматы: Reels (охваты), карусели (сохранения), фото-посты, Stories-идеи.
- Учитывай акцентный цвет каждого продукта для визуальной узнаваемости с упаковкой.
- Пиши живо, на «ты» к аудитории, с эмодзи в меру, под российскую аудиторию.
- Хэштеги — смесь брендовых, нишевых и среднечастотных на русском.
- Reels: давай раскадровку (сцена 1, сцена 2…) и идею звука/текста на экране.

Верни СТРОГО структуру по заданной схеме."""


def build_user_prompt(n_posts: int, start_date: str, cadence: str, focus: str | None) -> str:
    parts = [
        products_context(),
        "",
        "ЗАДАНИЕ:",
        f"- Составь контент-план на {n_posts} публикаций.",
        f"- Старт: {start_date}. Частота: {cadence}.",
        "- Проставь конкретные даты и дни недели начиная со старта с учётом частоты.",
        "- Покрой разные продукты линейки (не зацикливайся на одном).",
        "- Соблюди баланс рубрик и чередование форматов.",
    ]
    if focus:
        parts.append(f"- Особый акцент: {focus}")
    return "\n".join(parts)


def generate(
    n_posts: int = 15,
    start_date: str = "2026-06-09",
    cadence: str = "5 публикаций в неделю (пн-пт)",
    focus: str | None = None,
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
            {"role": "user", "content": build_user_prompt(n_posts, start_date, cadence, focus)}
        ],
        output_format=ContentPlan,
    )
    return response.parsed_output
