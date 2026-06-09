# План: генерация сцен (Replicate) + связка с бренд-оверлеем

Проект: `~/projects/instagram-automation`. Дата: 2026-06-09. Фаза D (PLANS.md).
Статус: **ДРАФТ — на согласование (annotation cycle), код не начат.**

## Проблема / зачем
На тёмной заглушке невозможно выбрать каркас оверлея (block/band/anchor) и оценить
bottle-карточки. Нужны реальные фоновые сцены под Instagram 4:5 (и 9:16 для Stories),
чтобы тестировать наш бренд поверх живых картинок и потом постить карусели.

## Acceptance criteria
1. Команда: промпт → сгенерированная сцена 4:5 (1080×1350) в `output/scenes/`.
2. Можно сразу прогнать сцену через `brand_overlay` (block/band/anchor) → готовая карточка.
3. Качество: дефолт «test» (дёшево, для итераций), флаг `--hq` → финальное.
4. Поддержка 9:16 (1080×1920) для Stories/Reels.
5. Нюанс с банкой: для карточек С банкой — генерим фон БЕЗ банки, врезаем реальную банку
   cutout'ом (`brand_overlay._cutout`), этикетка не искажается. Для лайфстайла — как есть.
6. Ключ только в `.env`, не в коде/гите. Понятная ошибка, если ключа/баланса нет.
7. CLI для быстрого теста: `prompt + [стиль оверлея] + [продукт] → файл`.

## Research → РЕКОМЕНДАЦИЯ
Сравнили 3 пути:
- **A. ProxyAPI gpt-image-2** — один ключ с Claude, нативно «любое разрешение». Минус: новый
  код с нуля, одна модель (gpt-image), дороже за картинку.
- **B. Replicate (как в wb-design)** — у пользователя УЖЕ рабочая инфра: `REPLICATE_API_TOKEN`,
  проверенный хелпер `call_replicate(model, body)` с `Prefer: wait`, протестированы модели
  (flux-1.1-pro-ultra, recraft-v3, imagen-4, seedream-4, ideogram, gpt-image-1). Философия
  wb-design идентична нашей: «4:5, тёмный фон, текст добавляем в пост-обработке».
- **C. Прямой OpenAI** — нужен доступ из РФ, отдельный ключ.

**Выбор: B (Replicate).** Переиспользуем готовый и оплаченный стек, выбор лучших моделей,
минимум нового кода, и это ровно то, чем пользователь уже генерил визуал POWERELIX.
Рабочие параметры из `wb-design/scripts/generate_images.py`:
- Flux: `{"prompt", "aspect_ratio":"4:5"|"9:16", "output_format":"png", "safety_tolerance":5, "raw":False}`
- эндпоинт `https://api.replicate.com/v1/models/<model>/predictions`, header `Prefer: wait`.

Маппинг качества (вместо low/med/high у gpt-image):
- дефолт `test` → `black-forest-labs/flux-dev` (~$0.003, быстро, для перебора сцен);
- `--hq` → `black-forest-labs/flux-1.1-pro-ultra` (проверенная hero-модель wb-design, ~$0.06);
- `--model <slug>` / env `IMAGE_MODEL` — переопределение (recraft-v3, imagen-4, seedream-4…).

## Архитектура (минимум кода)
Новый модуль `ig_automation/scenes.py`:
- `generate_scene(prompt, ratio="4:5", hq=False, model=None) -> Path` — sanitize → call_replicate
  → download → resize к точному 1080×1350 / 1080×1920 → сохранить в `output/scenes/`.
- `sanitize(prompt)` — портировать из wb-design (вырезать hex/кавычки; русский НЕ обязателен,
  т.к. текст рисуем оверлеем — но оставить вырезание, чтобы модель не печатала надписи).
- Конфиг: `config.py` += `REPLICATE_API_TOKEN`, `IMAGE_MODEL` (env, дефолт flux-dev).
- CLI `generate_scene.py`: `--prompt --ratio --hq --model --overlay {none,block,band,anchor}
  --product <id> --title --subtitle` → сцена и (опц.) готовая карточка через `brand_overlay`.
- Промпт-шаблоны: тянуть стили фона из `docs/visual_guide.md` (светлый минимализм / тёплый
  лайфстайл / тёмный премиум). Перед написанием промпта — читать `prompt-lab/playbook-image.md`
  (правило памяти `project_prompt_lab`).

## Edge cases / «10 причин обосраться» + путь пользователя
1. Нет `REPLICATE_API_TOKEN` → явная ошибка с инструкцией (не traceback).
2. Нулевой баланс/402 на Replicate → поймать HTTP, понятное сообщение.
3. Модель вернула webp/url вместо png → нормализовать (download + convert RGB).
4. Таймаут/долгая генерация (>180с, особенно ultra) → retry с backoff, как в wb-design.
5. Модель напечатала на фоне случайный «текст»/логотип → sanitize + промпт «no text, no watermark».
6. Сгенерила не тот ratio → принудительный resize/crop к точному размеру.
7. Модерация Replicate отклонила промпт (NSFW-триггеры в «спорт/тело») → понятное сообщение, не краш.
8. Сеть РФ → Replicate: проверить доступность (как у Claude через прокси?). ВОПРОС ниже.
9. Банка-cutout на тёмной сцене → нужна мягкая тень/обводка, иначе «наклейка». Переиспользовать `_place_bottle`.
10. Стоимость: цикл перебора сцен в `--hq` быстро жжёт деньги → дефолт `test`, лог цены/модели в вывод.
Путь пользователя: `generate_scene.py --prompt "..." --overlay band --product 2` → видит готовую
карточку за один шаг; ошибки — человекочитаемые.

## ОТКРЫТЫЕ ВОПРОСЫ (нужен ответ перед фазой 1)
- В wb-design Replicate работал с Мака напрямую — из текущей среды/прокси РФ доступ к
  `api.replicate.com` есть? (если нет — гонять генерацию на Маке пользователя.)
- Брать `REPLICATE_API_TOKEN` из `wb-design/.env` (скопировать в наш `.env`) — или завести отдельно?

## Фазы
- **Фаза 1 (блокирующая):** config + `scenes.py` (`generate_scene` + sanitize) + CLI без оверлея.
  Проверка: одна сцена 4:5 генерится и сохраняется.
- **Фаза 2:** связка с `brand_overlay` (флаг `--overlay`, `--product` с cutout банки в сцену).
- **Фаза 3:** промпт-шаблоны по `visual_guide.md` + `prompt-lab`; 9:16; batch для перебора каркасов.

## Security
- Токен только в `.env` (уже в `.gitignore`); в код/CLI-вывод не печатать.
- Не логировать полный ответ API с возможными URL-подписями дольше необходимости.
- Лимит на размер/кол-во за прогон (защита от случайного дорогого batch).

## Точки переиспользования (минимальный дифф)
- `call_replicate`, `sanitize`, retry — портировать из `wb-design/scripts/generate_images.py`.
- `_cutout`, `_place_bottle`, `render*` — уже в `brand_overlay.py`.
