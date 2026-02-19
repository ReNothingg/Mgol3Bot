from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import Repo
from app.db.session import session_scope
from app.handlers.common import ensure_subscribed
from app.keyboards.common import event_keyboard
from app.services.notifier import notify_admins
from app.services.render import event_card_text
from app.services.time_utils import is_within_period, utcnow_naive

router = Router(name="events")


@router.callback_query(lambda c: c.data == "event:noop")
async def event_noop(callback: CallbackQuery) -> None:
    await callback.answer("Действие недоступно.")


@router.callback_query(lambda c: c.data and c.data.startswith("event:open:"))
async def open_event_card(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or callback.message is None:
        return
    if not await ensure_subscribed(
        bot=bot,
        settings=settings,
        user_id=callback.from_user.id,
        target=callback,
    ):
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID ивента.")
        return

    now = utcnow_naive()
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await callback.answer("Ивент не найден.")
            return
        participation = await repo.get_participation(
            user_tg_id=callback.from_user.id,
            event_id=event.id,
        )
        has_submission = False
        if participation is not None:
            has_submission = (await repo.get_submission(participation.id)) is not None

    keyboard = event_keyboard(
        event=event,
        participation=participation,
        has_submission=has_submission,
        is_open_now=event.is_active and is_within_period(
            now=now,
            start=event.start_at,
            end=event.end_at,
        ),
        is_started=now >= event.start_at,
    )
    await callback.message.answer(event_card_text(event), reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("event:join:"))
async def join_event(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or callback.message is None:
        return
    if not await ensure_subscribed(
        bot=bot,
        settings=settings,
        user_id=callback.from_user.id,
        target=callback,
    ):
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID ивента.")
        return

    now = utcnow_naive()
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await callback.answer("Ивент не найден.")
            return
        if not (
            event.is_active
            and is_within_period(now=now, start=event.start_at, end=event.end_at)
        ):
            await callback.answer("Ивент недоступен.", show_alert=True)
            return

        participation, created = await repo.join_event(
            user_tg_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=f"{callback.from_user.first_name} {callback.from_user.last_name or ''}".strip(),
            event_id=event.id,
        )
        has_submission = (await repo.get_submission(participation.id)) is not None

    if created:
        username = f"@{callback.from_user.username}" if callback.from_user.username else "без username"
        text = (
            "✅ Новая регистрация в ивенте\n"
            f"Ивент: <b>{escape(event.title)}</b>\n"
            f"Пользователь: {escape(username)}\n"
            f"Telegram ID: <code>{callback.from_user.id}</code>"
        )
        await notify_admins(bot, settings.admin_ids, text)
        await callback.message.answer(
            "✅ Вы успешно зарегистрированы!\n"
            f"Ивент: <b>{escape(event.title)}</b>\n"
            "Мы отправим напоминание за 24 часа до дедлайна и пришлем результаты после завершения."
        )
        await callback.answer("Готово.")
    else:
        await callback.answer("Вы уже зарегистрированы в этом ивенте.")

    keyboard = event_keyboard(
        event=event,
        participation=participation,
        has_submission=has_submission,
        is_open_now=True,
        is_started=True,
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)


def _extract_id(data: str | None) -> int | None:
    if not data:
        return None
    chunk = data.rsplit(":", 1)[-1]
    return int(chunk) if chunk.isdigit() else None
