import asyncio
import json
import logging
from typing import Optional

from db import PushSubscriptionRepo
from config.settings import settings

logger = logging.getLogger(__name__)


class PushService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)

    @staticmethod
    async def register_subscription(user_id: int, subscription_json: str) -> bool:
        try:
            sub = json.loads(subscription_json)
            if not sub.get("endpoint"):
                logger.warning("Invalid push subscription: no endpoint for user %s", user_id)
                return False
            await PushSubscriptionRepo.upsert(user_id, subscription_json)
            logger.info("Push subscription registered for user %s", user_id)
            return True
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Invalid push subscription JSON for user %s: %s", user_id, e)
            return False

    @staticmethod
    async def unregister_subscription(user_id: int) -> None:
        await PushSubscriptionRepo.delete(user_id)

    @staticmethod
    async def send_push(user_id: int, title: str, body: str, url: str = "") -> bool:
        if not PushService.is_configured():
            logger.debug("Push not configured, skipping for user %s", user_id)
            return False

        sub_record = await PushSubscriptionRepo.get_by_user(user_id)
        if not sub_record:
            return False

        try:
            from pywebpush import webpush

            subscription = json.loads(sub_record.subscription_json)
            payload = json.dumps({
                "title": title,
                "body": body,
                "url": url or settings.WEBAPP_URL,
                "icon": "/icon-192.png",
                "tag": "mindflow-reminder",
            })

            await asyncio.to_thread(
                webpush,
                subscription_info=subscription,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            )
            logger.info("Push sent to user %s", user_id)
            return True
        except Exception as e:
            logger.warning("Push failed for user %s: %s", user_id, e)
            return False

    @staticmethod
    async def send_push_or_fallback(
        bot,
        user_id: int,
        title: str,
        body: str,
        fallback_text: str = "",
        url: str = "",
    ) -> str:
        push_sent = await PushService.send_push(user_id, title, body, url)
        if push_sent:
            return "push"

        try:
            text = fallback_text or f"{title}\n{body}"
            await bot.send_message(user_id, text)
            return "telegram"
        except Exception as e:
            logger.warning("Telegram fallback failed for %s: %s", user_id, e)
            return "failed"
