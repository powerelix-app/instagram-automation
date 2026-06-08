# Instagram Automation — POWERELIX

Автоматизация Instagram бренда POWERELIX через **официальный Instagram API** (Instagram Login).
Первый модуль — ИИ-генератор контент-плана под линейку БАДов (через Claude).

## Установка

```bash
cd ~/projects/instagram-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Настройка

Файл `.env` уже содержит доступы к Instagram. Нужно добавить только ключ Claude:

```
ANTHROPIC_API_KEY=...        # console.anthropic.com или ProxyAPI
# ANTHROPIC_BASE_URL=...      # раскомментировать, если ProxyAPI
CLAUDE_MODEL=claude-opus-4-8  # или claude-haiku-4-5 для экономии
```

## Команды

```bash
# Проверить связь с Instagram (профиль аккаунта)
python check_connection.py

# Сгенерировать контент-план
python generate_plan.py                         # 15 постов, пн-пт
python generate_plan.py --posts 10 --start 2026-06-15
python generate_plan.py --focus "запуск Омега-3"
python generate_plan.py --model claude-haiku-4-5
```

Результат сохраняется в `output/content_plan_<дата>.json` и `.md`.

## Что внутри

- `ig_automation/config.py` — чтение `.env`
- `ig_automation/products.py` — линейка POWERELIX (из `data/brand_powerelix.json`)
- `ig_automation/content_plan.py` — генератор плана (Claude, structured output)
- `ig_automation/instagram.py` — обёртка Instagram API: профиль, медиа, продление токена
- `generate_plan.py` / `check_connection.py` — CLI

## Токен Instagram

Долгоживущий токен живёт 60 дней. Продление (когда токену >24ч):

```python
from ig_automation.instagram import refresh_token
print(refresh_token())   # положить новый access_token в .env
```

Если токен протух — заново пройти OAuth (см. память проекта / PLANS.md).

## Дорожная карта

См. `PLANS.md`.
