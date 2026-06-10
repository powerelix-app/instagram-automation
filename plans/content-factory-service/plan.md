# Plan — Контент-завод (КАК)

> Парный файл к `spec.md`. Архитектура, схема БД, контракты, фазы, edge cases.

## Стек
- Python 3, **FastAPI + Uvicorn**, **SQLite + SQLAlchemy 2.0** (`Mapped`/`mapped_column`), **APScheduler** (BackgroundScheduler), **Jinja2 + HTMX + Tailwind (CDN)** — зеркало стека wb-promotion, чтобы переиспользовать паттерны и не плодить новый стек.
- Конфиг/секреты — `.env` через `config.py` (уже есть).
- Хранение медиа: локально в `data/media/` + (позже) зеркало в Google Drive через rclone (как у биддера).

## Карта переиспользования (что берём из текущего репо)
| Берём | Файл | Как используем |
|---|---|---|
| Генератор контент-плана | `ig_automation/content_plan.py::generate()` | Стадия «Контент-план», оборачиваем в сервис, результат пишем в БД |
| Мульти-модель генерации картинок | `ig_automation/scenes.py::generate_scene()` | Стадия «Генерация», визуал с лицом бренда (Grok edits) |
| Обёртка Apify | `ig_automation/apify.py` | Расширяем: добавляем актор поиска Reels по теме (сейчас только профили) |
| Graph API (read) | `ig_automation/instagram.py` | Расширяем: media container + publish + insights + auto-refresh токена |
| Каталог продуктов | `ig_automation/products.py` + `data/*.json` | Контекст для генерации, выбор SKU |
| Бренд-оверлеи | `brand_overlay.py`, `post_template.py` | Опц. наложения (не критично для MVP) |
| Конфиг/.env | `ig_automation/config.py` | Как есть |

**НЕ переиспользуем как каркас:** `build_post01.py` (одноразовый хардкод), `content-factory` репо (другой стек + запрет IG).

**Важно про скиллы:** `concept-analyzer`/`youtube-monitoring`/`instagram-monitoring` — интерактивные Claude-скиллы, из работающего сервиса их вызвать нельзя. Логику разбора хука в сервисе реализуем самостоятельным Python-промптом к Claude (по образцу `content_plan.py`). Скиллы остаются для ручного ad-hoc разбора.

## Архитектура (модули)
```
ig_automation/
  app.py            # FastAPI: create_app, lifespan(scheduler), middleware
  db/
    base.py         # engine, session, Base
    models.py       # таблицы (см. ниже)
  services/
    recon.py        # разведка: apify search-reels → trend_reels; hook-analysis (Claude)
    planner.py      # обёртка content_plan.generate → БД
    generator.py    # per-post: scenes.generate_scene + Claude-текст → post_assets
    compliance.py   # БАД-линт стоп-слов + проверка дисклеймера
    publisher.py    # IG container→publish, идемпотентность, статусы
    insights.py     # тянет метрики опубликованных
    tokens.py       # auto-refresh IG-токена
  scheduler.py      # APScheduler: publish_due, refresh_token, (опц.) recon_cron, insights_pull
  api/
    pages.py        # HTMX-страницы: /recon /plan /ideas /posts /post/{id} /analytics
  web/templates/    # base.html (+ nav), recon.html, plan.html, ideas.html, posts.html, post_detail.html, analytics.html
  web/static/
```

## Схема БД (SQLite)
- **trend_reels**: id, source_actor, url, username, play_count, likes, comments, caption, hashtags(json), video_url, local_media_path, music_info, transcript, topic, scraped_at.
- **hook_analyses**: id, trend_reel_id(fk), hook, retention_device, trigger, structure, why_viral, adapted_idea, created_at.
- **ideas**: id, text, hook, source(enum: trend/plan/manual), trend_reel_id(nullable fk), rubric, product, status(new/in_work/used), created_at.
- **content_plans**: id, period, strategy_summary, rubrics_legend(json), params(json), created_at.
- **posts**: id, plan_id(nullable fk), idea_id(nullable fk), format(photo/carousel/reels), rubric, product, hook, caption, hashtags(json), visual_idea, cta, status(draft/generating/review/approved/scheduled/published/failed), disclaimer_ok(bool), compliance_notes, scheduled_at, published_at, ig_media_id, permalink, error, created_at.
- **post_assets**: id, post_id(fk), kind(image/video), path, model, prompt, ord(int), created_at.
- **post_metrics**: id, post_id(fk), reach, likes, comments, saves, shares, plays, captured_at.
- **app_state**: key, value — для IG-токена/expiry и служебных флагов (или отдельная ig_token таблица).

`create_all` создаёт таблицы при старте (как wb-promotion).

## Контракты ключевых сервисов
- `recon.scrape_topic(topic|hashtag, limit) -> list[trend_reel_id]` — Apify `apify/instagram-scraper` (hashtag/search) или `data-slayer/instagram-search-reels`; сразу качает mp4/кадр.
- `recon.analyze(trend_reel_id) -> hook_analysis` — Claude structured output (как content_plan).
- `planner.generate_and_store(params) -> content_plan_id` — обёртка `content_plan.generate()`.
- `generator.generate_post_assets(post_id)` — `scenes.generate_scene(prompt, ratio, model, out_name)` с референсом лица бренда → post_assets; текст Claude при необходимости.
- `compliance.check(post) -> {disclaimer_ok, violations[]}` — словарь стоп-слов + проверка дисклеймера.
- `publisher.publish(post_id)` — idemпотентно: если status==published → no-op; контейнер `POST /{ig-user-id}/media` (image_url/children) → poll status → `POST /{ig-user-id}/media_publish`; записать ig_media_id/permalink или error.
- `tokens.ensure_fresh()` — если до истечения < 7 дней → `instagram.refresh_token()` → сохранить в app_state.
- `insights.pull(post_id)` — `GET /{ig-media-id}/insights`.

## Планировщик (APScheduler, по образцу wb-promotion)
- `publish_due` — каждую минуту: посты со status=scheduled и scheduled_at<=now → publish.
- `refresh_ig_token` — раз в сутки: tokens.ensure_fresh.
- `pull_insights` — раз в N часов для опубликованных за последние 30 дней.
- (опц.) `recon_cron` — раз в день собрать тренды по заданным темам.
- Event-listener heartbeat + try/except в каждом джобе (тихие сбои недопустимы).

## Фазы (макс. параллельность)
- **Фаза 1 (блокирующая, фундамент):** app.py + БД (модели, create_all) + base.html/nav + config + локальный запуск + хранение IG-токена в app_state. Без неё ничего.
- Дальше параллельно:
  - **Фаза 2 — Разведка:** apify search-reels + recon.analyze + UI /recon (список, сортировка по просмотрам, кнопка «в идеи»).
  - **Фаза 3 — План + Банк идей:** planner + UI /plan и /ideas; посты плана → черновики.
- **Фаза 4 — Генерация:** generator (scenes + лицо бренда) + post_assets + UI карточки поста. (нужны посты из Ф2/Ф3)
- **Фаза 5 — Аппрув + БАД-линт:** compliance + статус-воркфлоу в UI. (нужна Ф4)
- **Фаза 6 — Публикация + планировщик:** publisher + scheduler + tokens. (нужны Ф4,Ф5)
- **Фаза 7 — Аналитика:** insights + /analytics. (нужна Ф6)
- **Фаза 8 (финал) — Деплой:** systemd + nginx-поддомен + плитка Штаба + security-review + критика «10 причин».

## Edge cases / «10 причин обосраться»
1. **App Review не пройден** → реальный постинг невозможен. Митигейт: режим SIMULATE (постит «как бы», пишет в БД без вызова API) + явный флаг готовности.
2. **Аккаунт Creator, а не Business** → API не публикует. Проверить тип на Ф1 (`get_profile.account_type`), показать предупреждение.
3. **Токен истёк** → tokens.ensure_fresh + алерт; публикация при невалидном токене → failed, не молча.
4. **Контейнер IG ещё обрабатывается** → poll status_code до FINISHED, публиковать раньше = 400; таймаут ~5 мин → failed.
5. **Двойная публикация** (рестарт во время джоба) → идемпотентность по status + проверка ig_media_id перед публикацией.
6. **Apify вернул 0 / сломался** → fallback-актор + лог + не падать.
7. **mp4-ссылка протухла** → качаем сразу при сборе (Ф2), не лениво.
8. **Grok safety/ошибка генерации** → retry + fallback модель (как уже в scenes.py), статус generating не зависает.
9. **БАД-нарушение проскочило** → линт блокирует аппрув; override только явный, с записью.
10. **ProxyAPI не поддержал messages.parse/thinking** → фолбэк на обычный JSON-промпт + ручной парс; проверить на Ф1/Ф3.
11. **Стоимость** (Apify+Grok+Claude) → лимиты: maxTotalChargeUsd у Apify, кап на генерации/день.
12. **Рестарт VPS во время scheduler-джоба** → recovery как в wb-promotion (benign, восстанавливается).
13. **Пустые состояния** (нет идей/плана/токена) → дружелюбные заглушки, не 500.

## Безопасность (для финала)
- IG-токен/APIFY_TOKEN/XAI/ANTHROPIC — только в `.env`/app_state, никогда во фронт.
- Поддомен под auth (как биддер) — не публичный.
- РФ-данные на РФ-сервере (VPS).
- Нет хардкода — темы/SKU/расписание из БД.

## Открытые вопросы (закрыть до Ф1)
- Q1: тип IG-аккаунта (Business?) — см. spec [NEEDS CLARIFICATION].
- Q2: ProxyAPI vs прямой Anthropic для structured output.
- Q3: имя поддомена сервиса (`content.` / `smm.` / `zavod.`).
- Q4: где хостим — на VPS биддера (195.24.71.21) или отдельный.
