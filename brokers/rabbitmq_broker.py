
import asyncio
import json
import os
import time

import aio_pika

from config import BROKER


class RabbitMQBroker:
    name = "RabbitMQ"

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(BROKER.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1000)
        await self._channel.declare_queue(
            BROKER.rabbitmq_queue,
            durable=True,
            arguments={"x-queue-type": "classic"},
        )

    async def purge(self) -> None:
        if self._channel:
            queue = await self._channel.declare_queue(
                BROKER.rabbitmq_queue,
                durable=True,
                passive=True,
            )
            await queue.purge()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    async def produce(
        self,
        msg_size: int,
        rate: int,
        duration: float,
        sent_counter: list,
        stop_event: asyncio.Event,
    ) -> None:
        payload_data = os.urandom(max(0, msg_size - 64))
        interval = 1.0 / rate
        deadline = time.monotonic() + duration

        while not stop_event.is_set() and time.monotonic() < deadline:
            loop_start = time.monotonic()

            envelope = {
                "t": time.time(),
                "d": payload_data.hex(),
            }
            body = json.dumps(envelope).encode()

            await self._channel.default_exchange.publish(
                aio_pika.Message(
                    body=body,
                    delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
                ),
                routing_key=BROKER.rabbitmq_queue,
            )
            sent_counter[0] += 1

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
        queue = await self._channel.declare_queue(
            BROKER.rabbitmq_queue,
            durable=True,
            passive=True,
        )

        async with queue.iterator() as q_iter:
            async for message in q_iter:
                async with message.process():
                    now = time.time()
                    try:
                        envelope = json.loads(message.body)
                        latency_ms = (now - envelope["t"]) * 1000
                        latencies.append(latency_ms)
                    except Exception:
                        pass
                    recv_counter[0] += 1

                if stop_event.is_set():
                    break
