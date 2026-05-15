"""Простой in-memory antiflood: один апдейт от юзера в N секунд."""
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.4):
        super().__init__()
        self._rate = rate
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            previous = self._last.get(user.id, 0.0)
            if now - previous < self._rate:
                return None
            self._last[user.id] = now
        return await handler(event, data)
