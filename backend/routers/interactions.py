from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cache import mark_seen, pop_from_queue
from db import AsyncSessionLocal
from events import publish_event
from models import Like, Match, Skip, User, UserRating
from services.matching import build_queue
from services.profiles import (
    bump_activity,
    canonical_match_pair,
    get_user_or_none,
    profile_payload,
)
from tasks import schedule_recalculate_user_rating


router = APIRouter()


class InteractionRequest(BaseModel):
    from_tg_id: int
    to_tg_id: int


@router.post("/like")
async def record_like(data: InteractionRequest):
    mutual = False
    match_created = False
    matched_profile: Optional[dict] = None
    actor_profile: Optional[dict] = None

    async with AsyncSessionLocal() as session:
        existing_like = await session.scalar(
            select(Like).where(
                Like.from_tg_id == data.from_tg_id,
                Like.to_tg_id == data.to_tg_id,
            )
        )
        if existing_like:
            await mark_seen(data.from_tg_id, data.to_tg_id)
            return {
                "status": "already_liked",
                "mutual": False,
                "match_created": False,
                "matched_profile": None,
                "actor_profile": None,
            }

        existing_skip = await session.scalar(
            select(Skip).where(
                Skip.from_tg_id == data.from_tg_id,
                Skip.to_tg_id == data.to_tg_id,
            )
        )
        if existing_skip:
            await session.delete(existing_skip)

        session.add(Like(from_tg_id=data.from_tg_id, to_tg_id=data.to_tg_id))
        await session.flush()

        actor = await get_user_or_none(session, data.from_tg_id)
        target = await get_user_or_none(session, data.to_tg_id)

        reverse_like = await session.scalar(
            select(Like).where(
                Like.from_tg_id == data.to_tg_id,
                Like.to_tg_id == data.from_tg_id,
            )
        )
        mutual = reverse_like is not None

        if mutual:
            user1_tg_id, user2_tg_id = canonical_match_pair(
                data.from_tg_id, data.to_tg_id
            )
            existing_match = await session.scalar(
                select(Match).where(
                    Match.user1_tg_id == user1_tg_id,
                    Match.user2_tg_id == user2_tg_id,
                )
            )
            if existing_match is None:
                session.add(Match(user1_tg_id=user1_tg_id, user2_tg_id=user2_tg_id))
                match_created = True

            matched_profile = (
                profile_payload(target) if target else {"tg_id": data.to_tg_id}
            )
            actor_profile = (
                profile_payload(actor) if actor else {"tg_id": data.from_tg_id}
            )

        await bump_activity(session, data.from_tg_id)
        await session.commit()

    await mark_seen(data.from_tg_id, data.to_tg_id)
    schedule_recalculate_user_rating(data.from_tg_id, data.to_tg_id)
    await publish_event(
        "interaction.like",
        {
            "from_tg_id": data.from_tg_id,
            "to_tg_id": data.to_tg_id,
            "mutual": mutual,
            "match_created": match_created,
        },
    )
    if match_created:
        u1, u2 = canonical_match_pair(data.from_tg_id, data.to_tg_id)
        await publish_event(
            "match.created", {"user1_tg_id": u1, "user2_tg_id": u2}
        )

    return {
        "status": "success",
        "mutual": mutual,
        "match_created": match_created,
        "matched_profile": matched_profile,
        "actor_profile": actor_profile,
    }


@router.post("/skip")
async def record_skip(data: InteractionRequest):
    async with AsyncSessionLocal() as session:
        existing_skip = await session.scalar(
            select(Skip).where(
                Skip.from_tg_id == data.from_tg_id,
                Skip.to_tg_id == data.to_tg_id,
            )
        )
        if existing_skip is None:
            session.add(Skip(from_tg_id=data.from_tg_id, to_tg_id=data.to_tg_id))
            await bump_activity(session, data.from_tg_id)
            await session.commit()

    await mark_seen(data.from_tg_id, data.to_tg_id)
    schedule_recalculate_user_rating(data.to_tg_id)
    await publish_event(
        "interaction.skip",
        {"from_tg_id": data.from_tg_id, "to_tg_id": data.to_tg_id},
    )
    return {"status": "success"}


@router.get("/get_match")
async def get_match(tg_id: int):
    async with AsyncSessionLocal() as session:
        me = await get_user_or_none(session, tg_id)
        if me is not None:
            await bump_activity(session, tg_id)
            await session.commit()

    if not me:
        return {"status": "error", "message": "Сначала создай анкету!"}
    if not me.gender or not (me.photo_id or (me.photos and len(me.photos) > 0)):
        return {"status": "error", "message": "Сначала заполни анкету полностью!"}

    profile = await pop_from_queue(tg_id)
    if not profile:
        profile = await build_queue(tg_id)

    if not profile:
        return {"status": "error", "message": "Пока никого нет 😔"}

    return {"status": "success", **profile}


@router.get("/likes/received/{tg_id}")
async def likes_received(tg_id: int):
    async with AsyncSessionLocal() as session:
        likes = (
            await session.execute(select(Like).where(Like.to_tg_id == tg_id))
        ).scalars().all()
        rating = await session.scalar(
            select(UserRating).where(UserRating.telegram_id == tg_id)
        )
    return {
        "count": len(likes),
        "from_ids": [like.from_tg_id for like in likes],
        "rating": {
            "primary_score": rating.primary_score if rating else 0.0,
            "behavioral_score": rating.behavioral_score if rating else 0.0,
            "referral_score": rating.referral_score if rating else 0.0,
            "activity_score": rating.activity_score if rating else 0.0,
            "combined_score": rating.combined_score if rating else 0.0,
        },
    }
