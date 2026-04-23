import logging
import traceback
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramAPIError as e:
            logger.warning("Telegram API error: %s", e)
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Произошла ошибка", show_alert=False)
                except Exception:
                    pass
        except Exception as e:
            logger.error(
                "Unhandled error in handler: %s\n%s",
                e,
                traceback.format_exc(),
            )
            try:
                if isinstance(event, Message):
                    await event.answer("❌ Произошла непредвиденная ошибка. Попробуй позже.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Произошла ошибка", show_alert=True)
            except Exception:
                pass
