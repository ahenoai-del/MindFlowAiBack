import logging
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from config.settings import settings

logger = logging.getLogger(__name__)


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id
        data["is_admin"] = user_id in settings.ADMIN_IDS
        return await handler(event, data)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS
