import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command

from services.payment_service import PaymentService
from services.premium_service import PremiumService
from bot.keyboards.kb import get_premium_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    await message.answer(
        "👑 <b>MindFlow Pro</b>\n\n"
        "Преимущества Premium:\n"
        "🎨 Все темы оформления\n"
        "🏷 Безлимитные теги\n"
        "🔔 Напоминания без ограничений\n"
        "🤖 AI без лимитов\n"
        "📊 Расширенная аналитика\n\n"
        "Выберите план подписки:",
        reply_markup=get_premium_keyboard(),
    )


@router.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    plan = callback.data.split("_")[1]
    if plan not in PaymentService.get_plans():
        await callback.answer("Неверный план")
        return
    await PaymentService.create_invoice(callback.message, plan)
    await callback.answer()


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Отменено")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload

    until_str = await PaymentService.process_successful_payment(
        payload, message.from_user.id
    )
    if until_str:
        from config.settings import settings
        kb = None
        if settings.WEBAPP_URL:
            webapp_url = settings.WEBAPP_URL + ("&" if "?" in settings.WEBAPP_URL else "?") + "premium=1"
            if settings.API_URL:
                webapp_url += f"&api_url={settings.API_URL}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=webapp_url))],
            ])
        await message.answer(
            f"🎉 <b>Premium активирован!</b>\n\n"
            f"Действует до: {until_str}\n\n"
            f"Спасибо за поддержку! ⭐",
            reply_markup=kb,
        )
    else:
        await message.answer("✅ Оплата прошла успешно!")


@router.callback_query(F.data == "check_premium")
async def check_premium_status(callback: CallbackQuery):
    status = await PremiumService.get_status(callback.from_user.id)
    if status["active"]:
        await callback.answer(f"✅ Premium активен до: {status['until']}", show_alert=True)
    else:
        await callback.answer("❌ Premium не активен", show_alert=True)
