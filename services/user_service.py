import logging
from datetime import datetime, timedelta
from typing import Optional

from db import UserRepo
from db.models import User
from utils.cache import UserCache
from config.settings import settings

logger = logging.getLogger(__name__)

_cache = UserCache()


class UserService:
    @staticmethod
    async def get_or_create(user_id: int, username: Optional[str] = None) -> tuple[Optional[User], bool]:
        cached = _cache.get(user_id)
        if cached:
            return cached, False

        user, is_new = await UserRepo.create(user_id, username)
        if user and is_new:
            until = datetime.now() + timedelta(days=settings.PREMIUM_TRIAL_DAYS)
            await UserRepo.set_premium(user_id, until.strftime("%Y-%m-%d"))
            user.is_premium = True
            user.premium_until = until.strftime("%Y-%m-%d")

        if user:
            _cache.set(user_id, user, ttl=settings.USER_CACHE_TTL)
        return user, is_new

    @staticmethod
    async def get(user_id: int) -> Optional[User]:
        cached = _cache.get(user_id)
        if cached:
            return cached
        user = await UserRepo.get(user_id)
        if user:
            _cache.set(user_id, user, ttl=settings.USER_CACHE_TTL)
        return user

    @staticmethod
    async def is_premium(user_id: int) -> bool:
        user = await UserService.get(user_id)
        return user.is_premium_active if user else False

    @staticmethod
    async def update_activity(user_id: int) -> None:
        await UserRepo.update_last_activity(user_id)
        _cache.invalidate(user_id)

    @staticmethod
    async def update_settings(
        user_id: int,
        timezone: Optional[str] = None,
        morning_time: Optional[str] = None,
        evening_time: Optional[str] = None,
    ) -> None:
        await UserRepo.update_settings(user_id, timezone, morning_time, evening_time)
        _cache.invalidate(user_id)

    @staticmethod
    def invalidate_cache(user_id: int) -> None:
        _cache.invalidate(user_id)
