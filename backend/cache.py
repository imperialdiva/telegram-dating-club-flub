import json
from typing import Optional

import redis.asyncio as aioredis

from db import REDIS_URL


SEEN_KEY = "seen:{tg_id}"
QUEUE_KEY = "queue:{tg_id}"
SEEN_TTL = 7 * 24 * 3600
QUEUE_TTL = 30 * 60

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
