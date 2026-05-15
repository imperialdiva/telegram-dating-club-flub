import json
from typing import Iterable, Optional

import redis.asyncio as aioredis

from db import REDIS_URL


SEEN_KEY = "seen:{tg_id}"
QUEUE_KEY = "queue:{tg_id}"
BOOST_KEY = "boost:{tg_id}"
DAILY_CLAIM_KEY = "boost:claim:{tg_id}"
SEEN_TTL = 7 * 24 * 3600
QUEUE_TTL = 30 * 60
DAILY_CLAIM_TTL = 24 * 3600

redis_client: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)


def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


# ---------------------------------------------------------------------------
# seen / queue
# ---------------------------------------------------------------------------
async def get_seen_ids(tg_id: int) -> set[int]:
    members = await get_redis().smembers(SEEN_KEY.format(tg_id=tg_id))
    return {int(member) for member in members}


async def delete_queue(tg_id: int) -> None:
    await get_redis().delete(QUEUE_KEY.format(tg_id=tg_id))


async def delete_seen(tg_id: int) -> None:
    await get_redis().delete(SEEN_KEY.format(tg_id=tg_id))


async def mark_seen(from_tg_id: int, to_tg_id: int) -> None:
    redis = get_redis()
    key = SEEN_KEY.format(tg_id=from_tg_id)
    await redis.sadd(key, to_tg_id)
    await redis.expire(key, SEEN_TTL)
    await delete_queue(from_tg_id)


async def pop_from_queue(tg_id: int) -> Optional[dict]:
    raw = await get_redis().lpop(QUEUE_KEY.format(tg_id=tg_id))
    return json.loads(raw) if raw else None


async def store_profiles_in_queue(tg_id: int, profiles: list[dict]) -> None:
    redis = get_redis()
    queue_key = QUEUE_KEY.format(tg_id=tg_id)
    pipe = redis.pipeline()
    pipe.delete(queue_key)
    for profile in profiles:
        pipe.rpush(queue_key, json.dumps(profile, ensure_ascii=False))
    if profiles:
        pipe.expire(queue_key, QUEUE_TTL)
    await pipe.execute()


# ---------------------------------------------------------------------------
# boosts
# ---------------------------------------------------------------------------
async def apply_boost(tg_id: int, multiplier: float, ttl_seconds: int) -> None:
    """Установить бустер. Если уже есть — оставляет максимум по силе/длительности."""
    redis = get_redis()
    key = BOOST_KEY.format(tg_id=tg_id)
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    raw, ttl = await pipe.execute()
    current_mult = float(raw) if raw else 1.0
    current_ttl = int(ttl) if ttl and ttl > 0 else 0
    new_mult = max(current_mult, float(multiplier))
    new_ttl = max(current_ttl, int(ttl_seconds))
    await redis.set(key, f"{new_mult:.4f}", ex=new_ttl)


async def clear_boost(tg_id: int) -> None:
    await get_redis().delete(BOOST_KEY.format(tg_id=tg_id))


async def get_boost(tg_id: int) -> float:
    raw = await get_redis().get(BOOST_KEY.format(tg_id=tg_id))
    return float(raw) if raw else 1.0


async def get_boost_info(tg_id: int) -> dict:
    redis = get_redis()
    key = BOOST_KEY.format(tg_id=tg_id)
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.ttl(key)
    raw, ttl = await pipe.execute()
    return {
        "multiplier": float(raw) if raw else 1.0,
        "ttl_seconds": int(ttl) if ttl and ttl > 0 else 0,
        "active": bool(raw),
    }


async def get_boosts_bulk(tg_ids: Iterable[int]) -> dict[int, float]:
    ids = list(tg_ids)
    if not ids:
        return {}
    keys = [BOOST_KEY.format(tg_id=tg_id) for tg_id in ids]
    raws = await get_redis().mget(keys)
    return {
        tg_id: (float(raw) if raw else 1.0)
        for tg_id, raw in zip(ids, raws)
    }


async def try_claim_daily_boost(tg_id: int) -> bool:
    """Пытаемся залочить ежедневный буст. True если успешно (раз в 24ч)."""
    key = DAILY_CLAIM_KEY.format(tg_id=tg_id)
    return bool(await get_redis().set(key, "1", ex=DAILY_CLAIM_TTL, nx=True))


async def daily_claim_seconds_left(tg_id: int) -> int:
    ttl = await get_redis().ttl(DAILY_CLAIM_KEY.format(tg_id=tg_id))
    return int(ttl) if ttl and ttl > 0 else 0
