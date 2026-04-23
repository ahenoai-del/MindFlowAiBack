import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.reminder_service import ReminderService
from bot.keyboards.kb import get_back_button

router = Router()
logger = logging.getLogger(__name__)


class ReminderStates(StatesGroup):
    waiting_text = State()
    waiting_time = State()


@router.message(Command("remind"))
async def cmd_remind(message: Message, state: FSMContext):
    await message.answer(
        "🔔 <b>Создать напоминание</b>\n\n"
        "Напиши текст напоминания:\n\n"
        "Или /cancel для отмены",
        reply_markup=get_back_button(),
    )
    await state.set_state(ReminderStates.waiting_text)


@router.message(ReminderStates.waiting_text)
async def process_remind_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    await state.update_data(reminder_text=text)
    await message.answer(
        "⏰ Теперь напиши время в формате:\n\n"
        "• <b>ГГГГ-ММ-ДД ЧЧ:ММ</b> (2025-01-15 09:00)\n"
        "• <b>через N минут</b>\n"
        "• <b>через N часов</b>\n"
        "• <b>завтра</b>"
    )
    await state.set_state(ReminderStates.waiting_time)


@router.message(ReminderStates.waiting_time)
async def process_remind_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    remind_at = _parse_remind_time(time_str)

    if not remind_at:
        await message.answer(
            "❌ Не удалось распознать время. Попробуй:\n"
            "• 2025-01-15 09:00\n"
            "• через 30 минут\n"
            "• завтра"
        )
        return

    data = await state.get_data()
    text = data.get("reminder_text", "Напоминание")

    reminder = await ReminderService.create(
        user_id=message.from_user.id,
        text=text,
        remind_at=remind_at,
    )

    await state.clear()

    if reminder:
        dt = datetime.fromisoformat(remind_at)
        formatted = dt.strftime("%d.%m.%Y %H:%M")
        await message.answer(f"✅ Напоминание создано!\n\n🔔 {text}\n⏰ {formatted}")
    else:
        await message.answer("❌ Ошибка создания напоминания")


@router.message(Command("reminders"))
async def cmd_reminders(message: Message):
    reminders = await ReminderService.get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer("🔔 У тебя нет активных напоминаний")
        return

    text = "🔔 <b>Твои напоминания:</b>\n\n"
    for r in reminders[:10]:
        dt = datetime.fromisoformat(r.remind_at)
        formatted = dt.strftime("%d.%m.%Y %H:%M")
        text += f"• {r.text or 'Напоминание'}\n  ⏰ {formatted}\n\n"

    await message.answer(text)


def _parse_remind_time(text: str) -> str | None:
    from datetime import timedelta
    text = text.strip().lower()
    now = datetime.now()

    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        if dt > now:
            return dt.isoformat()
    except ValueError:
        pass

    try:
        dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        if dt > now:
            return dt.isoformat()
    except ValueError:
        pass

    if text == "завтра":
        target = now + timedelta(days=1)
        target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        return target.isoformat()

    if text.startswith("через "):
        parts = text.split()
        if len(parts) >= 3:
            try:
                amount = int(parts[1])
                unit = parts[2]
                if unit.startswith("минут"):
                    return (now + timedelta(minutes=amount)).isoformat()
                elif unit.startswith("час"):
                    return (now + timedelta(hours=amount)).isoformat()
                elif unit.startswith("дн"):
                    return (now + timedelta(days=amount)).isoformat()
            except (ValueError, IndexError):
                pass

    return None
