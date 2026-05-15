"""RabbitMQ consumer.

Слушает события из exchange `dating.events` и вызывает Celery-задачи
пересчёта рейтинга. Это даёт асинхронную потоковую обработку
взаимодействий с анкетами (лайки/пропуски/мэтчи/диалоги).
"""
import asyncio
import json
import logging
import os
import signal

import aio_pika

from tasks import schedule_recalculate_user_rating


RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://dating:dating@rabbitmq:5672/")
EXCHANGE_NAME = "dating.events"
QUEUE_NAME = "dating.events.rating-engine"

logger = logging.getLogger(__name__)


def _affected_ids(routing_key: str, payload: dict) -> set[int]:
    ids: set[int] = set()
    for field in ("from_tg_id", "to_tg_id", "tg_id", "user1_tg_id", "user2_tg_id"):
        value = payload.get(field)
        if value is not None:
            try:
                ids.add(int(value))
            except (TypeError, ValueError):
                continue
    return ids


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process(requeue=False):
        try:
            payload = json.loads(message.body.decode("utf-8"))
        except Exception:
            logger.exception("Bad event payload")
            return

        ids = _affected_ids(message.routing_key, payload)
        logger.info(
            "consume %s -> recalculate %s", message.routing_key, sorted(ids)
        )
        if ids:
            schedule_recalculate_user_rating(*ids)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting RabbitMQ consumer for %s", EXCHANGE_NAME)

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=32)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key="#")

    stop_event = asyncio.Event()

    def _signal_handler(*_):
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    await queue.consume(handle_message)

    await stop_event.wait()
    await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
