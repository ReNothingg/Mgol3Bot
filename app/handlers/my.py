from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import Repo
from app.db.session import session_scope
from app.handlers.common import ensure_subscribed
from app.keyboards.common import my_events_keyboard
from app.services.render import my_events_text

router = Router(name="my")


@router.message(Command("my"))
async def cmd_my(
    message: Message,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    if not await ensure_subscribed(
        bot=bot,
        settings=settings,
        user_id=message.from_user.id,
        target=message,
    ):
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        participations = await repo.list_user_participations(message.from_user.id)

    text = my_events_text(participations)
    if participations:
        await message.answer(text, reply_markup=my_events_keyboard(participations))
    else:
        await message.answer(text)
