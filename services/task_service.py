import logging
from typing import Optional

from db import TaskRepo, GamificationRepo, ACHIEVEMENTS
from db.models import Task, Gamification
from ai.parser import parse_task_text

logger = logging.getLogger(__name__)


class TaskService:
    @staticmethod
    async def create_from_text(user_id: int, text: str) -> Optional[Task]:
        parsed = await parse_task_text(text)
        task = await TaskRepo.create(
            user_id=user_id,
            title=parsed.get("title", text),
            description=parsed.get("description"),
            category=parsed.get("category", "general"),
            priority=parsed.get("priority", 2),
            deadline=parsed.get("deadline"),
        )
        if task:
            await GamificationRepo.add_xp(user_id, 10)

            g = await GamificationRepo.get_or_create(user_id)
            if g.total_completed == 0:
                if await GamificationRepo.add_achievement(user_id, "first_task"):
                    from db.models import ACHIEVEMENTS
                    await GamificationRepo.add_xp(user_id, ACHIEVEMENTS["first_task"]["xp"])

            from db.database import get_pool
            pool = get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = $1", user_id
                )
                task_count = row["cnt"] if row else 0
            if task_count >= 10:
                if await GamificationRepo.add_achievement(user_id, "ai_user"):
                    from db.models import ACHIEVEMENTS
                    await GamificationRepo.add_xp(user_id, ACHIEVEMENTS["ai_user"]["xp"])
        return task

    @staticmethod
    async def complete_task(user_id: int, task_id: int) -> Optional[dict]:
        task = await TaskRepo.get(task_id)
        if not task or task.user_id != user_id:
            return None

        completed = await TaskRepo.complete(task_id)
        if not completed:
            return None

        xp_earned = {1: 20, 2: 10, 3: 5}.get(task.priority, 10)
        g, new_level, leveled_up = await GamificationRepo.add_xp(user_id, xp_earned)
        streak = await GamificationRepo.update_streak(user_id)

        achievements: list[str] = []
        if g.total_completed == 0:
            if await GamificationRepo.add_achievement(user_id, "first_complete"):
                achievements.append("first_complete")

        if streak >= 3 and streak % 3 == 0:
            ach_key = f"streak_{streak}" if streak <= 30 else "streak_7"
            if ach_key in ACHIEVEMENTS and await GamificationRepo.add_achievement(user_id, ach_key):
                achievements.append(ach_key)

        for milestone in [10, 50, 100]:
            if g.total_completed + 1 == milestone:
                ach_key = f"tasks_{milestone}"
                if ach_key in ACHIEVEMENTS and await GamificationRepo.add_achievement(user_id, ach_key):
                    achievements.append(ach_key)

        from datetime import datetime
        hour = datetime.now().hour
        if hour < 9 and await GamificationRepo.add_achievement(user_id, "early_bird"):
            achievements.append("early_bird")
        elif hour >= 23 and await GamificationRepo.add_achievement(user_id, "night_owl"):
            achievements.append("night_owl")

        return {
            "task": completed,
            "xp_earned": xp_earned,
            "new_level": new_level,
            "leveled_up": leveled_up,
            "streak": streak,
            "achievements": achievements,
        }
