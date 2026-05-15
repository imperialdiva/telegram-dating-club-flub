"""Работа с пользователем и активностью."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ActivityHourly, User
from storage import public_url


async def get_user_or_none(session: AsyncSession, tg_id: int) -> Optional[User]:
    return await session.scalar(select(User).where(User.telegram_id == tg_id))


async def bump_activity(session: AsyncSession, tg_id: int) -> None:
    """Обновить last_active_at и почасовую гистограмму активности юзера."""
    now = datetime.utcnow()
    user = await get_user_or_none(session, tg_id)
    if user:
        user.last_active_at = now

    record = await session.scalar(
        select(ActivityHourly).where(
            ActivityHourly.telegram_id == tg_id,
            ActivityHourly.hour == now.hour,
        )
    )
    if record is None:
        session.add(ActivityHourly(telegram_id=tg_id, hour=now.hour, count=1))
    else:
        record.count = int(record.count or 0) + 1


def is_profile_complete(user: User) -> bool:
    has_photo = bool(user.photo_id) or bool(user.photos)
    return all(
        [user.first_name, user.age, user.gender, user.city, user.bio, has_photo]
    )


def photo_urls(user: User) -> list[str]:
    return [public_url(key) for key in (user.photos or [])]


def profile_payload(
    user: User,
    combined_score: float | None = None,
    rank_score: float | None = None,
) -> dict:
    payload = {
        "tg_id": user.telegram_id,
        "name": user.first_name,
        "age": user.age,
        "city": user.city,
        "bio": user.bio,
        "gender": user.gender,
        "photo_id": user.photo_id,
        "photos": list(user.photos or []),
        "photo_urls": photo_urls(user),
        "interests": list(user.interests or []),
    }
    if combined_score is not None:
        payload["combined_score"] = combined_score
    if rank_score is not None:
        payload["rank_score"] = rank_score
    return payload


def canonical_match_pair(first_tg_id: int, second_tg_id: int) -> tuple[int, int]:
    return tuple(sorted((int(first_tg_id), int(second_tg_id))))
