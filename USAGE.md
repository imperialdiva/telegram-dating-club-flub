# Club Flub — Telegram Dating Bot

## Что сделано

### Архитектура (микросервисы)
- **bot** — Telegram-бот на aiogram 3.x (FSM, anti-flood middleware, deep-link рефералы)
- **backend** — FastAPI: профили, фото, лайки/скипы/мэтчи, диалоги, рейтинги, метрики `/metrics`
- **rating_consumer** — отдельный процесс, слушает RabbitMQ exchange `dating.events` и ставит задачи пересчёта рейтинга в Celery
- **celery_worker** — выполняет задачи пересчёта рейтинга (одна анкета или массовый пересчёт)
- **celery_beat** — каждый час запускает массовый пересчёт всех рейтингов
- **db (PostgreSQL)** — основное хранилище (`users`, `likes`, `skips`, `matches`, `user_ratings`, `user_activity_hourly`)
- **redis** — кэш отранжированной очереди анкет + множество "seen" + Celery broker
- **rabbitmq** — топик-exchange `dating.events` (events: `user.registered`, `profile.updated`, `profile.preferences_updated`, `profile.deleted`, `interaction.like`, `interaction.skip`, `match.created`, `match.dialog_started`)
- **minio** — S3-совместимое хранилище фото (бакет `photos`, ключи `users/{tg_id}/{uuid}.jpg`)
- **minio-init** — одноразовый job, создаёт бакет и ставит anonymous read

### Анкета пользователя
- Имя, возраст, город, био, пол
- **Интересы** (до 10 тегов, через запятую)
- **До 5 фото**: оригинал заливается в **MinIO** через backend, плюс хранится Telegram `file_id` для быстрого показа в чате
- Предпочтения: пол, город, возрастной диапазон (`18-30`)
- **Реферальная ссылка** (`/start ref_<my_id>`) — приглашённый засчитывается приглашающему

### Алгоритм рейтинга — все три уровня
| Уровень | Что считаем | Где |
|---|---|---|
| **1. Primary** | возраст, пол, город, био, username, кол-во фото (до 5), кол-во интересов, заполнены ли предпочтения | [backend/rating.py:28](backend/rating.py#L28) |
| **2. Behavioral** | полученные лайки, ratio лайков/скипов, мэтчи, начатые диалоги | [backend/rating.py:62](backend/rating.py#L62) |
| **2. Activity** | гистограмма активности по часам (`user_activity_hourly`), бонус если кандидат активен в текущий час, бонус за свежесть `last_active_at` | [backend/rating.py:91](backend/rating.py#L91) |
| **3. Referral** | счётчик `referrals_count` × 2, до +10 | [backend/rating.py:87](backend/rating.py#L87) |
| **3. Combined** | `0.45·primary + 0.35·behavioral + 0.10·referral + 0.10·activity` | [backend/rating.py:120](backend/rating.py#L120) |
| **Compatibility bonus** (на лету при показе) | город, пол, возраст в диапазоне, **пересечение интересов** | [backend/rating.py:135](backend/rating.py#L135) |

Рейтинги хранятся в отдельной таблице `user_ratings` и пересчитываются:
- **по событиям** — `interaction.like` / `interaction.skip` / `match.dialog_started` / `profile.updated` → RabbitMQ → consumer → Celery
- **периодически** — каждый час (`celery beat`) пересчитывает всех (`tasks.recalculate_all_ratings`)

### Кэш Redis
- Когда пользователь нажимает «Смотреть анкеты», backend подгружает первую анкету через полный путь (БД + рейтинг + персональный бонус), а **ещё N кандидатов укладывает в Redis-очередь** `queue:{tg_id}` ([backend/cache.py:67](backend/cache.py#L67)).
- Следующий клик берёт анкету через `LPOP` без обращения к БД.
- Очередь инвалидируется при изменении профиля, лайке, скипе, удалении.
- Множество `seen:{tg_id}` хранится 7 дней — чтобы не показывать одну и ту же анкету.

### 🚀 Boost-система (TTL в Redis)
- Каждый пользователь может иметь временный множитель к своему `combined_score`. Хранится в Redis: `boost:{tg_id}` → значение `1.50`, `EX = 86400` ([backend/cache.py:84](backend/cache.py#L84)).
- В `build_queue` множители всех кандидатов подтягиваются батчем `MGET` и применяются к их рейтингу — буст временно поднимает анкету в чужих очередях.
- В карточке кандидата (бот) с активным бустом появляется бейдж 🚀 *boosted*.
- `apply_boost` берёт максимум по силе И длительности — повторный буст не "обнуляет" сильный действующий.
- **Триггеры буста** (все настраиваются константами в [backend/main.py](backend/main.py)):
  | Событие | Множитель | TTL |
  |---|---|---|
  | Регистрация (онбординг) | ×2.0 | 1 час |
  | За каждого приглашённого реферала | ×1.5 | 24 часа |
  | Заполнение анкеты до конца (анкета+фото) | ×1.4 | 1 час |
  | Ежедневный клейм (раз в 24ч) | ×1.3 | 24 часа |
- Ежедневный клейм защищён ключом `boost:claim:{tg_id}` с `SET NX EX 86400` — атомарный rate-limit без гонок.
- Очередь юзера инвалидируется при выдаче буста, чтобы новый множитель сразу применился к нему самому.

### Метрики и логирование
- `/metrics` на backend (Prometheus) — встроено `prometheus_fastapi_instrumentator`
- структурированный stdout-лог в формате `time level logger :: msg`
- antiflood-middleware в боте (1 апдейт / 0.4 сек / юзер)

---

## Как запустить

### 1) Подготовка
```bash
cp .env.example .env
# в .env вставить BOT_TOKEN от @BotFather
```

### 2) Запуск
```bash
docker compose up -d --build
```

Проверить, что всё поднялось:
```bash
docker compose ps
```

Должно быть зелёным: `db`, `redis`, `rabbitmq`, `minio`, `minio-init` (exited 0), `backend`, `celery_worker`, `celery_beat`, `rating_consumer`, `bot`.

### 3) UI / порты
| Что | URL |
|---|---|
| Backend Swagger | http://localhost:8000/docs |
| Backend `/metrics` | http://localhost:8000/metrics |
| RabbitMQ management | http://localhost:15672 (login `dating` / `dating`) |
| MinIO console | http://localhost:9001 (login `minioadmin` / `minioadmin`) |
| Бот | в Telegram, по токену из `.env` |

### 4) Логи
```bash
docker compose logs -f bot
docker compose logs -f backend
docker compose logs -f rating_consumer
docker compose logs -f celery_worker
```

### 5) Остановить
```bash
docker compose down             
docker compose down -v           
```

---

## Как пользоваться ботом

| Кнопка / команда | Что происходит |
|---|---|
| `/start` | Регистрация (берётся `telegram_id`). Если открыл по реф-ссылке `?start=ref_<id>` — пригласивший получит +балл |
| `/help` | Список команд |
| **👤 Моя анкета** | Показ профиля + рейтинга (combined / primary / behavioral / activity / referral) |
| **🔍 Смотреть анкеты** | Получает следующую анкету из Redis-очереди или строит новую через backend |
| ❤️ / 👎| Лайк / скип. Если лайк взаимный — оба получают карточку с кнопкой **«💬 Написать первым»** |
| **💞 Мои мэтчи** | Список взаимных лайков, у каждого — кнопка «Написать первым» (ставит `dialog_started=True` и шлёт уведомление мэтчу) |
| **⚙️ Настройки → Редактировать анкету** | Перезапускает FSM регистрации (имя→возраст→город→био→пол→интересы→фото→ещё фото) |
| **⚙️ → Изменить предпочтения** | FSM: пол поиска → город → возрастной диапазон |
| **⚙️ → Реферальная ссылка** | Показывает твою `https://t.me/<bot>?start=ref_<id>` |
| **⚙️ → 🚀 Мой буст** | Показывает активный множитель и кнопку «Получить дневной буст ×1.3» (раз в 24ч) |
| **⚙️ → Удалить анкету** | Подтверждение → удаление профиля, фото в MinIO, лайков, мэтчей, активности |

---

## REST API (backend)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | health |
| GET | `/metrics` | Prometheus |
| POST | `/register?tg_id=&username=&first_name=&referrer_tg_id=` | регистрация / повторный визит |
| POST | `/update_profile` (JSON) | заменить анкету |
| PATCH | `/preferences` (JSON) | обновить только предпочтения |
| GET | `/profile/{tg_id}` | анкета + рейтинг |
| DELETE | `/profile/{tg_id}` | удалить анкету (+ фото + всё связанное) |
| POST | `/profile/{tg_id}/photos` (multipart `file=`) | загрузить фото в MinIO |
| DELETE | `/profile/{tg_id}/photos/{index}` | удалить N-е фото |
| POST | `/like` `{from_tg_id, to_tg_id}` | лайк (вернёт `mutual` + `match_created`) |
| POST | `/skip` `{from_tg_id, to_tg_id}` | пропуск |
| GET | `/get_match?tg_id=` | следующая анкета (через очередь Redis) |
| GET | `/matches/{tg_id}` | список мэтчей |
| POST | `/matches/dialog-started` `{from_tg_id, to_tg_id}` | пометить диалог начатым |
| GET | `/likes/received/{tg_id}` | счётчик и рейтинг |
| GET | `/boost/{tg_id}` | текущий буст + cooldown дневного клейма |
| POST | `/boost/{tg_id}/claim-daily` | забрать дневной буст ×1.3 на 24ч |

---

---


## Структура проекта

```
.
├── docker-compose.yml         # 9 сервисов
├── .env.example               # все переменные
├── README.md                  # описание архитектуры (mermaid)
├── USAGE.md                   # этот файл
├── docs/services.md           # описание сервисов
├── backend/
│   ├── main.py                # FastAPI: профили, фото, лайки, мэтчи, диалоги
│   ├── models.py              # SQLAlchemy: User, Like, Skip, Match, UserRating, ActivityHourly
│   ├── db.py                  # async engine + session
│   ├── rating.py              # все 4 формулы рейтинга + compatibility_bonus
│   ├── cache.py               # Redis: seen + queue
│   ├── celery_app.py          # Celery + beat-расписание
│   ├── tasks.py               # пересчёт рейтингов
│   ├── consumer.py            # RabbitMQ → Celery bridge
│   ├── events.py              # publisher (aio-pika)
│   ├── storage.py             # MinIO (boto3)
│   └── Dockerfile
└── bot/
    ├── main.py                # aiogram dispatcher
    ├── api.py                 # REST-клиент к backend
    ├── middlewares.py         # antiflood
    ├── states/profile.py      # FSM: ProfileRegistration, PreferencesEdit
    ├── handlers/
    │   ├── start.py           # /start (с deep-link), /help, /profile, /matches, /settings
    │   ├── profile.py         # FSM регистрации + multi-photo upload
    │   ├── my_profile.py      # «👤 Моя анкета»
    │   ├── search.py          # «🔍 Смотреть анкеты», лайк/скип
    │   ├── matches.py         # «💞 Мои мэтчи», диалог
    │   └── settings.py        # настройки, предпочтения, реф-ссылка, удаление
    ├── keyboards/
    └── Dockerfile
```

---

