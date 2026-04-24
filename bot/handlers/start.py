import logging
from urllib.parse import urlencode

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config.settings import settings
from services.user_service import UserService
from bot.keyboards.kb import get_main_menu, get_back_button

router = Router()
logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    waiting_timezone = State()
    waiting_morning = State()
    waiting_evening = State()


TIMEZONE_MAP = {
    "moscow": "Europe/Moscow",
    "london": "Europe/London",
    "new york": "America/New_York",
    "tokyo": "Asia/Tokyo",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "kiev": "Europe/Kiev",
    "kyiv": "Europe/Kiev",
    "dubai": "Asia/Dubai",
    "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney",
    "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "istanbul": "Europe/Istanbul",
    "almaty": "Asia/Almaty",
    "tashkent": "Asia/Tashkent",
    "baku": "Asia/Baku",
    "minsk": "Europe/Minsk",
}


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    try:
        user, is_new = await UserService.get_or_create(
            message.from_user.id, message.from_user.username
        )
        if user is None:
            await message.answer("❌ Ошибка создания пользователя. Попробуй позже.")
            return

        if is_new:
            await message.answer(
                "🎉 <b>Добро пожаловать в MindFlow AI!</b>\n\n"
                "🎁 Тебе подарили <b>3 дня Premium</b>!\n\n"
                "Теперь доступны:\n"
                "🎨 Все темы оформления\n"
                "🏷 Безлимитные теги\n"
                "🤖 AI без ограничений\n\n"
                "Давай настроим твой часовой пояс. Напиши название города "
                "(например: Moscow, London, New York):"
            )
            await state.set_state(OnboardingStates.waiting_timezone)
        elif user.timezone == "UTC" and user.morning_time == "09:00":
            await message.answer(
                "👋 Привет! Я MindFlow AI — твой AI-ассистент для планирования.\n\n"
                "Давай настроим твой часовой пояс. Напиши название города "
                "(например: Moscow, London, New York):"
            )
            await state.set_state(OnboardingStates.waiting_timezone)
        else:
            await show_main_menu(message)
    except Exception as e:
        logger.error("Error in cmd_start: %s", e, exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуй позже.")


@router.message(OnboardingStates.waiting_timezone)
async def process_timezone(message: Message, state: FSMContext):
    city = message.text.strip()
    timezone = TIMEZONE_MAP.get(city.lower(), "UTC")
    await UserService.update_settings(message.from_user.id, timezone=timezone)
    await state.update_data(timezone=timezone)
    await message.answer(
        f"✅ Часовой пояс: {timezone}\n\n"
        "Во сколько тебе удобно получать утренний план? (формат: ЧЧ:ММ)"
    )
    await state.set_state(OnboardingStates.waiting_morning)


@router.message(OnboardingStates.waiting_morning)
async def process_morning(message: Message, state: FSMContext):
    time_str = message.text.strip()
    if not _is_valid_time(time_str):
        await message.answer("❌ Неверный формат. Напиши время как: 09:00")
        return
    await UserService.update_settings(message.from_user.id, morning_time=time_str)
    await message.answer(
        f"✅ Утренний план в {time_str}\n\n"
        "Во сколько отправлять вечерний отчёт? (формат: ЧЧ:ММ)"
    )
    await state.set_state(OnboardingStates.waiting_evening)


@router.message(OnboardingStates.waiting_evening)
async def process_evening(message: Message, state: FSMContext):
    time_str = message.text.strip()
    if not _is_valid_time(time_str):
        await message.answer("❌ Неверный формат. Напиши время как: 21:00")
        return
    await UserService.update_settings(message.from_user.id, evening_time=time_str)
    await state.clear()
    await message.answer(
        f"✅ Вечерний отчёт в {time_str}\n\n"
        "🎉 Настройка завершена! Я готов помогать тебе планировать день."
    )
    await show_main_menu(message)


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=get_main_menu(),
    )
    try:
        await callback.message.delete()
    except Exception:
        pass


async def show_main_menu(message: Message):
    webapp_url = await _build_webapp_url(message.from_user.id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(url=webapp_url),
        )] if webapp_url else [],
        [
            InlineKeyboardButton(text="📋 Задачи", callback_data="task_list"),
            InlineKeyboardButton(text="📊 План", callback_data="plan_generate"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
            InlineKeyboardButton(text="📈 Статистика", callback_data="stats"),
        ],
    ])
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыбери действие или открой приложение:",
        reply_markup=keyboard,
    )


async def _build_webapp_url(user_id: int) -> str:
    if not settings.WEBAPP_URL:
        return ""
    url = settings.WEBAPP_URL
    params: dict[str, str] = {}
    is_premium = await UserService.is_premium(user_id)
    if is_premium:
        params["premium"] = "1"
    if settings.API_URL:
        params["api_url"] = settings.API_URL
    if settings.BOT_USERNAME:
        params["bot_username"] = settings.BOT_USERNAME.lstrip("@")
    if params:
        separator = "&" if "?" in url else "?"
        url += separator + urlencode(params)
    return url


def _is_valid_time(time_str: str) -> bool:
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, AttributeError):
        return False
