import logging
from datetime import datetime, timedelta
from typing import Optional

from db import UserRepo
from services.user_service import UserService

logger = logging.getLogger(__name__)


class PremiumService:
    @staticmethod
    async def activate(user_id: int, days: int) -> str:
        until = datetime.now() + timedelta(days=days)
        until_str = until.strftime("%Y-%m-%d")
        await UserRepo.set_premium(user_id, until_str)
        UserService.invalidate_cache(user_id)
        logger.info("Premium activated for user %s until %s", user_id, until_str)
        return until_str

    @staticmethod
    async def revoke(user_id: int) -> None:
        await UserRepo.revoke_premium(user_id)
        UserService.invalidate_cache(user_id)
        logger.info("Premium revoked for user %s", user_id)

    @staticmethod
    async def check_and_expire(user_id: int) -> bool:
        user = await UserService.get(user_id)
        if not user or not user.is_premium:
            return False
        if not user.is_premium_active:
            await PremiumService.revoke(user_id)
            return True
        return False

    @staticmethod
    async def get_status(user_id: int) -> dict:
        user = await UserService.get(user_id)
        if not user:
            return {"active": False, "until": None}
        return {
            "active": user.is_premium_active,
            "until": user.premium_until,
        }
