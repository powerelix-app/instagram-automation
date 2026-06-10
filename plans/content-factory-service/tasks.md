# Tasks — Контент-завод

Легенда: `[ ]` не начато · `[~]` в работе · `[x]` готово · **(P)** parallel-safe · **(S)** sequential.

## Фаза 1 — Фундамент сервиса (S, блокирующая)
- [ ] T-101 (S) `db/base.py`: engine SQLite, Session, Base (SQLAlchemy 2.0).
- [ ] T-102 (S) `db/models.py`: все таблицы из plan.md + create_all.
- [ ] T-103 (S) `app.py`: FastAPI create_app, lifespan со scheduler-хуком, config-load.
- [ ] T-104 (S) `web/templates/base.html` + nav (рубрики конвейера), Tailwind CDN.
- [ ] T-105 (S) auth (cookie-сессия, как биддер) — поддомен не публичный.
- [ ] T-106 (S) хранение IG-токена в app_state; страница /status: тип аккаунта (Business?), валидность токена, остаток дней.
- [ ] T-107 (S) Q1/Q2/Q4 закрыть фактами (account_type через get_profile; тест messages.parse через ProxyAPI).

## Фаза 2 — Разведка (P, после Ф1)
- [ ] T-201 (P) `apify.py`: функция search_reels(topic/hashtag, limit) на актор поиска; сразу скачать mp4/кадр в data/media.
- [ ] T-202 (P) `services/recon.py`: scrape_topic → trend_reels; analyze(reel) → hook_analyses (Claude structured).
- [ ] T-203 (P) UI `/recon`: запуск сбора, список с сортировкой по просмотрам, карточка разбора, кнопка «в Банк идей».
- [ ] T-204 (P) лимиты Apify (maxTotalChargeUsd) + fallback-актор + лог сбоев.

## Фаза 3 — План + Банк идей (P, после Ф1)
- [ ] T-301 (P) `services/planner.py`: обёртка content_plan.generate → content_plans + posts(draft опц.).
- [ ] T-302 (P) UI `/plan`: форма (N, старт, частота, фокус), просмотр плана, кнопка «посты → черновики».
- [ ] T-303 (P) UI `/ideas`: банк идей (источник/рубрика/продукт/статус), «создать черновик поста».

## Фаза 4 — Генерация (S, после Ф2/Ф3)
- [ ] T-401 `services/generator.py`: generate_post_assets(post) — scenes.generate_scene с лицом бренда (assets/brand/ai_model.png) → post_assets.
- [ ] T-402 текст поста (подпись/хэштеги/хук) — из плана или Claude-догенерация.
- [ ] T-403 UI карточки поста `/post/{id}`: визуал, текст, перегенерация, статус.

## Фаза 5 — Аппрув + БАД-линт (S, после Ф4)
- [ ] T-501 `services/compliance.py`: словарь стоп-слов + проверка дисклеймера → violations.
- [ ] T-502 статус-воркфлоу в UI: draft→review→approved; блок аппрува при нарушениях; явный override с записью.

## Фаза 6 — Публикация + планировщик (S, после Ф4/Ф5)
- [ ] T-601 `instagram.py`: create_container (image/carousel) + poll status + media_publish.
- [ ] T-602 `services/publisher.py`: идемпотентная publish(post) + статусы + error.
- [ ] T-603 `services/tokens.py`: ensure_fresh (refresh при <7 дней) + алерт.
- [ ] T-604 `scheduler.py`: publish_due (1 мин), refresh_ig_token (сутки) + heartbeat/try-except.
- [ ] T-605 режим SIMULATE до прохождения App Review (флаг).

## Фаза 7 — Аналитика (S, после Ф6)
- [ ] T-701 `services/insights.py`: pull метрик опубликованных.
- [ ] T-702 джоб pull_insights + UI `/analytics`: сводка по рубрикам/хукам.

## Фаза 8 — Деплой (S, финал)
- [ ] T-801 systemd-юнит на VPS + порт + .env.
- [ ] T-802 nginx-поддомен + TLS + security-headers + auth.
- [ ] T-803 плитка на Штабе (hub/index.html) → активная.
- [ ] T-804 security-review + критика «10 причин» + проход пользовательского пути.
- [ ] T-805 requirements.txt привести в порядок (добавить Pillow/numpy/rembg/onnxruntime/fastapi/sqlalchemy/apscheduler/jinja2/uvicorn).
- [ ] T-806 обновить PLANS.md репо + git commit/push.
