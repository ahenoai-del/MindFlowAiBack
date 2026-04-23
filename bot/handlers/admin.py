import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime

from config.settings import settings
from services.analytics_service import AnalyticsService
from services.premium_service import PremiumService
from services.broadcast_service import BroadcastService
from middlewares.admin import is_admin
from bot.keyboards.kb import get_admin_keyboard, get_back_button

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return
    await message.answer(
        "🔐 <b>Админ-панель MindFlow AI</b>\n\nВыберите раздел:",
        reply_markup=get_admin_keyboard(),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await AnalyticsService.get_bot_stats()
    await message.answer(AnalyticsService.format_bot_stats(stats))


@router.message(Command("user"))
async def cmd_user_info(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Формат: /user USER_ID")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный USER_ID")
        return
    info = await AnalyticsService.get_user_info(user_id)
    if not info:
        await message.answer("❌ Пользователь не найден")
        return
    await message.answer(AnalyticsService.format_user_info(info))


@router.message(Command("add_premium"))
async def cmd_add_premium(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Формат: /add_premium USER_ID DAYS")
        return
    try:
        user_id = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.answer("❌ Неверные аргументы")
        return
    until_str = await PremiumService.activate(user_id, days)
    await message.answer(f"✅ Premium добавлен для {user_id} на {days} дней (до {until_str})")
    try:
        await message.bot.send_message(
            user_id,
            f"🎉 <b>Premium активирован!</b>\n\n"
            f"Вы получили MindFlow Pro на {days} дней!\n"
            f"Действует до: {until_str}",
        )
    except Exception:
        pass


@router.message(Command("remove_premium"))
async def cmd_remove_premium(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Формат: /remove_premium USER_ID")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный USER_ID")
        return
    await PremiumService.revoke(user_id)
    await message.answer(f"✅ Premium удалён для {user_id}")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("❌ Укажите текст рассылки: /broadcast Текст")
        return

    status_msg = await message.answer("📢 Рассылка начата...")
    result = await BroadcastService.broadcast(message.bot, text)
    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Отправлено: {result['success']}\n"
        f"❌ Ошибок: {result['failed']}\n"
        f"🚫 Заблокировано: {result['blocked']}"
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    stats = await AnalyticsService.get_bot_stats()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(
            AnalyticsService.format_bot_stats(stats),
            reply_markup=keyboard,
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    from db import UserRepo
    users = await UserRepo.get_all()
    text = "👥 <b>Последние пользователи:</b>\n\n"
    for u in users[-20:]:
        username = f"@{u.username}" if u.username else "No username"
        premium = "💎" if u.is_premium_active else ""
        text += f"• {username} {premium}\n  ID: <code>{u.id}</code>\n\n"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_premium")
async def admin_premium(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    from db import UserRepo
    users = await UserRepo.get_all()
    premium_users = [u for u in users if u.is_premium_active]
    text = f"💎 <b>Premium пользователи ({len(premium_users)}):</b>\n\n"
    for u in premium_users:
        username = f"@{u.username}" if u.username else f"ID: {u.id}"
        until = u.premium_until or "Бессрочно"
        text += f"• {username}\n  До: {until}\n\n"
    text += (
        "\nКоманды:\n"
        "• /add_premium USER_ID DAYS — выдать премиум\n"
        "• /remove_premium USER_ID — снять премиум"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_analytics")
async def admin_analytics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    from db.database import get_pool
    pool = get_pool()
    text = "📈 <b>Аналитика</b>\n\n"
    try:
        async with pool.acquire() as conn:
            by_category = await conn.fetch(
                "SELECT category, COUNT(*) as cnt FROM tasks GROUP BY category ORDER BY cnt DESC LIMIT 5"
            )
            by_priority = await conn.fetch(
                "SELECT priority, COUNT(*) as cnt FROM tasks GROUP BY priority"
            )
        text += "📊 <b>По категориям:</b>\n"
        for r in by_category:
            text += f"• {r['category']}: {r['cnt']}\n"
        text += "\n⚡ <b>По приоритету:</b>\n"
        pnames = {1: "🔴 Высокий", 2: "🟡 Средний", 3: "🟢 Низкий"}
        for r in by_priority:
            p = r['priority']
            name = pnames.get(p, f"Приоритет {p}")
            text += f"• {name}: {r['cnt']}\n"
    except Exception as e:
        logger.error("Analytics query error: %s", e)
        text += "❌ Ошибка загрузки аналитики"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_top")
async def admin_top(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    import json
    from db.database import get_pool
    pool = get_pool()
    text = "🏆 <b>Топ пользователи по XP:</b>\n\n"
    try:
        async with pool.acquire() as conn:
            top_users = await conn.fetch(
                "SELECT u.username, u.id, g.level, g.xp, g.streak, g.achievements "
                "FROM gamification g JOIN users u ON g.user_id = u.id "
                "ORDER BY g.xp DESC LIMIT 10"
            )
        for i, u in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            username = f"@{u['username']}" if u["username"] else f"User {u['id']}"
            ach_count = len(json.loads(u["achievements"] or "[]"))
            text += f"{medal} {username}\n   ⭐ Ур. {u['level']} | {u['xp']} XP\n   🔥 Серия: {u['streak']} | 🏅 {ach_count}\n\n"
    except Exception as e:
        logger.error("Top query error: %s", e)
        text += "❌ Ошибка загрузки"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"🤖 Bot Token: {'✅' if settings.BOT_TOKEN else '❌'}\n"
        f"🧠 OpenAI Key: {'✅' if settings.OPENAI_API_KEY else '❌'}\n"
        f"🌐 WebApp URL: {settings.WEBAPP_URL or '❌'}\n"
        f"👤 Admin IDs: {settings.ADMIN_IDS or '❌'}\n\n"
        "Команды:\n"
        "• /admin — Админ-панель\n"
        "• /stats — Статистика\n"
        "• /user USER_ID — Инфо\n"
        "• /add_premium USER_ID DAYS\n"
        "• /remove_premium USER_ID\n"
        "• /broadcast Текст"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    try:
        await callback.message.edit_text(
            "🔐 <b>Админ-панель MindFlow AI</b>\n\nВыберите раздел:",
            reply_markup=get_admin_keyboard(),
        )
    except Exception:
        pass
    await callback.answer()
