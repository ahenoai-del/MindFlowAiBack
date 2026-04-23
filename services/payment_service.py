import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

from config.settings import settings
from services.premium_service import PremiumService

logger = logging.getLogger(__name__)

PREMIUM_PLANS = {
    "month": {"stars": settings.PREMIUM_MONTH_STARS, "days": 30},
    "year": {"stars": settings.PREMIUM_YEAR_STARS, "days": 365},
}


class PaymentService:
    @staticmethod
    def get_plans() -> dict:
        return PREMIUM_PLANS

    @staticmethod
    async def create_invoice(
        message: Message,
        plan: str = "year",
    ) -> None:
        if plan not in PREMIUM_PLANS:
            plan = "year"
        price = PREMIUM_PLANS[plan]
        stars = price["stars"]
        days = price["days"]
        months_label = "1 месяц" if days == 30 else "1 год"

        title = f"MindFlow Pro — {months_label}"
        description = (
            f"Premium подписка на {months_label}\n\n"
            "• Все темы оформления\n"
            "• Безлимитные теги\n"
            "• AI без ограничений\n"
            "• Расширенная аналитика"
        )
        await message.answer_invoice(
            title=title,
            description=description,
            payload=f"premium_{plan}_{message.from_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Premium {months_label}", amount=stars)],
            provider_token="",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"⭐ Оплатить {stars} звёзд", pay=True)],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")],
            ]),
        )

    @staticmethod
    async def process_successful_payment(payload: str, user_id: int) -> Optional[str]:
        if not payload.startswith("premium_"):
            logger.warning("Unknown payment payload: %s", payload)
            return None

        parts = payload.split("_")
        if len(parts) < 3:
            logger.error("Invalid payment payload format: %s", payload)
            return None

        plan = parts[1]
        if plan not in PREMIUM_PLANS:
            logger.error("Unknown plan in payload: %s", plan)
            return None

        days = PREMIUM_PLANS[plan]["days"]
        until_str = await PremiumService.activate(user_id, days)
        logger.info("Premium payment processed: user=%s plan=%s days=%s", user_id, plan, days)
        return until_str
