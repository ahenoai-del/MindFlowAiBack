import json
import logging
from datetime import datetime, date, timedelta
from typing import Any, List, Optional

import asyncpg

from db.database import get_pool
from db.models import User, Task, Plan, Stats, Gamification, Reminder, PushSubscription

logger = logging.getLogger(__name__)

TASK_UPDATE_FIELDS = {
    "title",
    "description",
    "category",
    "priority",
    "deadline",
    "estimated_minutes",
    "status",
}


def _to_str(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        timezone=row["timezone"],
        morning_time=row["morning_time"],
        evening_time=row["evening_time"],
        is_premium=bool(row["is_premium"]),
        premium_until=row["premium_until"],
        created_at=_to_str(row["created_at"]),
        last_activity=_to_str(row["last_activity"]),
    )


def _row_to_task(row: asyncpg.Record) -> Task:
    return Task(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        priority=row["priority"],
        deadline=row["deadline"],
        estimated_minutes=row["estimated_minutes"],
        status=row["status"],
        created_at=_to_str(row["created_at"]),
        completed_at=_to_str(row["completed_at"]),
    )


def _row_to_gamification(row: asyncpg.Record) -> Gamification:
    return Gamification(
        user_id=row["user_id"],
        xp=row["xp"],
        level=row["level"],
        streak=row["streak"],
        max_streak=row["max_streak"],
        last_activity=row["last_activity"],
        total_completed=row["total_completed"],
        achievements=row["achievements"],
    )


def _row_to_reminder(row: asyncpg.Record) -> Reminder:
    return Reminder(
        id=row["id"],
        user_id=row["user_id"],
        task_id=row["task_id"],
        text=row["text"],
        remind_at=row["remind_at"],
        status=row["status"] or "pending",
        repeat_interval=row["repeat_interval"],
        snoozed_until=row["snoozed_until"],
        sent=bool(row["sent"]),
        created_at=_to_str(row["created_at"]),
    )


class UserRepo:
    @staticmethod
    async def create(user_id: int, username: Optional[str] = None) -> tuple[Optional[User], bool]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO users (id, username) VALUES ($1, $2) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                user_id, username,
            )
            is_new = row is not None
            user = await UserRepo.get(user_id)
            return user, is_new

    @staticmethod
    async def get(user_id: int) -> Optional[User]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id
            )
            if row:
                user = _row_to_user(row)
                if user.is_premium and user.premium_until:
                    try:
                        until_date = datetime.strptime(user.premium_until, "%Y-%m-%d").date()
                        if until_date < datetime.now().date():
                            await UserRepo.revoke_premium(user_id)
                            user.is_premium = False
                    except (ValueError, TypeError):
                        pass
                return user
        return None

    @staticmethod
    async def update_last_activity(user_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_activity = NOW() WHERE id = $1",
                user_id,
            )

    @staticmethod
    async def update_settings(
        user_id: int,
        timezone: Optional[str] = None,
        morning_time: Optional[str] = None,
        evening_time: Optional[str] = None,
    ) -> None:
        pool = get_pool()
        updates: list[str] = []
        values: list[Any] = []
        idx = 1
        if timezone is not None:
            updates.append(f"timezone = ${idx}")
            values.append(timezone)
            idx += 1
        if morning_time is not None:
            updates.append(f"morning_time = ${idx}")
            values.append(morning_time)
            idx += 1
        if evening_time is not None:
            updates.append(f"evening_time = ${idx}")
            values.append(evening_time)
            idx += 1
        if not updates:
            return
        values.append(user_id)
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ${idx}", *values
            )

    @staticmethod
    async def set_premium(user_id: int, until: str) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_premium = TRUE, premium_until = $1 WHERE id = $2",
                until, user_id,
            )

    @staticmethod
    async def revoke_premium(user_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_premium = FALSE, premium_until = NULL WHERE id = $1",
                user_id,
            )

    @staticmethod
    async def get_all() -> List[User]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
            return [_row_to_user(row) for row in rows]

    @staticmethod
    async def count() -> int:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
            return row["cnt"] if row else 0

    @staticmethod
    async def count_premium() -> int:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM users WHERE is_premium = TRUE"
            )
            return row["cnt"] if row else 0

    @staticmethod
    async def count_active_24h() -> int:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM users WHERE last_activity >= NOW() - INTERVAL '24 hours'"
            )
            return row["cnt"] if row else 0

    @staticmethod
    async def count_new_since(since) -> int:
        pool = get_pool()
        async with pool.acquire() as conn:
            if isinstance(since, str):
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM users WHERE created_at >= $1::timestamp",
                    since,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM users WHERE created_at >= $1",
                    since,
                )
            return row["cnt"] if row else 0

    @staticmethod
    async def get_all_ids() -> List[int]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM users")
            return [row["id"] for row in rows]


class TaskRepo:
    @staticmethod
    async def create(
        user_id: int,
        title: str,
        description: Optional[str] = None,
        category: str = "general",
        priority: int = 2,
        deadline: Optional[str] = None,
        estimated_minutes: Optional[int] = None,
    ) -> Optional[Task]:
        pool = get_pool()
        if deadline == "":
            deadline = None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO tasks
                   (user_id, title, description, category, priority, deadline, estimated_minutes)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   RETURNING *""",
                user_id, title, description, category, priority, deadline, estimated_minutes,
            )
            return _row_to_task(row) if row else None

    @staticmethod
    async def get(task_id: int) -> Optional[Task]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE id = $1", task_id
            )
            return _row_to_task(row) if row else None

    @staticmethod
    async def get_user_tasks(
        user_id: int,
        status: Optional[str] = None,
        include_completed: bool = False,
    ) -> List[Task]:
        pool = get_pool()
        query = "SELECT * FROM tasks WHERE user_id = $1"
        params: list[Any] = [user_id]
        idx = 2
        if status:
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1
        elif not include_completed:
            query += " AND status != 'completed'"
        query += " ORDER BY priority ASC, deadline ASC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [_row_to_task(row) for row in rows]

    @staticmethod
    async def update(task_id: int, **kwargs) -> Optional[Task]:
        filtered = {k: v for k, v in kwargs.items() if k in TASK_UPDATE_FIELDS}
        if not filtered:
            return await TaskRepo.get(task_id)
        if filtered.get("deadline") == "":
            filtered["deadline"] = None
        pool = get_pool()
        updates: list[str] = []
        values: list[Any] = []
        idx = 1
        for k, v in filtered.items():
            updates.append(f"{k} = ${idx}")
            values.append(v)
            idx += 1
        values.append(task_id)
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ${idx}", *values
            )
        return await TaskRepo.get(task_id)

    @staticmethod
    async def complete(task_id: int) -> Optional[Task]:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status = 'completed', completed_at = NOW() WHERE id = $1",
                task_id,
            )
        return await TaskRepo.get(task_id)

    @staticmethod
    async def uncomplete(task_id: int) -> Optional[Task]:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status = 'pending', completed_at = NULL WHERE id = $1",
                task_id,
            )
        return await TaskRepo.get(task_id)

    @staticmethod
    async def delete(task_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)

    @staticmethod
    async def delete_for_user(task_id: int, user_id: int) -> bool:
        pool = get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM tasks WHERE id = $1 AND user_id = $2",
                task_id, user_id,
            )
            return result.endswith(" 1")


class PlanRepo:
    @staticmethod
    async def create(user_id: int, date_str: str, schedule: str) -> Optional[Plan]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO plans (user_id, date, schedule) VALUES ($1, $2, $3)
                   ON CONFLICT (user_id, date) DO UPDATE SET schedule = EXCLUDED.schedule
                   RETURNING *""",
                user_id, date_str, schedule,
            )
            if row:
                return Plan(
                    id=row["id"],
                    user_id=row["user_id"],
                    date=row["date"],
                    schedule=row["schedule"],
                    created_at=_to_str(row["created_at"]),
                )
        return None

    @staticmethod
    async def get(user_id: int, date_str: str) -> Optional[Plan]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM plans WHERE user_id = $1 AND date = $2",
                user_id, date_str,
            )
            if row:
                return Plan(
                    id=row["id"],
                    user_id=row["user_id"],
                    date=row["date"],
                    schedule=row["schedule"],
                    created_at=_to_str(row["created_at"]),
                )
        return None


class StatsRepo:
    @staticmethod
    async def create_or_update(
        user_id: int,
        date_str: str,
        tasks_completed: Optional[int] = None,
        tasks_total: Optional[int] = None,
        focus_score: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Optional[Stats]:
        pool = get_pool()
        existing = await StatsRepo.get(user_id, date_str)
        async with pool.acquire() as conn:
            if existing:
                updates: list[str] = []
                values: list[Any] = []
                idx = 1
                if tasks_completed is not None:
                    updates.append(f"tasks_completed = ${idx}")
                    values.append(tasks_completed)
                    idx += 1
                if tasks_total is not None:
                    updates.append(f"tasks_total = ${idx}")
                    values.append(tasks_total)
                    idx += 1
                if focus_score is not None:
                    updates.append(f"focus_score = ${idx}")
                    values.append(focus_score)
                    idx += 1
                if notes is not None:
                    updates.append(f"notes = ${idx}")
                    values.append(notes)
                    idx += 1
                if updates:
                    values.extend([user_id, date_str])
                    await conn.execute(
                        f"UPDATE stats SET {', '.join(updates)} "
                        f"WHERE user_id = ${idx} AND date = ${idx + 1}",
                        *values,
                    )
            else:
                await conn.execute(
                    """INSERT INTO stats
                       (user_id, date, tasks_completed, tasks_total, focus_score, notes)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    user_id, date_str, tasks_completed or 0, tasks_total or 0,
                    focus_score, notes,
                )
        return await StatsRepo.get(user_id, date_str)

    @staticmethod
    async def get(user_id: int, date_str: str) -> Optional[Stats]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM stats WHERE user_id = $1 AND date = $2",
                user_id, date_str,
            )
            if row:
                return Stats(
                    id=row["id"],
                    user_id=row["user_id"],
                    date=row["date"],
                    tasks_completed=row["tasks_completed"],
                    tasks_total=row["tasks_total"],
                    focus_score=row["focus_score"],
                    notes=row["notes"],
                )
        return None

    @staticmethod
    async def get_week_stats(user_id: int) -> List[Stats]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM stats WHERE user_id = $1
                   AND date >= CURRENT_DATE - INTERVAL '7 days'
                   ORDER BY date DESC""",
                user_id,
            )
            return [
                Stats(
                    id=row["id"],
                    user_id=row["user_id"],
                    date=row["date"],
                    tasks_completed=row["tasks_completed"],
                    tasks_total=row["tasks_total"],
                    focus_score=row["focus_score"],
                    notes=row["notes"],
                )
                for row in rows
            ]


class GamificationRepo:
    @staticmethod
    async def get_or_create(user_id: int) -> Gamification:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO gamification (user_id) VALUES ($1)
                   ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
                   RETURNING *""",
                user_id,
            )
            if row:
                return _row_to_gamification(row)
        return Gamification(user_id=user_id)

    @staticmethod
    async def add_xp(user_id: int, xp: int) -> tuple[Gamification, int, bool]:
        from db.models import get_level

        current = await GamificationRepo.get_or_create(user_id)
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE gamification SET xp = xp + $1 WHERE user_id = $2",
                xp, user_id,
            )
        g = await GamificationRepo.get_or_create(user_id)
        new_level = get_level(g.xp)
        if new_level > current.level:
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE gamification SET level = $1 WHERE user_id = $2",
                    new_level, user_id,
                )
            g.level = new_level
            return g, new_level, True
        return g, g.level, False

    @staticmethod
    async def update_streak(user_id: int, completed: bool = True) -> int:
        pool = get_pool()
        g = await GamificationRepo.get_or_create(user_id)
        if not completed:
            return g.streak

        today = date.today().isoformat()
        if g.last_activity:
            try:
                last = datetime.fromisoformat(g.last_activity).date()
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                if last.isoformat() == yesterday:
                    new_streak = g.streak + 1
                elif last.isoformat() == today:
                    new_streak = g.streak
                else:
                    new_streak = 1
            except (ValueError, TypeError):
                new_streak = 1
        else:
            new_streak = 1

        max_streak = max(g.max_streak, new_streak)
        now_iso = datetime.now().isoformat()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE gamification
                   SET streak = $1, max_streak = $2, last_activity = $3, total_completed = total_completed + 1
                   WHERE user_id = $4""",
                new_streak, max_streak, now_iso, user_id,
            )
        return new_streak

    @staticmethod
    async def add_achievement(user_id: int, achievement_id: str) -> bool:
        pool = get_pool()
        g = await GamificationRepo.get_or_create(user_id)
        try:
            achievements = json.loads(g.achievements or "[]")
        except (json.JSONDecodeError, TypeError):
            achievements = []
        if achievement_id in achievements:
            return False
        achievements.append(achievement_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE gamification SET achievements = $1 WHERE user_id = $2",
                json.dumps(achievements), user_id,
            )
        return True

    @staticmethod
    async def get_achievements(user_id: int) -> list:
        g = await GamificationRepo.get_or_create(user_id)
        try:
            return json.loads(g.achievements or "[]")
        except (json.JSONDecodeError, TypeError):
            return []


class ReminderRepo:
    @staticmethod
    async def create(
        user_id: int,
        remind_at: str,
        task_id: Optional[int] = None,
        text: Optional[str] = None,
        repeat_interval: Optional[str] = None,
    ) -> Optional[Reminder]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO reminders (user_id, task_id, text, remind_at, repeat_interval)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING *""",
                user_id, task_id, text, remind_at, repeat_interval,
            )
            return _row_to_reminder(row) if row else None

    @staticmethod
    async def get(reminder_id: int) -> Optional[Reminder]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM reminders WHERE id = $1", reminder_id
            )
            return _row_to_reminder(row) if row else None

    @staticmethod
    async def get_pending(user_id: Optional[int] = None) -> List[Reminder]:
        pool = get_pool()
        now = datetime.now().isoformat()
        query = """SELECT * FROM reminders
                   WHERE (status = 'pending' OR status IS NULL) AND sent = FALSE
                   AND REPLACE(REPLACE(remind_at, 'Z', ''), '+00:00', '') <= $1"""
        params: list[Any] = [now]
        if user_id:
            query += " AND user_id = $2"
            params.append(user_id)
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [_row_to_reminder(row) for row in rows]

    @staticmethod
    async def get_user_reminders(user_id: int) -> List[Reminder]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM reminders
                   WHERE user_id = $1 AND (status = 'pending' OR status IS NULL) AND sent = FALSE
                   ORDER BY remind_at ASC""",
                user_id,
            )
            return [_row_to_reminder(row) for row in rows]

    @staticmethod
    async def mark_sent(reminder_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE reminders SET sent = TRUE, status = 'sent' WHERE id = $1",
                reminder_id,
            )

    @staticmethod
    async def snooze(reminder_id: int, snoozed_until: str) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE reminders SET snoozed_until = $1, remind_at = $1, status = 'snoozed' WHERE id = $2",
                snoozed_until, reminder_id,
            )

    @staticmethod
    async def delete(reminder_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM reminders WHERE id = $1", reminder_id)

    @staticmethod
    async def delete_for_task(task_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM reminders WHERE task_id = $1", task_id)


class PushSubscriptionRepo:
    @staticmethod
    async def upsert(user_id: int, subscription_json: str) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO push_subscriptions (user_id, subscription_json, updated_at)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (user_id) DO UPDATE SET subscription_json = EXCLUDED.subscription_json, updated_at = NOW()""",
                user_id, subscription_json,
            )

    @staticmethod
    async def get_by_user(user_id: int) -> Optional[PushSubscription]:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM push_subscriptions WHERE user_id = $1", user_id
            )
            if row:
                return PushSubscription(
                    id=row["id"],
                    user_id=row["user_id"],
                    subscription_json=row["subscription_json"],
                    created_at=_to_str(row["created_at"]),
                    updated_at=_to_str(row["updated_at"]),
                )
        return None

    @staticmethod
    async def get_all() -> List[PushSubscription]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM push_subscriptions")
            return [
                PushSubscription(
                    id=row["id"],
                    user_id=row["user_id"],
                    subscription_json=row["subscription_json"],
                    created_at=_to_str(row["created_at"]),
                    updated_at=_to_str(row["updated_at"]),
                )
                for row in rows
            ]

    @staticmethod
    async def delete(user_id: int) -> None:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM push_subscriptions WHERE user_id = $1", user_id
            )
