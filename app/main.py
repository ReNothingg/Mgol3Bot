from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings
from app.db.session import create_engine_and_factory, init_db
from app.handlers import setup_routers
from app.services.event_closer import EventCloser


async def run() -> None:
    settings = get_settings()
    engine, session_factory = create_engine_and_factory(settings)
    await init_db(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    setup_routers(dp)

    event_closer = EventCloser(settings=settings, session_factory=session_factory)

    async def on_startup(bot: Bot) -> None:
        event_closer.start(bot)

    async def on_shutdown(bot: Bot) -> None:
        _ = bot
        await event_closer.stop()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(
            bot,
            settings=settings,
            session_factory=session_factory,
        )
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
