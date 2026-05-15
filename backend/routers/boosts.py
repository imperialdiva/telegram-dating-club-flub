from fastapi import APIRouter, HTTPException

from cache import (
    apply_boost,
    daily_claim_seconds_left,
    delete_queue,
    get_boost_info,
    try_claim_daily_boost,
)
from config import DAILY_BOOST_MULT, DAILY_BOOST_TTL
from db import AsyncSessionLocal
from events import publish_event
from services.profiles import get_user_or_none


router = APIRouter()


@router.get("/boost/{tg_id}")
async def get_user_boost(tg_id: int):
    info = await get_boost_info(tg_id)
    info["daily_boost_cooldown"] = await daily_claim_seconds_left(tg_id)
    return info


@router.post("/boost/{tg_id}/claim-daily")
async def claim_daily_boost(tg_id: int):
    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    if not await try_claim_daily_boost(tg_id):
        info = await get_boost_info(tg_id)
        info["daily_boost_cooldown"] = await daily_claim_seconds_left(tg_id)
        return {"status": "already_claimed", **info}

    await apply_boost(tg_id, DAILY_BOOST_MULT, DAILY_BOOST_TTL)
    await delete_queue(tg_id)
    info = await get_boost_info(tg_id)
    info["daily_boost_cooldown"] = await daily_claim_seconds_left(tg_id)
    await publish_event(
        "boost.claimed",
        {
            "tg_id": tg_id,
            "kind": "daily",
            "multiplier": DAILY_BOOST_MULT,
            "ttl_seconds": DAILY_BOOST_TTL,
        },
    )
    return {"status": "success", **info}
