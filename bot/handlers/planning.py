import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import date, datetime, timedelta

from db import TaskRepo, PlanRepo, UserRepo, GamificationRepo, ACHIEVEMENTS
from services.gamification_service import GamificationService
from services.user_service import UserService
from bot.keyboards.kb import get_plan_menu, get_back_button, get_settings_menu
from ai.scheduler import generate_day_plan

router = Router()
logger = logging.getLogger(__name__)


class ScheduleStates(StatesGroup):
    waiting_time = State()


class SettingsStates(StatesGroup):
    waiting_timezone = State()
    waiting_morning = State()
    waiting_evening = State()


@router.callback_query(F.data == "plan_generate")
async def show_today_plan(callback: CallbackQuery):
    user_id = callback.from_user.id
    today = date.today().isoformat()

    existing_plan = await PlanRepo.get(user_id, today)
    if existing_plan:
        await _show_plan(callback, existing_plan.schedule)
        return

    tasks = await TaskRepo.get_user_tasks(user_id)
    user = await UserService.get(user_id)

    if not tasks:
        text = "📭 Нет задач на сегодня. Добавь задачи, и я составлю план!"
        try:
            await callback.message.edit_text(text, reply_markup=get_plan_menu())
        except Exception:
            await callback.answer(text)
        return

    plan_text = await generate_day_plan(tasks, user.timezone if user else "UTC")
    await PlanRepo.create(user_id, today, plan_text)

    if await GamificationRepo.add_achievement(user_id, "planner"):
        await GamificationRepo.add_xp(user_id, ACHIEVEMENTS["planner"]["xp"])

    await _show_plan(callback, plan_text)


@router.callback_query(F.data == "plan_schedule")
async def plan_schedule_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📅 <b>Настройка расписания</b>\n\nНапиши время в формате ЧЧ:ММ для начала планирования:\n\nНапример: <b>09:00</b>",
        reply_markup=get_back_button(),
    )
    await state.set_state(ScheduleStates.waiting_time)
    await callback.answer()


@router.message(ScheduleStates.waiting_time)
async def process_schedule_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    parts = time_str.split(":")
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Напиши время как: 09:00")
        return
    try:
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши время как: 09:00")
        return

    await UserService.update_settings(message.from_user.id, morning_time=time_str)
    await state.clear()
    await message.answer(f"✅ Планирование будет в {time_str} каждый день")


@router.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    today = date.today()

    tasks = await TaskRepo.get_user_tasks(user_id, include_completed=True)
    completed = [t for t in tasks if t.status == "completed"]

    today_tasks = [t for t in tasks if t.deadline == today.isoformat()]
    today_completed = [
        t for t in completed
        if t.completed_at and t.completed_at.startswith(today.isoformat())
    ]

    g = await GamificationService.get_profile(user_id)
    profile_text = GamificationService.format_profile(g)

    total_today = max(len(today_tasks), 1)
    pct = len(today_completed) / total_today * 100

    text = (
        f"📊 <b>Твоя статистика</b>\n\n"
        f"{profile_text}\n\n"
        f"📊 <b>Сегодня:</b>\n"
        f"• Выполнено: {len(today_completed)}/{len(today_tasks)} задач\n"
        f"• Продуктивность: {pct:.0f}%\n\n"
        f"📅 <b>За неделю:</b>\n"
        f"• Всего задач: {len(tasks)}\n"
        f"• Выполнено: {len(completed)}"
    )

    categories: dict[str, int] = {}
    for t in completed:
        categories[t.category] = categories.get(t.category, 0) + 1
    if categories:
        text += "\n\n🏆 <b>Топ категории:</b>\n"
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]:
            text += f"• {cat}: {count} задач\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏅 Достижения", callback_data="achievements")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.answer("Статистика")


@router.callback_query(F.data == "achievements")
async def show_achievements(callback: CallbackQuery):
    unlocked = await GamificationService.get_achievements(callback.from_user.id)
    text = GamificationService.format_achievements(unlocked)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="stats")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback.answer("Достижения")


@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    user = await UserService.get(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"🌍 Часовой пояс: {user.timezone}\n"
        f"🌅 Утренний план: {user.morning_time}\n"
        f"🌙 Вечерний отчёт: {user.evening_time}"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_settings_menu())
    except Exception:
        await callback.answer("Настройки")


@router.callback_query(F.data == "settings_timezone")
async def change_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌍 Напиши название города для часового пояса:\n\nПримеры: Moscow, London, New York, Tokyo",
        reply_markup=get_back_button(),
    )
    await state.set_state(SettingsStates.waiting_timezone)
    await callback.answer()


@router.callback_query(F.data == "settings_morning")
async def change_morning(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌅 Напиши время для утреннего плана (формат ЧЧ:ММ):\n\nПример: 09:00",
        reply_markup=get_back_button(),
    )
    await state.set_state(SettingsStates.waiting_morning)
    await callback.answer()


@router.callback_query(F.data == "settings_evening")
async def change_evening(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌙 Напиши время для вечернего отчёта (формат ЧЧ:ММ):\n\nПример: 21:00",
        reply_markup=get_back_button(),
    )
    await state.set_state(SettingsStates.waiting_evening)
    await callback.answer()


@router.message(SettingsStates.waiting_timezone)
async def process_settings_timezone(message: Message, state: FSMContext):
    from bot.handlers.start import TIMEZONE_MAP
    city = message.text.strip()
    timezone = TIMEZONE_MAP.get(city.lower(), "UTC")
    await UserService.update_settings(message.from_user.id, timezone=timezone)
    await state.clear()
    await message.answer(f"✅ Часовой пояс: {timezone}")


@router.message(SettingsStates.waiting_morning)
async def process_settings_morning(message: Message, state: FSMContext):
    time_str = message.text.strip()
    parts = time_str.split(":")
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Напиши время как: 09:00")
        return
    try:
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши время как: 09:00")
        return
    await UserService.update_settings(message.from_user.id, morning_time=time_str)
    await state.clear()
    await message.answer(f"✅ Утренний план в {time_str}")


@router.message(SettingsStates.waiting_evening)
async def process_settings_evening(message: Message, state: FSMContext):
    time_str = message.text.strip()
    parts = time_str.split(":")
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Напиши время как: 21:00")
        return
    try:
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except ValueError:
        await message.answer("❌ Неверный формат. Напиши время как: 21:00")
        return
    await UserService.update_settings(message.from_user.id, evening_time=time_str)
    await state.clear()
    await message.answer(f"✅ Вечерний отчёт в {time_str}")


async def _show_plan(event: CallbackQuery, plan_text: str):
    text = f"📅 <b>План на сегодня</b>\n\n{plan_text}"
    try:
        await event.message.edit_text(text, reply_markup=get_plan_menu())
    except Exception:
        await event.answer("План готов!")
