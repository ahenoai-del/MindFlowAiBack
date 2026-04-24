import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from db import UserRepo, TaskRepo, PlanRepo, ReminderRepo
from services.push_service import PushService
from services.premium_service import PremiumService
from services.reminder_service import ReminderService
from ai.scheduler import generate_day_plan, generate_evening_summary

scheduler = AsyncIOScheduler()
logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot) -> None:
    scheduler.add_job(
        send_scheduled_messages,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="scheduled_messages",
        replace_existing=True,
    )
    scheduler.add_job(
        send_reminders,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="send_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        expire_premium_users,
        IntervalTrigger(hours=6),
        id="expire_premium",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()


async def send_scheduled_messages(bot: Bot) -> None:
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    today = date.today().isoformat()

    try:
        users = await UserRepo.get_all()
    except Exception as e:
        logger.error("Failed to fetch users for scheduled messages: %s", e)
        return

    for user in users:
        try:
            if user.morning_time == current_time:
                tasks = await TaskRepo.get_user_tasks(user.id)
                if tasks:
                    plan = await PlanRepo.get(user.id, today)
                    if not plan:
                        plan_text = await generate_day_plan(tasks, user.timezone)
                        await PlanRepo.create(user.id, today, plan_text)
                    else:
                        plan_text = plan.schedule
                    await bot.send_message(
                        user.id,
                        f"🌅 <b>Доброе утро!</b>\n\n📅 Вот твой план на сегодня:\n\n{plan_text}",
                    )

            if user.evening_time == current_time:
                tasks = await TaskRepo.get_user_tasks(user.id, include_completed=True)
                if tasks:
                    summary = await generate_evening_summary(tasks)
                    await bot.send_message(user.id, summary)

        except Exception as e:
            logger.debug("Failed to send scheduled message to %s: %s", user.id, e)


async def send_reminders(bot: Bot) -> None:
    try:
        reminders = await ReminderService.get_due_reminders()
    except Exception as e:
        logger.error("Failed to fetch reminders: %s", e)
        return

    for reminder in reminders:
        try:
            reminder_text = await ReminderService.format_reminder_text(reminder)
            push_payload = await ReminderService.format_push_payload(reminder)

            delivery = await PushService.send_push_or_fallback(
                bot=bot,
                user_id=reminder.user_id,
                title=push_payload["title"],
                body=push_payload["body"],
                fallback_text=reminder_text,
            )

            logger.info("Reminder %s delivered via %s", reminder.id, delivery)

            await ReminderService.mark_sent(reminder.id)
            await ReminderService.handle_repeat(reminder)

        except Exception as e:
            logger.debug("Failed to send reminder %s: %s", reminder.id, e)


async def expire_premium_users() -> None:
    try:
        users = await UserRepo.get_all()
        for user in users:
            if user.is_premium and user.premium_until:
                try:
                    from datetime import datetime as dt
                    until_date = dt.strptime(user.premium_until, "%Y-%m-%d").date()
                    if until_date < date.today():
                        await PremiumService.revoke(user.id)
                        logger.info("Expired premium for user %s", user.id)
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        logger.error("Failed to expire premium users: %s", e)
