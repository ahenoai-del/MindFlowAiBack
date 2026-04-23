import asyncpg
import logging
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                timezone TEXT DEFAULT 'UTC',
                morning_time TEXT DEFAULT '09:00',
                evening_time TEXT DEFAULT '21:00',
                is_premium BOOLEAN DEFAULT FALSE,
                premium_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'general',
                priority INTEGER DEFAULT 2,
                deadline TEXT,
                estimated_minutes INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                date TEXT NOT NULL,
                schedule TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                date TEXT NOT NULL,
                tasks_completed INTEGER DEFAULT 0,
                tasks_total INTEGER DEFAULT 0,
                focus_score DOUBLE PRECISION,
                notes TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gamification (
                user_id BIGINT PRIMARY KEY REFERENCES users(id),
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                last_activity TEXT,
                total_completed INTEGER DEFAULT 0,
                achievements TEXT DEFAULT '[]'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                task_id BIGINT REFERENCES tasks(id),
                text TEXT,
                remind_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                repeat_interval TEXT,
                snoozed_until TEXT,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                subscription_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium)",
            "CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline)",
            "CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(sent, remind_at)",
            "CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status, remind_at)",
            "CREATE INDEX IF NOT EXISTS idx_gamification_user ON gamification(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_push_subs_user ON push_subscriptions(user_id)",
        ]
        for idx in indexes:
            await conn.execute(idx)

    logger.info("Database initialized")


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _pool
