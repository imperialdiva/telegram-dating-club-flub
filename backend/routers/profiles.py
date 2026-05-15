from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select

from cache import (
    apply_boost,
    daily_claim_seconds_left,
    delete_queue,
    delete_seen,
    get_boost_info,
)
from config import (
    MAX_INTERESTS,
    ONBOARDING_BOOST_MULT,
    ONBOARDING_BOOST_TTL,
    PROFILE_COMPLETE_BOOST_MULT,
    PROFILE_COMPLETE_BOOST_TTL,
    REFERRER_BOOST_MULT,
    REFERRER_BOOST_TTL,
)
from db import AsyncSessionLocal
from events import publish_event
from models import ActivityHourly, Like, Match, Skip, User, UserRating
from rating import default_preferred_age_range, resolve_preferred_gender
from services.profiles import (
    bump_activity,
    get_user_or_none,
    is_profile_complete,
    photo_urls,
)
from storage import delete_photo
from tasks import schedule_recalculate_user_rating


router = APIRouter()


class ProfileUpdate(BaseModel):
    tg_id: int
    name: str
    age: int
    gender: str
    photo_id: Optional[str] = None
    city: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[list[str]] = None
    preferred_gender: Optional[str] = None
    preferred_city: Optional[str] = None
    preferred_age_min: Optional[int] = None
    preferred_age_max: Optional[int] = None


class PreferencesUpdate(BaseModel):
    tg_id: int
    preferred_gender: Optional[str] = None
    preferred_city: Optional[str] = None
    preferred_age_min: Optional[int] = Field(default=None, ge=18, le=120)
    preferred_age_max: Optional[int] = Field(default=None, ge=18, le=120)


# ---------------------------------------------------------------------------
@router.post("/register")
async def register_user(
    tg_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    referrer_tg_id: Optional[int] = None,
):
    async with AsyncSessionLocal() as session:
        existing = await get_user_or_none(session, tg_id)
        if existing:
            await bump_activity(session, tg_id)
            await session.commit()
            return {"status": "already_exists"}

        ref_id: Optional[int] = None
        if referrer_tg_id and referrer_tg_id != tg_id:
            referrer = await get_user_or_none(session, int(referrer_tg_id))
            if referrer:
                ref_id = int(referrer_tg_id)
                referrer.referrals_count = int(referrer.referrals_count or 0) + 1

        try:
            session.add(
                User(
                    telegram_id=tg_id,
                    username=username,
                    first_name=first_name,
                    referrer_tg_id=ref_id,
                )
            )
            await bump_activity(session, tg_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            return {"status": "error", "message": str(exc)}

    schedule_recalculate_user_rating(tg_id)
    await apply_boost(tg_id, ONBOARDING_BOOST_MULT, ONBOARDING_BOOST_TTL)
    if ref_id is not None:
        schedule_recalculate_user_rating(ref_id)
        await apply_boost(ref_id, REFERRER_BOOST_MULT, REFERRER_BOOST_TTL)
    await publish_event("user.registered", {"tg_id": tg_id, "referrer_tg_id": ref_id})
    return {"status": "success", "referrer_applied": ref_id is not None}


@router.post("/update_profile")
async def update_profile(data: ProfileUpdate):
    preferred_age_min = data.preferred_age_min
    preferred_age_max = data.preferred_age_max
    if preferred_age_min is None or preferred_age_max is None:
        preferred_age_min, preferred_age_max = default_preferred_age_range(data.age)

    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, data.tg_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        was_complete = is_profile_complete(user)

        user.first_name = data.name
        user.age = data.age
        user.gender = data.gender
        if data.photo_id:
            user.photo_id = data.photo_id
        user.city = data.city
        user.bio = data.bio
        if data.interests is not None:
            user.interests = [
                str(item).strip()
                for item in data.interests
                if str(item).strip()
            ][:MAX_INTERESTS]
        user.preferred_gender = data.preferred_gender or resolve_preferred_gender(
            data.gender, None
        )
        user.preferred_city = data.preferred_city or data.city
        user.preferred_age_min = preferred_age_min
        user.preferred_age_max = preferred_age_max
        await bump_activity(session, data.tg_id)
        await session.commit()
        became_complete = (not was_complete) and is_profile_complete(user)

    await delete_queue(data.tg_id)
    schedule_recalculate_user_rating(data.tg_id)
    if became_complete:
        await apply_boost(
            data.tg_id, PROFILE_COMPLETE_BOOST_MULT, PROFILE_COMPLETE_BOOST_TTL
        )
    await publish_event(
        "profile.updated",
        {"tg_id": data.tg_id, "completed": became_complete},
    )
    return {"status": "success", "boost_granted": became_complete}


@router.patch("/preferences")
async def update_preferences(data: PreferencesUpdate):
    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, data.tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if data.preferred_gender is not None:
            user.preferred_gender = data.preferred_gender or None
        if data.preferred_city is not None:
            user.preferred_city = data.preferred_city or None
        if data.preferred_age_min is not None:
            user.preferred_age_min = int(data.preferred_age_min)
        if data.preferred_age_max is not None:
            user.preferred_age_max = int(data.preferred_age_max)

        if (
            user.preferred_age_min is not None
            and user.preferred_age_max is not None
            and user.preferred_age_min > user.preferred_age_max
        ):
            user.preferred_age_min, user.preferred_age_max = (
                user.preferred_age_max,
                user.preferred_age_min,
            )
        await bump_activity(session, data.tg_id)
        await session.commit()

    await delete_queue(data.tg_id)
    schedule_recalculate_user_rating(data.tg_id)
    await publish_event("profile.preferences_updated", {"tg_id": data.tg_id})
    return {"status": "success"}


@router.get("/profile/{tg_id}")
async def get_profile(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="Profile not found")
        rating = await session.scalar(
            select(UserRating).where(UserRating.telegram_id == tg_id)
        )
        await bump_activity(session, tg_id)
        await session.commit()

    boost_info = await get_boost_info(tg_id)
    daily_left = await daily_claim_seconds_left(tg_id)
    return {
        "tg_id": user.telegram_id,
        "name": user.first_name,
        "username": user.username,
        "age": user.age,
        "city": user.city,
        "bio": user.bio,
        "gender": user.gender,
        "photo_id": user.photo_id,
        "photos": list(user.photos or []),
        "photo_urls": photo_urls(user),
        "interests": list(user.interests or []),
        "preferred_gender": user.preferred_gender,
        "preferred_city": user.preferred_city,
        "preferred_age_min": user.preferred_age_min,
        "preferred_age_max": user.preferred_age_max,
        "referrer_tg_id": user.referrer_tg_id,
        "referrals_count": int(user.referrals_count or 0),
        "created_at": user.created_at,
        "rating": {
            "primary_score": rating.primary_score if rating else 0.0,
            "behavioral_score": rating.behavioral_score if rating else 0.0,
            "referral_score": rating.referral_score if rating else 0.0,
            "activity_score": rating.activity_score if rating else 0.0,
            "combined_score": rating.combined_score if rating else 0.0,
        },
        "boost": boost_info,
        "daily_boost_cooldown": daily_left,
    }


@router.delete("/profile/{tg_id}")
async def delete_profile(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="Profile not found")

        photo_keys = list(user.photos or [])

        await session.execute(
            delete(Like).where(or_(Like.from_tg_id == tg_id, Like.to_tg_id == tg_id))
        )
        await session.execute(
            delete(Skip).where(or_(Skip.from_tg_id == tg_id, Skip.to_tg_id == tg_id))
        )
        await session.execute(
            delete(Match).where(
                or_(Match.user1_tg_id == tg_id, Match.user2_tg_id == tg_id)
            )
        )
        await session.execute(
            delete(ActivityHourly).where(ActivityHourly.telegram_id == tg_id)
        )
        await session.execute(delete(UserRating).where(UserRating.telegram_id == tg_id))
        await session.delete(user)
        await session.commit()

    for key in photo_keys:
        delete_photo(key)

    await delete_queue(tg_id)
    await delete_seen(tg_id)
    await publish_event("profile.deleted", {"tg_id": tg_id})
    return {"status": "success"}
