import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config.settings import settings
from db.database import init_db, close_db
from bot.handlers import start_router, tasks_router, planning_router, webapp_router, admin_router, payments_router, reminders_router
from middlewares.error_handler import ErrorHandlerMiddleware
from middlewares.rate_limit import RateLimitMiddleware
from scheduler.jobs import setup_scheduler
from utils.logging import setup_logging

logger = logging.getLogger(__name__)


class ProxySession(AiohttpSession):
    def __init__(self, proxy_url: str, **kwargs):
        super().__init__(**kwargs)
        self._proxy_url = proxy_url

    async def _make_request(self, *args, **kwargs):
        kwargs.setdefault("proxy", self._proxy_url)
        return await super()._make_request(*args, **kwargs)


async def run_bot() -> None:
    if settings.PROXY_URL:
        session = ProxySession(proxy_url=settings.PROXY_URL)
    else:
        session = AiohttpSession()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    dp = Dispatcher()

    dp.message.middleware(ErrorHandlerMiddleware())
    dp.callback_query.middleware(ErrorHandlerMiddleware())
    dp.message.middleware(RateLimitMiddleware(limit_seconds=settings.RATE_LIMIT_SECONDS))

    dp.include_router(payments_router)
    dp.include_router(start_router)
    dp.include_router(tasks_router)
    dp.include_router(planning_router)
    dp.include_router(webapp_router)
    dp.include_router(admin_router)
    dp.include_router(reminders_router)

    setup_scheduler(bot)

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()


async def run_api() -> None:
    import uvicorn
    from api import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    setup_logging(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)
    logger.info("Starting MindFlow...")
    logger.info("DATABASE_URL set: %s", bool(settings.DATABASE_URL))
    logger.info("BOT_TOKEN set: %s", bool(settings.BOT_TOKEN))
    try:
        await init_db()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.critical("Failed to connect to database: %s", e, exc_info=True)
        raise

    if os.environ.get("RUN_API") == "true":
        logger.info("Running bot + API mode")
        await asyncio.gather(run_bot(), run_api())
    else:
        logger.info("Running bot only mode")
        await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
