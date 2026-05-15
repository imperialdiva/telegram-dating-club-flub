"""RabbitMQ event bus.

Publishes domain events (like / skip / match / profile_updated / dialog_started)
to a topic exchange so any number of consumers can subscribe.
"""
import asyncio
import json
import logging
import os
from typing import Any, Optional

import aio_pika


logger = logging.getLogger(__name__)


RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://dating:dating@rabbitmq:5672/")
EXCHANGE_NAME = "dating.events"

_publisher_lock = asyncio.Lock()
_publisher_connection: Optional[aio_pika.RobustConnection] = None
_publisher_channel: Optional[aio_pika.abc.AbstractChannel] = None
_publisher_exchange: Optional[aio_pika.abc.AbstractExchange] = None


async def _ensure_publisher() -> aio_pika.abc.AbstractExchange:
    global _publisher_connection, _publisher_channel, _publisher_exchange
    async with _publisher_lock:
        if _publisher_exchange is None:
            _publisher_connection = await aio_pika.connect_robust(RABBITMQ_URL)
            _publisher_channel = await _publisher_connection.channel()
            _publisher_exchange = await _publisher_channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
        return _publisher_exchange


async def publish_event(routing_key: str, payload: dict[str, Any]) -> None:
    try:
        exchange = await _ensure_publisher()
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
        logger.info("event %s published: %s", routing_key, payload)
    except Exception as exc:
        logger.warning("Failed to publish event %s: %s", routing_key, exc)


async def close_publisher() -> None:
    global _publisher_connection, _publisher_channel, _publisher_exchange
    if _publisher_connection is not None:
        try:
            await _publisher_connection.close()
        except Exception:
            pass
    _publisher_connection = None
    _publisher_channel = None
    _publisher_exchange = None
