
import asyncio
import json
import os
import time

import redis.asyncio as aioredis

from config import BROKER


class RedisBroker:
    name = "Redis"

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(BROKER.redis_url, decode_responses=False)
        try:
            await self._client.xgroup_create(
                BROKER.redis_stream,
                BROKER.redis_group,
                id="0",
                mkstream=True,
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def purge(self) -> None:
        if self._client:
            await self._client.delete(BROKER.redis_stream)
            try:
                await self._client.xgroup_create(
                    BROKER.redis_stream,
                    BROKER.redis_group,
                    id="0",
                    mkstream=True,
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def produce(
        self,
        msg_size: int,
        rate: int,
        duration: float,
        sent_counter: list,
        stop_event: asyncio.Event,
        lost_counter: list | None = None,
    ) -> None:
        payload_data = os.urandom(max(0, msg_size - 64))
        interval = 1.0 / rate
        deadline = time.monotonic() + duration
        _MAXLEN = 50_000

        while not stop_event.is_set() and time.monotonic() < deadline:
            loop_start = time.monotonic()

            envelope = {
                b"t": str(time.time()).encode(),
                b"d": payload_data,
            }

            try:
                await self._client.xadd(
                    BROKER.redis_stream,
                    envelope,
                    maxlen=_MAXLEN,
                    approximate=True,
                )
                sent_counter[0] += 1
            except aioredis.OutOfMemoryError:
                if lost_counter is not None:
                    lost_counter[0] += 1
                await asyncio.sleep(0.01)
                continue

            elapsed = time.monotonic() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        stop_event.set()

    async def consume(
        self,
        latencies: list,
        recv_counter: list,
        stop_event: asyncio.Event,
    ) -> None:
        while True:
            entries = await self._client.xreadgroup(
                groupname=BROKER.redis_group,
                consumername=BROKER.redis_consumer,
                streams={BROKER.redis_stream: ">"},
                count=500,
                block=200,
            )

            if entries:
                now = time.time()
                ids_to_ack = []
                for _stream, messages in entries:
                    for msg_id, fields in messages:
                        try:
                            send_time = float(fields[b"t"])
                            latency_ms = (now - send_time) * 1000
                            latencies.append(latency_ms)
                        except Exception:
                            pass
                        recv_counter[0] += 1
                        ids_to_ack.append(msg_id)

                if ids_to_ack:
                    await self._client.xack(
                        BROKER.redis_stream, BROKER.redis_group, *ids_to_ack
                    )

            if stop_event.is_set() and not entries:
                break
