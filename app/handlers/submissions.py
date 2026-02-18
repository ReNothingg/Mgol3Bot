from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import SubmissionType
from app.db.repo import Repo
from app.db.session import session_scope
from app.handlers.common import ensure_subscribed
from app.keyboards.common import submission_cancel_keyboard
from app.services.notifier import send_submission_to_admins

router = Router(name="submissions")


class SubmissionFlow(StatesGroup):
    waiting_material = State()


@router.callback_query(lambda c: c.data and c.data.startswith("event:submit:"))
async def ask_for_submission(
    callback: CallbackQuery,
    state: FSMContext,
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
        await callback.answer("Некорректный ID.")
        return

    now = datetime.now(timezone.utc)
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await callback.answer("Ивент не найден.")
            return
        if not (event.is_active and event.start_at <= now <= event.end_at):
            await callback.answer("Ивент уже закрыт.", show_alert=True)
            return

        participation = await repo.get_participation(
            user_tg_id=callback.from_user.id,
            event_id=event.id,
        )
        if participation is None:
            await callback.answer("Сначала нажмите «Принять участие».", show_alert=True)
            return
        existing = await repo.get_submission(participation.id)
        if existing is not None:
            await callback.answer("Вы уже отправили работу.", show_alert=True)
            return
        if event.submission_type == SubmissionType.NONE:
            await callback.answer("Для этого ивента отправка не требуется.")
            return

        await state.set_state(SubmissionFlow.waiting_material)
        await state.update_data(event_id=event.id, submission_type=event.submission_type.value)

    prompt = _prompt_by_type(event.submission_type)
    await callback.message.answer(prompt, reply_markup=submission_cancel_keyboard(event.id))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("event:cancel:"))
async def cancel_submission(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Отправка отменена.")
    await callback.answer()


@router.message(SubmissionFlow.waiting_material, F.photo | F.document | F.text)
async def handle_submission_material(
    message: Message,
    state: FSMContext,
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

    data = await state.get_data()
    event_id = data.get("event_id")
    type_raw = data.get("submission_type")
    if not isinstance(event_id, int) or not isinstance(type_raw, str):
        await state.clear()
        await message.answer("Сессия отправки сброшена. Нажмите кнопку заново.")
        return

    try:
        submission_type = SubmissionType(type_raw)
    except ValueError:
        await state.clear()
        await message.answer("Сессия отправки сброшена. Нажмите кнопку заново.")
        return

    file_id: str | None = None
    text_content: str | None = None

    if submission_type == SubmissionType.PHOTO:
        if not message.photo:
            await message.answer("Нужно отправить именно фото.")
            return
        file_id = message.photo[-1].file_id
    elif submission_type == SubmissionType.DOCUMENT:
        if not message.document:
            await message.answer("Нужно отправить именно файл.")
            return
        file_id = message.document.file_id
    elif submission_type == SubmissionType.TEXT:
        if not message.text:
            await message.answer("Нужно отправить именно текстовое сообщение.")
            return
        text_content = message.text.strip()
        if not text_content:
            await message.answer("Текст не должен быть пустым.")
            return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await state.clear()
            await message.answer("Ивент не найден.")
            return
        participation = await repo.get_participation(
            user_tg_id=message.from_user.id,
            event_id=event.id,
        )
        if participation is None:
            await state.clear()
            await message.answer("Вы не зарегистрированы в этом ивенте.")
            return

        saved = await repo.save_submission(
            participation_id=participation.id,
            submission_type=submission_type,
            file_id=file_id,
            text_content=text_content,
        )
        if saved is None:
            await state.clear()
            await message.answer("Работа уже была отправлена ранее (максимум 1).")
            return

    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    caption = (
        f"Новая работа по ивенту <b>{escape(event.title)}</b>\n"
        f"Пользователь: {escape(username)}\n"
        f"Telegram ID: <code>{message.from_user.id}</code>"
    )
    await send_submission_to_admins(
        bot,
        admin_ids=settings.admin_ids,
        submission_type=submission_type,
        caption=caption,
        file_id=file_id,
        text_content=text_content,
    )
    await state.clear()
    await message.answer("Работа принята и отправлена администраторам.")


@router.message(SubmissionFlow.waiting_material)
async def wrong_submission_material(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    type_raw = data.get("submission_type")
    try:
        expected = SubmissionType(type_raw)
    except Exception:
        await message.answer("Ожидаю материал по выбранному формату.")
        return
    await message.answer(_short_hint(expected))


def _extract_id(data: str | None) -> int | None:
    if not data:
        return None
    chunk = data.rsplit(":", 1)[-1]
    return int(chunk) if chunk.isdigit() else None


def _prompt_by_type(submission_type: SubmissionType) -> str:
    if submission_type == SubmissionType.PHOTO:
        return (
            "Отправьте мне фото (макс. 1).\n"
            "Качество должно быть четким, если работа на бумаге.\n"
            "Электронные рисунки тоже принимаются."
        )
    if submission_type == SubmissionType.DOCUMENT:
        return (
            "Отправьте файл (макс. 1).\n"
            "Убедитесь, что файл открывается и содержит финальную версию работы."
        )
    if submission_type == SubmissionType.TEXT:
        return "Отправьте одно текстовое сообщение с вашей работой."
    return "Отправка материала для этого ивента не требуется."


def _short_hint(submission_type: SubmissionType) -> str:
    if submission_type == SubmissionType.PHOTO:
        return "Сейчас ожидается фото. Отправьте фото или нажмите «Отмена»."
    if submission_type == SubmissionType.DOCUMENT:
        return "Сейчас ожидается файл. Отправьте документ или нажмите «Отмена»."
    if submission_type == SubmissionType.TEXT:
        return "Сейчас ожидается текстовое сообщение. Отправьте текст или нажмите «Отмена»."
    return "Ожидается материал по ивенту."
