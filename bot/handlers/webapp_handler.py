import json
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

from config.settings import settings
from services.user_service import UserService
from services.premium_service import PremiumService
from services.payment_service import PaymentService
from services.reminder_service import ReminderService
from db import TaskRepo, UserRepo
from bot.keyboards.kb import get_back_button

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "📱 Приложение")
async def open_webapp(message: Message):
    if not settings.WEBAPP_URL:
        await message.answer("⚠️ WebApp пока не настроен.\nДобавь WEBAPP_URL в .env файл")
        return

    from bot.handlers.start import _build_webapp_url
    webapp_url = await _build_webapp_url(message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Открыть MindFlow App",
            web_app=WebAppInfo(url=webapp_url),
        )],
    ])
    await message.answer(
        "📱 <b>MindFlow WebApp</b>\n\nУдобный интерфейс для управления задачами",
        reply_markup=kb,
    )


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        await message.answer("❌ Неверные данные")
        return

    action = data.get("action")

    if action == "buy_premium":
        await PaymentService.create_invoice(message, data.get("plan", "year"))
        return

    if action == "add_reminder":
        text = data.get("text", "").strip()
        remind_at = data.get("remind_at", "")
        if not text or not remind_at:
            await message.answer("❌ Укажи текст и время напоминания")
            return
        repeat = data.get("repeat_interval") or None
        reminder = await ReminderService.create(
            user_id=message.from_user.id,
            text=text,
            remind_at=remind_at,
            repeat_interval=repeat,
        )
        if reminder:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(remind_at)
                formatted = dt.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                formatted = remind_at
            await message.answer(f"✅ Напоминание создано!\n\n🔔 {text}\n⏰ {formatted}")
        else:
            await message.answer("❌ Не удалось создать напоминание")
        return

    if action == "check_premium":
        status = await PremiumService.get_status(message.from_user.id)
        if status["active"]:
            until = status["until"] or "бессрочно"
            await message.answer(f"✅ Premium активен до: {until}")
        else:
            await message.answer("❌ Premium не активен. Напиши /premium для покупки.")
        return

    if action == "add_task":
        title = data.get("title", "").strip()
        if not title:
            await message.answer("❌ Пустое название задачи")
            return
        task = await TaskRepo.create(
            user_id=message.from_user.id,
            title=title,
            description=data.get("description"),
            category=data.get("category", data.get("tag", "general")),
            priority=data.get("priority", 2),
            deadline=data.get("deadline") or None,
            estimated_minutes=data.get("estimated_minutes"),
        )
        if task:
            await message.answer(f"✅ Задача создана: {task.title}")
        else:
            await message.answer("❌ Не удалось создать задачу")
        return

    if action == "complete_task":
        task_id = data.get("task_id")
        if not task_id:
            await message.answer("❌ Не указан ID задачи")
            return
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            await message.answer("❌ Неверный ID задачи")
            return
        from services.task_service import TaskService
        result = await TaskService.complete_task(message.from_user.id, task_id)
        if result:
            await message.answer(f"✅ Выполнено: {result['task'].title}")
        else:
            await message.answer("❌ Задача не найдена")
        return

    if action == "delete_task":
        task_id = data.get("task_id")
        if not task_id:
            await message.answer("❌ Не указан ID задачи")
            return
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            await message.answer("❌ Неверный ID задачи")
            return
        deleted = await TaskRepo.delete_for_user(task_id, message.from_user.id)
        if not deleted:
            await message.answer("❌ Задача не найдена")
            return
        await message.answer("🗑 Задача удалена")
        return

    if action == "update_task":
        task_id = data.get("task_id")
        if not task_id:
            await message.answer("❌ Не указан ID задачи")
            return
        try:
            task_id = int(task_id)
        except (ValueError, TypeError):
            await message.answer("❌ Неверный ID задачи")
            return
        filtered = {
            k: v for k, v in {
                "title": data.get("title"),
                "description": data.get("description"),
                "priority": data.get("priority"),
                "category": data.get("category"),
                "deadline": data.get("deadline") or None,
                "status": data.get("status"),
            }.items() if v is not None
        }
        existing = await TaskRepo.get(task_id)
        if not existing or existing.user_id != message.from_user.id:
            await message.answer("❌ Задача не найдена")
            return
        task = await TaskRepo.update(task_id, **filtered)
        if task:
            await message.answer(f"✏️ Задача обновлена: {task.title}")
        else:
            await message.answer("❌ Задача не найдена")
        return

    await message.answer("❓ Неизвестное действие")
