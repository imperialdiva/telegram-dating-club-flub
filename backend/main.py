import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, or_, select, text

from cache import (
    close_redis,
    delete_seen,
    delete_queue,
    get_seen_ids,
    init_redis,
    mark_seen,
    pop_from_queue,
    store_profiles_in_queue,
)
from db import AsyncSessionLocal, Base, engine
from models import Like, Match, Skip, User, UserRating
from rating import (
    compatibility_bonus,
    default_preferred_age_range,
    resolve_preferred_gender,
)
from tasks import recalculate_user_rating_async, schedule_recalculate_user_rating


async def _run_schema_migrations() -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_gender VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_city VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_age_min INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_age_max INTEGER",
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


def _profile_payload(user: User, combined_score: float | None = None, rank_score: float | None = None) -> dict:
    payload = {
        "tg_id": user.telegram_id,
        "name": user.first_name,
        "age": user.age,
        "city": user.city,
        "bio": user.bio,
        "photo_id": user.photo_id,
    }
    if combined_score is not None:
        payload["combined_score"] = combined_score
    if rank_score is not None:
        payload["rank_score"] = rank_score
    return payload


def _canonical_match_pair(first_tg_id: int, second_tg_id: int) -> tuple[int, int]:
    return tuple(sorted((int(first_tg_id), int(second_tg_id))))


async def _get_user_or_none(session, tg_id: int) -> Optional[User]:
    return await session.scalar(select(User).where(User.telegram_id == tg_id))


async def build_queue(tg_id: int) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        me = await _get_user_or_none(session, tg_id)
        if not me:
            return None

        seen_ids = await get_seen_ids(tg_id)
        preferred_gender = resolve_preferred_gender(me.gender, me.preferred_gender)

        stmt = (
            select(User, UserRating)
            .outerjoin(UserRating, UserRating.telegram_id == User.telegram_id)
            .where(User.telegram_id != tg_id, User.photo_id.isnot(None))
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

        scored_profiles = []
        for candidate, rating in candidate_rows:
            combined_score = float(rating.combined_score if rating else 0.0)
            personalized_score = combined_score + compatibility_bonus(me, candidate)
            scored_profiles.append(
                (
                    personalized_score,
                    _profile_payload(
                        candidate,
                        combined_score=combined_score,
                        rank_score=personalized_score,
                    ),
                )
            )

        scored_profiles.sort(key=lambda item: item[0], reverse=True)
        queue_payload = [payload for _, payload in scored_profiles]
        await store_profiles_in_queue(tg_id, queue_payload)

    return await pop_from_queue(tg_id)


app = FastAPI(title="Club Flub Backend")


@app.on_event("startup")
async def startup():
    logging.basicConfig(level=logging.INFO)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_schema_migrations()
    await init_redis()


@app.on_event("shutdown")
async def shutdown():
    await close_redis()


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.post("/register")
async def register_user(
    tg_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
):
    async with AsyncSessionLocal() as session:
        existing = await _get_user_or_none(session, tg_id)
        if existing:
            return {"status": "already_exists"}
        try:
            session.add(User(telegram_id=tg_id, username=username, first_name=first_name))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            return {"status": "error", "message": str(exc)}

    schedule_recalculate_user_rating(tg_id)
    return {"status": "success"}


class ProfileUpdate(BaseModel):
    tg_id: int
    name: str
    age: int
    gender: str
    photo_id: str
    city: Optional[str] = None
    bio: Optional[str] = None
    preferred_gender: Optional[str] = None
    preferred_city: Optional[str] = None
    preferred_age_min: Optional[int] = None
    preferred_age_max: Optional[int] = None


@app.post("/update_profile")
async def update_profile(data: ProfileUpdate):
    preferred_age_min = data.preferred_age_min
    preferred_age_max = data.preferred_age_max
    if preferred_age_min is None or preferred_age_max is None:
        preferred_age_min, preferred_age_max = default_preferred_age_range(data.age)

    async with AsyncSessionLocal() as session:
        user = await _get_user_or_none(session, data.tg_id)
        if not user:
            return {"status": "error", "message": "User not found"}

        user.first_name = data.name
        user.age = data.age
        user.gender = data.gender
        user.photo_id = data.photo_id
        user.city = data.city
        user.bio = data.bio
        user.preferred_gender = data.preferred_gender or resolve_preferred_gender(
            data.gender,
            None,
        )
        user.preferred_city = data.preferred_city or data.city
        user.preferred_age_min = preferred_age_min
        user.preferred_age_max = preferred_age_max
        await session.commit()

    await delete_queue(data.tg_id)
    schedule_recalculate_user_rating(data.tg_id)
    return {"status": "success"}


@app.get("/profile/{tg_id}")
async def get_profile(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await _get_user_or_none(session, tg_id)
        rating = await session.scalar(
            select(UserRating).where(UserRating.telegram_id == tg_id)
        )
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "tg_id": user.telegram_id,
        "name": user.first_name,
        "username": user.username,
        "age": user.age,
        "city": user.city,
        "bio": user.bio,
        "gender": user.gender,
        "photo_id": user.photo_id,
        "preferred_gender": user.preferred_gender,
        "preferred_city": user.preferred_city,
        "preferred_age_min": user.preferred_age_min,
        "preferred_age_max": user.preferred_age_max,
        "created_at": user.created_at,
        "rating": {
            "primary_score": rating.primary_score if rating else 0.0,
            "behavioral_score": rating.behavioral_score if rating else 0.0,
            "combined_score": rating.combined_score if rating else 0.0,
        },
    }


@app.delete("/profile/{tg_id}")
async def delete_profile(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await _get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="Profile not found")

        await session.execute(
            delete(Like).where(
                or_(Like.from_tg_id == tg_id, Like.to_tg_id == tg_id)
            )
        )
        await session.execute(
            delete(Skip).where(
                or_(Skip.from_tg_id == tg_id, Skip.to_tg_id == tg_id)
            )
        )
        await session.execute(
            delete(Match).where(
                or_(Match.user1_tg_id == tg_id, Match.user2_tg_id == tg_id)
            )
        )
        await session.execute(delete(UserRating).where(UserRating.telegram_id == tg_id))
        await session.delete(user)
        await session.commit()

    await delete_queue(tg_id)
    await delete_seen(tg_id)
    return {"status": "success"}


class InteractionRequest(BaseModel):
    from_tg_id: int
    to_tg_id: int


@app.post("/like")
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
            return {"status": "already_liked", "mutual": False, "match_created": False}

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

        actor = await _get_user_or_none(session, data.from_tg_id)
        target = await _get_user_or_none(session, data.to_tg_id)

        reverse_like = await session.scalar(
            select(Like).where(
                Like.from_tg_id == data.to_tg_id,
                Like.to_tg_id == data.from_tg_id,
            )
        )
        mutual = reverse_like is not None

        if mutual:
            user1_tg_id, user2_tg_id = _canonical_match_pair(
                data.from_tg_id,
                data.to_tg_id,
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

            matched_profile = _profile_payload(target) if target else {"tg_id": data.to_tg_id}
            actor_profile = _profile_payload(actor) if actor else {"tg_id": data.from_tg_id}

        await session.commit()

    await mark_seen(data.from_tg_id, data.to_tg_id)
    schedule_recalculate_user_rating(data.from_tg_id, data.to_tg_id)

    return {
        "status": "success",
        "mutual": mutual,
        "match_created": match_created,
        "matched_profile": matched_profile,
        "actor_profile": actor_profile,
    }


@app.post("/skip")
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
            await session.commit()

    await mark_seen(data.from_tg_id, data.to_tg_id)
    schedule_recalculate_user_rating(data.to_tg_id)
    return {"status": "success"}


@app.get("/get_match")
async def get_match(tg_id: int):
    async with AsyncSessionLocal() as session:
        me = await _get_user_or_none(session, tg_id)

    if not me:
        return {"status": "error", "message": "Сначала создай анкету!"}
    if not me.gender or not me.photo_id:
        return {"status": "error", "message": "Сначала заполни анкету полностью!"}

    profile = await pop_from_queue(tg_id)
    if not profile:
        profile = await build_queue(tg_id)

    if not profile:
        return {"status": "error", "message": "Пока никого нет 😔"}

    return {"status": "success", **profile}


@app.get("/likes/received/{tg_id}")
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
            "combined_score": rating.combined_score if rating else 0.0,
        },
    }
