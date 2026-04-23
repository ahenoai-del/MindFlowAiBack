import logging
from datetime import datetime, timedelta
from typing import Optional

from db import UserRepo, TaskRepo, GamificationRepo
from db.database import get_pool

logger = logging.getLogger(__name__)


class AnalyticsService:
    @staticmethod
    async def get_bot_stats() -> dict:
        pool = get_pool()
        total_users = await UserRepo.count()
        premium_users = await UserRepo.count_premium()
        active_24h = await UserRepo.count_active_24h()
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        new_week = await UserRepo.count_new_since(week_ago)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        new_today = await UserRepo.count_new_since(today_start)

        total_tasks = 0
        completed_tasks = 0
        today_active = 0
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM tasks")
                total_tasks = row["cnt"] if row else 0
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed'"
                )
                completed_tasks = row["cnt"] if row else 0
                row = await conn.fetchrow(
                    "SELECT COUNT(DISTINCT user_id) as cnt FROM tasks WHERE created_at::date = CURRENT_DATE"
                )
                today_active = row["cnt"] if row else 0
        except Exception as e:
            logger.error("Error fetching task stats: %s", e)

        return {
            "total_users": total_users,
            "premium_users": premium_users,
            "active_24h": active_24h,
            "new_today": new_today,
            "new_week": new_week,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "today_active": today_active,
        }

    @staticmethod
    async def get_user_info(user_id: int) -> Optional[dict]:
        user = await UserRepo.get(user_id)
        if not user:
            return None
        g = await GamificationRepo.get_or_create(user_id)
        pool = get_pool()
        tasks_count = 0
        completed_count = 0
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = $1", user_id
                )
                tasks_count = row["cnt"] if row else 0
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM tasks WHERE user_id = $1 AND status = 'completed'",
                    user_id,
                )
                completed_count = row["cnt"] if row else 0
        except Exception as e:
            logger.error("Error fetching user task counts: %s", e)

        return {
            "user": user,
            "gamification": g,
            "tasks_count": tasks_count,
            "completed_count": completed_count,
        }

    @staticmethod
    def format_bot_stats(stats: dict) -> str:
        return (
            f"📊 <b>Статистика MindFlow AI</b>\n\n"
            f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
            f"🟢 Активных (24ч): <b>{stats['active_24h']}</b>\n"
            f"💎 Premium: <b>{stats['premium_users']}</b>\n"
            f"📈 Новых сегодня: <b>{stats['new_today']}</b>\n"
            f"📈 Новых за неделю: <b>{stats['new_week']}</b>\n\n"
            f"📋 Всего задач: <b>{stats['total_tasks']}</b>\n"
            f"✅ Выполнено: <b>{stats['completed_tasks']}</b>\n"
            f"🔥 Активных сегодня: <b>{stats['today_active']}</b>\n\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

    @staticmethod
    def format_user_info(info: dict) -> str:
        user = info["user"]
        g = info["gamification"]
        premium_status = "✅ Активен" if user.is_premium_active else "❌ Не активен"
        until = user.premium_until or "—"
        return (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 Username: @{user.username or 'не указан'}\n"
            f"💎 Premium: {premium_status}\n"
            f"📅 Premium до: {until}\n"
            f"🌍 Часовой пояс: {user.timezone}\n"
            f"🌅 Утро: {user.morning_time}\n"
            f"🌙 Вечер: {user.evening_time}\n"
            f"📅 Регистрация: {user.created_at}\n"
            f"🕐 Последняя активность: {user.last_activity or 'нет'}\n\n"
            f"⭐ Уровень: {g.level}\n"
            f"🔥 XP: {g.xp}\n"
            f"📊 Серия: {g.streak} дней\n\n"
            f"📋 Задач создано: {info['tasks_count']}\n"
            f"✅ Выполнено: {info['completed_count']}"
        )
