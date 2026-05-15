"""Логика подбора кандидатов и формирования очереди в Redis."""
from typing import Optional

from sqlalchemy import func, or_, select

from cache import (
    get_boosts_bulk,
    get_seen_ids,
    pop_from_queue,
    store_profiles_in_queue,
)
from db import AsyncSessionLocal
from models import User, UserRating
from rating import compatibility_bonus, resolve_preferred_gender
from services.profiles import get_user_or_none, profile_payload
from tasks import recalculate_user_rating_async


def _photos_present_clause():
    """SQL-условие: у анкеты есть либо telegram-photo_id, либо хоть одно MinIO-фото."""
    return or_(
        User.photo_id.isnot(None),
        func.coalesce(func.array_length(User.photos, 1), 0) > 0,
    )


async def build_queue(tg_id: int) -> Optional[dict]:
    """Собрать персонализированную очередь анкет для юзера и вернуть первую."""
    async with AsyncSessionLocal() as session:
        me = await get_user_or_none(session, tg_id)
        if not me:
            return None

        seen_ids = await get_seen_ids(tg_id)
        preferred_gender = resolve_preferred_gender(me.gender, me.preferred_gender)

        stmt = (
            select(User, UserRating)
            .outerjoin(UserRating, UserRating.telegram_id == User.telegram_id)
            .where(User.telegram_id != tg_id)
            .where(_photos_present_clause())
        )
        if preferred_gender:
            stmt = stmt.where(User.gender == preferred_gender)

        rows = (await session.execute(stmt)).all()
        candidate_rows = []
        missing_ratings: list[int] = []

        for candidate, rating in rows:
            if candidate.telegram_id in seen_ids:
                continue
            if rating is None:
                missing_ratings.append(candidate.telegram_id)
            candidate_rows.append((candidate, rating))

        if not candidate_rows:
            return None

        if missing_ratings:
            for missing_tg_id in missing_ratings:
                await recalculate_user_rating_async(missing_tg_id, session=session)
            await session.commit()

            rows = (await session.execute(stmt)).all()
            candidate_rows = [
                (candidate, rating)
                for candidate, rating in rows
                if candidate.telegram_id not in seen_ids
            ]

        candidate_ids = [int(c.telegram_id) for c, _ in candidate_rows]
        boosts = await get_boosts_bulk(candidate_ids)

        scored: list[tuple[float, dict]] = []
        for candidate, rating in candidate_rows:
            base_score = float(rating.combined_score if rating else 0.0)
            boost_mult = float(boosts.get(int(candidate.telegram_id), 1.0))
            boosted_score = round(base_score * boost_mult, 2)
            personalized_score = round(
                boosted_score + compatibility_bonus(me, candidate), 2
            )
            payload = profile_payload(
                candidate,
                combined_score=base_score,
                rank_score=personalized_score,
            )
            if boost_mult > 1.0:
                payload["boosted"] = True
                payload["boost_multiplier"] = round(boost_mult, 2)
            scored.append((personalized_score, payload))

        scored.sort(key=lambda item: item[0], reverse=True)
        await store_profiles_in_queue(tg_id, [payload for _, payload in scored])

    return await pop_from_queue(tg_id)
