# Отчёт по проекту

## 1. Краткий обзор

Сервис знакомств в Telegram: 9 контейнеров (бот + backend + 2 celery + consumer + postgres + redis + rabbitmq + minio). Все три уровня рейтинга, событийная архитектура через RabbitMQ, кэш предотранжированных анкет в Redis, фото в S3-совместимом MinIO, Prometheus-метрики, антифлуд-middleware, реферальная система, **Boost-система с TTL в Redis**.

Структура полностью отрефакторена: `backend/main.py` теперь только wiring + lifespan, бизнес-логика разнесена по `routers/` и `services/`.

---

## 2. Карта: требование → файлы → как применено

### Уровень 1 — Первичный рейтинг

| Подпункт | Где | Как применено |
|---|---|---|
| Рейтинг из анкеты (возраст, пол, интересы, гео) | [backend/rating.py:28](backend/rating.py#L28) `calculate_primary_score` | начисляются баллы за каждое заполненное поле `age/gender/city/bio/username` |
| Полнота анкеты + кол-во фото | [backend/rating.py:42-46](backend/rating.py#L42) | `min(len(photos), 5) * 1.5` — больше фото = выше балл |
| Кол-во интересов | [backend/rating.py:49-51](backend/rating.py#L49) | `min(len(interests), 5) * 0.5` |
| Первичные предпочтения (возраст, пол, город) | [backend/rating.py:53-58](backend/rating.py#L53) + [backend/models.py:30-33](backend/models.py#L30) | поля `preferred_gender / preferred_city / preferred_age_min/max`, начисляются доп. баллы за их заполнение |
| Применение предпочтений при показе | [backend/rating.py:135](backend/rating.py#L135) `compatibility_bonus` + [backend/services/matching.py:55](backend/services/matching.py#L55) | при сборке очереди — фильтрация по полу + бонус за город/возраст/пересечение интересов |

### Уровень 2 — Поведенческий рейтинг

| Подпункт | Где | Как применено |
|---|---|---|
| Кол-во лайков анкеты | [backend/tasks.py:32-37](backend/tasks.py#L32) + [backend/rating.py:69](backend/rating.py#L69) | `select count() from likes where to_tg_id = …` → `min(likes_received * 2, 10)` |
| Соотношение лайков и пропусков | [backend/rating.py:71-79](backend/rating.py#L71) | `like_ratio = likes / (likes + skips)` → ступенчатый бонус 1/2/3/4 балла |
| Частота взаимных лайков (мэтчей) | [backend/rating.py:81](backend/rating.py#L81) + [backend/tasks.py:44-50](backend/tasks.py#L44) | `min(matches_count * 3, 9)` |
| Частота инициирования диалогов | [backend/rating.py:82](backend/rating.py#L82) + [backend/models.py:71](backend/models.py#L71) | поле `Match.dialog_started`, endpoint `/matches/dialog-started`, `min(dialogs_started * 2, 6)` |
| Активность в определённое время суток | [backend/rating.py:91](backend/rating.py#L91) `calculate_activity_score` + [backend/models.py:99](backend/models.py#L99) `ActivityHourly` | таблица `user_activity_hourly(tg_id, hour, count)`, бонус за попадание текущего часа в топ-3 пиковых + бонус за свежесть `last_active_at` |

### Уровень 3 — Комбинированный рейтинг

| Подпункт | Где | Как применено |
|---|---|---|
| Весовая модель | [backend/rating.py:120](backend/rating.py#L120) `combine_scores` | `0.45·primary + 0.35·behavioral + 0.10·referral + 0.10·activity` |
| Реферальная система | [backend/routers/profiles.py:67-100](backend/routers/profiles.py#L67) + [bot/handlers/start.py:14-32](bot/handlers/start.py#L14) | deep-link `/start ref_<id>`, инкремент `referrals_count`, бонус `min(refs * 2, 10)` в [backend/rating.py:87](backend/rating.py#L87) |

### Доп. баллы

| Технология | Где | Как применено |
|---|---|---|
| **Отдельная таблица рейтингов** | [backend/models.py:84](backend/models.py#L84) `UserRating` | поля `primary/behavioral/referral/activity/combined_score` + счётчики |
| **Регулярные пересчёты через Celery** | [backend/celery_app.py:20-25](backend/celery_app.py#L20) + [backend/tasks.py:122](backend/tasks.py#L122) | `celery beat` каждый час запускает `tasks.recalculate_all_ratings`. Точечно — `recalculate_user_rating_task.delay(tg_id)` после каждого события |
| **Redis: кэш отранжированных анкет** | [backend/cache.py:67](backend/cache.py#L67) `store_profiles_in_queue` + [backend/services/matching.py](backend/services/matching.py) | при первом запросе строим всю очередь, кладём в `queue:{tg_id}` (LIST, TTL 30 мин). Следующие клики — `LPOP` без БД |
| **Redis: множество "seen"** | [backend/cache.py:49](backend/cache.py#L49) `mark_seen` | `SADD seen:{tg_id}` с TTL 7 дней — не показываем одну и ту же анкету |
| **RabbitMQ для потоковой обработки событий** | [backend/events.py](backend/events.py) (publisher) + [backend/consumer.py](backend/consumer.py) (consumer) | топик-exchange `dating.events`, события: `user.registered / profile.updated / profile.preferences_updated / profile.deleted / interaction.like / interaction.skip / match.created / match.dialog_started / boost.claimed`. Consumer слушает `#` и ставит задачу пересчёта в Celery |
| **Prometheus-метрики** | [backend/main.py:69](backend/main.py#L69) | `prometheus_fastapi_instrumentator` + endpoint `/metrics` (HTTP requests, latency, in-progress) |
| **Структурированное логирование** | [backend/main.py:46-49](backend/main.py#L46) + [bot/main.py:11-14](bot/main.py#L11) | формат `time level logger :: msg` |
| **S3-хранилище для фото (MinIO)** | [backend/storage.py](backend/storage.py) + [docker-compose.yml:50-83](docker-compose.yml#L50) (`minio` + `minio-init`) | boto3-клиент, ключи `users/{tg_id}/{uuid}.jpg`, до 5 фото, `presigned_url`, удаление при `DELETE /profile`. Бот скачивает фото из Telegram → шлёт multipart в backend → backend кладёт в MinIO |

---

## 3. Доп. функционал

###  Boost-система с TTL в Redis
- **Файлы**: [backend/cache.py:84-126](backend/cache.py#L84) (хранилище), [backend/services/matching.py:78-92](backend/services/matching.py#L78) (применение в очереди), [backend/routers/boosts.py](backend/routers/boosts.py) (API), [bot/handlers/settings.py:75-127](bot/handlers/settings.py#L75) (UI)
- **Как работает**: каждый юзер может иметь временный множитель к своему `combined_score`. Хранится в Redis `boost:{tg_id} → 1.50, EX=86400`. В `build_queue` все бусты кандидатов забираются батчем `MGET` за один запрос и применяются перед сортировкой — boosted-анкеты всплывают вверх.
- **`apply_boost`** берёт `max(существующий, новый)` по силе И длительности — пересечение бустов не убивает действующий сильный.
- **4 триггера**:
  | Событие | × | TTL |
  |---|---|---|
  | Регистрация (онбординг) | 2.0 | 1ч |
  | За каждого приглашённого реферала | 1.5 | 24ч |
  | Анкета впервые стала "complete" | 1.4 | 1ч |
  | Ежедневный клейм через бота | 1.3 | 24ч |
- **Защита от двойного клейма**: атомарный `SET NX EX 86400` на `boost:claim:{tg_id}` ([backend/cache.py:140](backend/cache.py#L140)).
- **Эмиттит событие** `boost.claimed` в RabbitMQ.
- **В UI**: бейдж  *boosted* в карточке кандидата ([bot/services/format.py:58](bot/services/format.py#L58)), статус и обратный отсчёт в «Моей анкете», кнопка «Получить дневной буст» в Настройках.

###  Интересы с семантическим бонусом
- **Файлы**: [backend/models.py:29](backend/models.py#L29) (`interests TEXT[]`), [backend/rating.py:128-132](backend/rating.py#L128) (`_interests_overlap`), [backend/rating.py:159-163](backend/rating.py#L159) (бонус), [bot/handlers/profile.py:90-108](bot/handlers/profile.py#L90) (FSM)
- При показе кандидата считается пересечение `set(my.interests) & set(candidate.interests)`, добавляется до +4 баллов к `compatibility_bonus`.

###  Multi-photo upload в MinIO
- До 5 фото на анкету. В FSM регистрации после первого фото — состояние `extra_photos`, можно слать ещё, пока не нажмёшь «Готово».
- **Файлы**: [bot/handlers/profile.py:131-178](bot/handlers/profile.py#L131), [backend/routers/photos.py](backend/routers/photos.py), [backend/storage.py:50-65](backend/storage.py#L50).

###  Deep-link рефералы
- Ссылка вида `https://t.me/<bot>?start=ref_<my_id>` ([bot/handlers/settings.py:147](bot/handlers/settings.py#L147)).
- В `/start` распознаётся payload `ref_<id>`, инкрементится `referrals_count` приглашающего, выдаётся буст ×1.5 на 24ч.

###  Трекинг инициирования диалогов
- После мэтча кнопка « Написать первым» → `POST /matches/dialog-started` → `Match.dialog_started=True` → бонус в behavioral_score.
- **Файлы**: [bot/handlers/matches.py:71-80](bot/handlers/matches.py#L71), [backend/routers/matches.py:55-79](backend/routers/matches.py#L55).

###  Antiflood middleware
- In-memory throttler в боте: 1 апдейт / 0.4 сек / юзер.
- **Файл**: [bot/middlewares.py](bot/middlewares.py).

### Activity by-hour гистограмма
- На каждом запросе к backend (`bump_activity` в [backend/services/profiles.py:18](backend/services/profiles.py#L18)) инкрементится `user_activity_hourly[hour]` и `last_active_at`. Используется в `calculate_activity_score`.

### Идемпотентные миграции без alembic
- На старте backend выполняется список `ALTER TABLE … IF NOT EXISTS` ([backend/main.py:24-37](backend/main.py#L24)) — можно поднимать на свежей БД и на старой.

---

## 4. Структура проекта

```
backend/
├── main.py               # FastAPI lifespan + регистрация роутеров 
├── config.py             # константы 
├── db.py                 # async SQLAlchemy engine
├── models.py             # User, Like, Skip, Match, UserRating, ActivityHourly
├── rating.py             # 4 формулы + compatibility_bonus
├── cache.py              # Redis: seen, queue, boosts
├── storage.py            # MinIO (boto3)
├── events.py             # RabbitMQ publisher (aio-pika)
├── consumer.py           # отдельный процесс: RabbitMQ → Celery
├── celery_app.py         # Celery + beat schedule
├── tasks.py              # пересчёт рейтингов
├── routers/
│   ├── system.py         # /
│   ├── profiles.py       # /register, /update_profile, /preferences, GET/DELETE /profile
│   ├── photos.py         # /profile/{id}/photos
│   ├── interactions.py   # /like, /skip, /get_match, /likes/received
│   ├── matches.py        # /matches, /matches/dialog-started
│   └── boosts.py         # /boost, /boost/claim-daily
└── services/
    ├── profiles.py       # helpers (get_user, bump_activity, profile_payload)
    └── matching.py       # build_queue (с применением бустов)

bot/
├── main.py               # aiogram dispatcher + middleware
├── api.py                # типизированный REST-клиент к backend
├── config.py             # BOT_TOKEN, BACKEND_URL
├── middlewares.py        # antiflood
├── states/profile.py     # FSM: ProfileRegistration, PreferencesEdit
├── keyboards/            # main_kb, profile_kb
├── handlers/
│   ├── start.py          # /start (с deep-link), /help, /profile, /matches
│   ├── profile.py        # FSM регистрации + multi-photo
│   ├── my_profile.py     # «Моя анкета»
│   ├── search.py         # «Смотреть анкеты», лайк/скип
│   ├── matches.py        # «Мои мэтчи», диалог
│   └── settings.py       # настройки, предпочтения, рефералы, бусты, удаление
└── services/
    ├── format.py         # чистые форматтеры (TTL, профиль, кандидат, буст)
    └── notify.py         # уведомления о мэтче и диалоге
```

---

## 5.Запуск

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps    
```

| Где смотреть | URL |
|---|---|
| Swagger | http://localhost:8000/docs |
| Prometheus метрики | http://localhost:8000/metrics |
| RabbitMQ management | http://localhost:15672 |
| MinIO console | http://localhost:9001 |

---

## 6. Фишки
- **Boost-система с TTL в Redis** — не было в спеке, добавлена как нестандартная фишка с честным алгоритмом стэкинга (max по силе и TTL)
- **Activity-by-hour гистограмма** — не просто `last_seen`, а полноценный массив часов с пиковыми бонусами
- **Идемпотентные миграции** на старте — позволяют поднимать без alembic, не падая на повторных запусках
- **Чистая архитектура**: 6 routers + 2 services + чистые форматтеры в боте без I/O
- **Topic-exchange RabbitMQ** с routing keys по доменам (`profile.*`, `interaction.*`, `match.*`, `boost.*`) — легко подключить новых консьюмеров без правки publisher
- **MGET всех бустов одним запросом** в `build_queue` — масштабируется на сотни кандидатов без N+1
