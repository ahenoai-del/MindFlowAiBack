import time
import logging
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from config.settings import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_seconds: int = 2):
        self.limit_seconds = limit_seconds
        self._last_time: dict[int, float] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        last = self._last_time.get(user_id, 0)

        if now - last < self.limit_seconds:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком быстро, подожди секунду", show_alert=False)
            elif isinstance(event, Message):
                await event.answer("⏳ Слишком быстро. Подожди немного.")
            return None

        self._last_time[user_id] = now
        return await handler(event, data)
