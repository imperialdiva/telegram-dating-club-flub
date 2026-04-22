import asyncio
import logging
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cache import delete_queue, init_redis
from celery_app import celery_app
from db import AsyncSessionLocal
from models import Like, Match, Skip, User, UserRating
from rating import calculate_behavioral_score, calculate_primary_score, combine_scores


logger = logging.getLogger(__name__)


async def recalculate_user_rating_async(
    tg_id: int,
    session: AsyncSession | None = None,
) -> UserRating | None:
    owns_session = session is None
    if owns_session:
        session = AsyncSessionLocal()

    try:
        user = await session.scalar(select(User).where(User.telegram_id == tg_id))
        if not user:
            return None

        likes_received = int(
            await session.scalar(
                select(func.count()).select_from(Like).where(Like.to_tg_id == tg_id)
            )
            or 0
        )
        skips_received = int(
            await session.scalar(
                select(func.count()).select_from(Skip).where(Skip.to_tg_id == tg_id)
            )
            or 0
        )
        matches_count = int(
            await session.scalar(
                select(func.count()).select_from(Match).where(
                    (Match.user1_tg_id == tg_id) | (Match.user2_tg_id == tg_id)
                )
            )
            or 0
        )
        dialogs_started = int(
            await session.scalar(
                select(func.count()).select_from(Match).where(
                    ((Match.user1_tg_id == tg_id) | (Match.user2_tg_id == tg_id))
                    & (Match.dialog_started.is_(True))
                )
            )
            or 0
        )

        primary_score = calculate_primary_score(user)
        behavioral_score = calculate_behavioral_score(
            likes_received=likes_received,
            skips_received=skips_received,
            matches_count=matches_count,
            dialogs_started=dialogs_started,
        )
        combined_score = combine_scores(primary_score, behavioral_score)

        rating = await session.scalar(
            select(UserRating).where(UserRating.telegram_id == tg_id)
        )
        if rating is None:
            rating = UserRating(telegram_id=tg_id)
            session.add(rating)

        rating.primary_score = primary_score
        rating.behavioral_score = behavioral_score
        rating.combined_score = combined_score
        rating.likes_received = likes_received
        rating.skips_received = skips_received
        rating.matches_count = matches_count
        rating.dialogs_started = dialogs_started
        rating.last_calculated_at = datetime.utcnow()

        if owns_session:
            await session.commit()

        return rating
    except Exception:
        if owns_session:
            await session.rollback()
        logger.exception("Failed to recalculate rating for %s", tg_id)
        raise
    finally:
        if owns_session:
            await session.close()


async def recalculate_all_ratings_async() -> None:
    async with AsyncSessionLocal() as session:
        tg_ids = (await session.execute(select(User.telegram_id))).scalars().all()
        for tg_id in tg_ids:
            await recalculate_user_rating_async(int(tg_id), session=session)
        await session.commit()


async def delete_user_state_async(tg_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserRating).where(UserRating.telegram_id == tg_id))
        await session.commit()
    await init_redis()
    await delete_queue(tg_id)


async def invalidate_user_queue_async(tg_id: int) -> None:
    await init_redis()
    await delete_queue(tg_id)


def schedule_recalculate_user_rating(*tg_ids: int) -> None:
    for tg_id in {int(value) for value in tg_ids if value is not None}:
        recalculate_user_rating_task.delay(tg_id)


def schedule_delete_queue(*tg_ids: int) -> None:
    for tg_id in {int(value) for value in tg_ids if value is not None}:
        invalidate_user_queue_task.delay(tg_id)


def schedule_recalculate_all_ratings() -> None:
    recalculate_all_ratings_task.delay()


def _run_async(coro) -> None:
    asyncio.run(coro)


@celery_app.task(name="tasks.recalculate_user_rating")
def recalculate_user_rating_task(tg_id: int) -> None:
    _run_async(recalculate_user_rating_async(int(tg_id)))


@celery_app.task(name="tasks.invalidate_user_queue")
def invalidate_user_queue_task(tg_id: int) -> None:
    _run_async(invalidate_user_queue_async(int(tg_id)))


@celery_app.task(name="tasks.recalculate_all_ratings")
def recalculate_all_ratings_task() -> None:
    _run_async(recalculate_all_ratings_async())


@celery_app.task(name="tasks.delete_user_state")
def delete_user_state_task(tg_id: int) -> None:
    _run_async(delete_user_state_async(int(tg_id)))
