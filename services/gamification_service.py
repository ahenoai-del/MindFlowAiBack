import logging
from typing import Optional
from db import GamificationRepo, ACHIEVEMENTS
from db.models import Gamification, get_level, xp_to_next_level

logger = logging.getLogger(__name__)


class GamificationService:
    @staticmethod
    async def get_profile(user_id: int) -> Optional[Gamification]:
        return await GamificationRepo.get_or_create(user_id)

    @staticmethod
    async def add_xp(user_id: int, xp: int) -> tuple[Gamification, int, bool]:
        return await GamificationRepo.add_xp(user_id, xp)

    @staticmethod
    async def get_achievements(user_id: int) -> list:
        return await GamificationRepo.get_achievements(user_id)

    @staticmethod
    def format_profile(g: Gamification) -> str:
        xp_next = xp_to_next_level(g.xp)
        return (
            f"🏆 <b>Уровень {g.level}</b>\n"
            f"💰 XP: {g.xp}\n"
            f"📈 До следующего: {xp_next} XP\n\n"
            f"🔥 Серия: {g.streak} дней\n"
            f"⚡ Лучшая серия: {g.max_streak} дней\n"
            f"✅ Всего выполнено: {g.total_completed}"
        )

    @staticmethod
    def format_achievements(unlocked: list) -> str:
        text = "🏅 <b>Достижения</b>\n\n"
        unlocked_count = 0
        for ach_id, ach in ACHIEVEMENTS.items():
            if ach_id in unlocked:
                text += f"✅ {ach['icon']} {ach['name']}\n   <i>{ach['description']}</i>\n"
                unlocked_count += 1
            else:
                text += f"⬜ {ach['icon']} {ach['name']}\n   <i>{ach['description']}</i>\n"
        text += f"\n🔓 Разблокировано: {unlocked_count}/{len(ACHIEVEMENTS)}"
        return text
