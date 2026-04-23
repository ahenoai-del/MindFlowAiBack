import logging
import asyncio
from typing import Optional

from aiogram import Bot
from config.settings import settings
from db import UserRepo

logger = logging.getLogger(__name__)


class BroadcastService:
    @staticmethod
    async def broadcast(
        bot: Bot,
        text: str,
        parse_mode: str = "HTML",
        batch_size: Optional[int] = None,
        delay: Optional[float] = None,
    ) -> dict:
        batch_size = batch_size or settings.BROADCAST_BATCH_SIZE
        delay = delay or settings.BROADCAST_DELAY_SECONDS

        user_ids = await UserRepo.get_all_ids()
        total = len(user_ids)
        success = 0
        failed = 0
        blocked = 0

        for i in range(0, total, batch_size):
            batch = user_ids[i : i + batch_size]
            for uid in batch:
                try:
                    await bot.send_message(uid, text, parse_mode=parse_mode)
                    success += 1
                except Exception as e:
                    err_msg = str(e).lower()
                    if "blocked" in err_msg or "deactivated" in err_msg:
                        blocked += 1
                    else:
                        failed += 1
                    logger.debug("Broadcast failed for %s: %s", uid, e)
            if i + batch_size < total and delay > 0:
                await asyncio.sleep(delay)

        result = {
            "total": total,
            "success": success,
            "failed": failed,
            "blocked": blocked,
        }
        logger.info("Broadcast completed: %s", result)
        return result
