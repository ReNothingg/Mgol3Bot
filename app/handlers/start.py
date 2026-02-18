from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import Repo
from app.db.session import session_scope
from app.handlers.common import ensure_subscribed, ensure_user_saved, send_main_menu
from app.services.notifier import notify_admins
from app.services.time_utils import is_within_period, utcnow_naive

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject | None,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return

    await ensure_user_saved(message=message, session_factory=session_factory)

    if not await ensure_subscribed(
        bot=bot,
        settings=settings,
        user_id=message.from_user.id,
        target=message,
    ):
        return

    deep_link_arg = (command.args or "").strip() if command else ""
    if deep_link_arg.startswith("join_"):
        await handle_deep_link_join(
            message=message,
            deep_link_arg=deep_link_arg,
            settings=settings,
            session_factory=session_factory,
            bot=bot,
        )
    await send_main_menu(target=message, settings=settings, session_factory=session_factory)


@router.callback_query(lambda c: c.data == "sub:check")
async def check_subscription(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None:
        return
    if not await ensure_subscribed(
        bot=bot,
        settings=settings,
        user_id=callback.from_user.id,
        target=callback,
    ):
        return
    await send_main_menu(target=callback, settings=settings, session_factory=session_factory)


@router.callback_query(lambda c: c.data == "menu:main")
async def open_main_menu(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await send_main_menu(target=callback, settings=settings, session_factory=session_factory)


async def handle_deep_link_join(
    *,
    message: Message,
    deep_link_arg: str,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    event_id_str = deep_link_arg.removeprefix("join_")
    if not event_id_str.isdigit():
        return

    event_id = int(event_id_str)
    now = utcnow_naive()
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await message.answer("Ивент по ссылке не найден.")
            return
        if not (
            event.is_active
            and is_within_period(now=now, start=event.start_at, end=event.end_at)
        ):
            await message.answer("Ивент по ссылке уже недоступен.")
            return

        _, created = await repo.join_event(
            user_tg_id=message.from_user.id,
            username=message.from_user.username,
            full_name=f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip(),
            event_id=event.id,
        )

    if created:
        username = f"@{message.from_user.username}" if message.from_user.username else "без username"
        await notify_admins(
            bot,
            settings.admin_ids,
            f"Новый участник по deep-link: {username} ({message.from_user.id}) в ивенте «{event.title}».",
        )
        await message.answer(f"Вы зарегистрированы в ивенте «{event.title}».")
    else:
        await message.answer(f"Вы уже участвуете в ивенте «{event.title}».")
