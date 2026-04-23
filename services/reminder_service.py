import logging
from datetime import datetime, timedelta
from typing import Optional, List

from db import ReminderRepo, TaskRepo
from db.models import Reminder

logger = logging.getLogger(__name__)


class ReminderService:
    @staticmethod
    async def create(
        user_id: int,
        remind_at: str,
        text: Optional[str] = None,
        task_id: Optional[int] = None,
        repeat_interval: Optional[str] = None,
    ) -> Optional[Reminder]:
        return await ReminderRepo.create(
            user_id=user_id,
            remind_at=remind_at,
            task_id=task_id,
            text=text,
            repeat_interval=repeat_interval,
        )

    @staticmethod
    async def get_user_reminders(user_id: int) -> List[Reminder]:
        return await ReminderRepo.get_user_reminders(user_id)

    @staticmethod
    async def delete(reminder_id: int, user_id: int) -> bool:
        reminder = await ReminderRepo.get(reminder_id)
        if not reminder or reminder.user_id != user_id:
            return False
        await ReminderRepo.delete(reminder_id)
        return True

    @staticmethod
    async def snooze(reminder_id: int, user_id: int, minutes: int = 10) -> bool:
        reminder = await ReminderRepo.get(reminder_id)
        if not reminder or reminder.user_id != user_id:
            return False
        snoozed_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        await ReminderRepo.snooze(reminder_id, snoozed_until)
        return True

    @staticmethod
    async def get_due_reminders() -> List[Reminder]:
        return await ReminderRepo.get_pending()

    @staticmethod
    async def mark_sent(reminder_id: int) -> None:
        await ReminderRepo.mark_sent(reminder_id)

    @staticmethod
    async def format_reminder_text(reminder: Reminder) -> str:
        if reminder.text:
            return f"⏰ <b>Напоминание!</b>\n\n{reminder.text}"
        if reminder.task_id:
            task = await TaskRepo.get(reminder.task_id)
            if task:
                return f"⏰ <b>Напоминание о задаче!</b>\n\n📋 {task.title}"
            return f"⏰ <b>Напоминание о задаче!</b>\n\n📋 Задача ID: {reminder.task_id}"
        return "⏰ <b>Напоминание!</b>"

    @staticmethod
    async def format_push_payload(reminder: Reminder) -> dict:
        if reminder.text:
            return {"title": "MindFlow Напоминание", "body": reminder.text}
        if reminder.task_id:
            task = await TaskRepo.get(reminder.task_id)
            body = task.title if task else f"Задача #{reminder.task_id}"
            return {"title": "MindFlow", "body": body}
        return {"title": "MindFlow", "body": "У тебя есть напоминание!"}

    @staticmethod
    async def handle_repeat(reminder: Reminder) -> None:
        if not reminder.repeat_interval:
            return
        try:
            current = datetime.fromisoformat(reminder.remind_at)
            intervals = {
                "daily": timedelta(days=1),
                "weekly": timedelta(weeks=1),
                "monthly": timedelta(days=30),
                "hourly": timedelta(hours=1),
            }
            delta = intervals.get(reminder.repeat_interval)
            if delta:
                next_time = current + delta
                await ReminderRepo.create(
                    user_id=reminder.user_id,
                    remind_at=next_time.isoformat(),
                    task_id=reminder.task_id,
                    text=reminder.text,
                    repeat_interval=reminder.repeat_interval,
                )
        except Exception as e:
            logger.error("Failed to handle repeat for reminder %s: %s", reminder.id, e)
