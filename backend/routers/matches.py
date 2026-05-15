from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select

from db import AsyncSessionLocal
from events import publish_event
from models import Match, User
from services.profiles import (
    bump_activity,
    canonical_match_pair,
    profile_payload,
)
from tasks import schedule_recalculate_user_rating


router = APIRouter()


class DialogStartRequest(BaseModel):
    from_tg_id: int
    to_tg_id: int


@router.get("/matches/{tg_id}")
async def list_matches(tg_id: int):
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Match).where(
                    or_(Match.user1_tg_id == tg_id, Match.user2_tg_id == tg_id)
                ).order_by(Match.created_at.desc())
            )
        ).scalars().all()

        if not rows:
            return {"matches": []}

        partner_ids = [
            m.user2_tg_id if m.user1_tg_id == tg_id else m.user1_tg_id for m in rows
        ]
        users = (
            await session.execute(select(User).where(User.telegram_id.in_(partner_ids)))
        ).scalars().all()
        users_by_id = {u.telegram_id: u for u in users}

    out = []
    for match in rows:
        partner_id = (
            match.user2_tg_id if match.user1_tg_id == tg_id else match.user1_tg_id
        )
        partner = users_by_id.get(partner_id)
        out.append(
            {
                "match_id": str(match.id),
                "partner_tg_id": partner_id,
                "partner": profile_payload(partner) if partner else None,
                "dialog_started": bool(match.dialog_started),
                "created_at": match.created_at.isoformat() if match.created_at else None,
            }
        )
    return {"matches": out}


@router.post("/matches/dialog-started")
async def mark_dialog_started(data: DialogStartRequest):
    user1_tg_id, user2_tg_id = canonical_match_pair(data.from_tg_id, data.to_tg_id)

    async with AsyncSessionLocal() as session:
        match = await session.scalar(
            select(Match).where(
                Match.user1_tg_id == user1_tg_id,
                Match.user2_tg_id == user2_tg_id,
            )
        )
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")

        if not match.dialog_started:
            match.dialog_started = True
            match.dialog_started_by = int(data.from_tg_id)
        await bump_activity(session, data.from_tg_id)
        await session.commit()

    schedule_recalculate_user_rating(data.from_tg_id, data.to_tg_id)
    await publish_event(
        "match.dialog_started",
        {"from_tg_id": data.from_tg_id, "to_tg_id": data.to_tg_id},
    )
    return {"status": "success"}
