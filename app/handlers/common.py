from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import Repo
from app.db.session import session_scope
from app.keyboards.common import main_menu_keyboard, subscription_keyboard
from app.services.render import main_description
from app.services.subscription import is_user_subscribed


def _full_name(message: Message) -> str:
    first = message.from_user.first_name if message.from_user else ""
    last = message.from_user.last_name if message.from_user else ""
    full = f"{first} {last}".strip()
    return full or "Unknown User"


async def ensure_user_saved(
    *,
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        await repo.get_or_create_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            full_name=_full_name(message),
        )


async def ensure_subscribed(
    *,
    bot: Bot,
    settings: Settings,
    user_id: int,
    target: Message | CallbackQuery,
) -> bool:
    subscribed = await is_user_subscribed(bot, settings.required_channel, user_id)
    if subscribed:
        return True

    text = (
        "Для использования бота нужно подписаться на канал.\n"
        "После подписки нажмите «Проверить подписку»."
    )
    keyboard = subscription_keyboard(settings.required_channel_url)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
    else:
        if target.message:
            await target.message.answer(text, reply_markup=keyboard)
        await target.answer()
    return False


async def send_main_menu(
    *,
    target: Message | CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        events = await repo.list_events_for_main(now)

    text = main_description(
        bot_name=settings.bot_name,
        channel_name=settings.channel_name,
        channel_url=settings.required_channel_url,
        developer_url=settings.developer_url,
    )
    keyboard = main_menu_keyboard(events)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
        return

    if target.message:
        await target.message.answer(text, reply_markup=keyboard)
    await target.answer()

