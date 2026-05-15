"""Сборка FastAPI: lifespan, миграции, метрики, регистрация роутеров."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from cache import close_redis, init_redis
from db import Base, engine
from events import close_publisher
from routers import boosts, interactions, matches, photos, profiles, system
from storage import ensure_bucket


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# schema migrations (идемпотентные — используем вместо alembic для простоты)
# ---------------------------------------------------------------------------
_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_gender VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_city VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_age_min INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_age_max INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS photos TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS interests TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_tg_id BIGINT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrals_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP",
    "ALTER TABLE matches ADD COLUMN IF NOT EXISTS dialog_started_by BIGINT",
    "ALTER TABLE user_ratings ADD COLUMN IF NOT EXISTS referral_score FLOAT NOT NULL DEFAULT 0",
    "ALTER TABLE user_ratings ADD COLUMN IF NOT EXISTS activity_score FLOAT NOT NULL DEFAULT 0",
]


async def _run_schema_migrations() -> None:
    async with engine.begin() as conn:
        for statement in _MIGRATIONS:
            await conn.execute(text(statement))


# ---------------------------------------------------------------------------
# lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    # models должны быть импортированы для metadata.create_all
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_schema_migrations()
    await init_redis()
    try:
        ensure_bucket()
    except Exception as exc:
        logger.warning("MinIO bootstrap failed (will retry on upload): %s", exc)

    try:
        yield
    finally:
        await close_redis()
        await close_publisher()


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------
app = FastAPI(title="Club Flub Backend", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(system.router)
app.include_router(profiles.router)
app.include_router(photos.router)
app.include_router(interactions.router)
app.include_router(matches.router)
app.include_router(boosts.router)
