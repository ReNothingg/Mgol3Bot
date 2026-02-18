from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import SubmissionType
from app.db.repo import Repo
from app.db.session import session_scope
from app.keyboards.admin import (
    admin_create_type_keyboard,
    admin_delete_confirm_keyboard,
    admin_event_manage_keyboard,
    admin_events_list_keyboard,
    admin_main_keyboard,
)
from app.services.datetime_utils import DATETIME_INPUT_FORMAT, parse_datetime_utc
from app.services.notifier import send_submission_to_admins
from app.services.render import event_manage_text

router = Router(name="admin")


class CreateEventFSM(StatesGroup):
    waiting_type = State()
    waiting_title = State()
    waiting_description = State()
    waiting_start = State()
    waiting_end = State()
    waiting_prize_places = State()


class DeadlineFSM(StatesGroup):
    waiting_new_deadline = State()


class WinnersFSM(StatesGroup):
    waiting_winners = State()


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    settings: Settings,
) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        await message.answer("Команда доступна только администраторам.")
        return
    await message.answer("Админ-панель", reply_markup=admin_main_keyboard())


@router.callback_query(lambda c: c.data == "admin:menu")
async def admin_menu(callback: CallbackQuery, settings: Settings) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    if callback.message:
        await callback.message.answer("Админ-панель", reply_markup=admin_main_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.answer("Действие отменено.", reply_markup=admin_main_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:create")
async def admin_create_start(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(CreateEventFSM.waiting_type)
    if callback.message:
        await callback.message.answer(
            "Выберите шаблон ивента:",
            reply_markup=admin_create_type_keyboard(),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:create:type:"))
async def admin_create_pick_type(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    type_raw = callback.data.rsplit(":", 1)[-1] if callback.data else ""
    try:
        submission_type = SubmissionType(type_raw)
    except ValueError:
        await callback.answer("Некорректный шаблон.")
        return

    await state.set_state(CreateEventFSM.waiting_title)
    await state.update_data(submission_type=submission_type.value)
    if callback.message:
        await callback.message.answer("Введите название ивента:")
    await callback.answer()


@router.message(CreateEventFSM.waiting_title)
async def admin_create_title(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Название слишком короткое. Введите минимум 3 символа.")
        return
    await state.set_state(CreateEventFSM.waiting_description)
    await state.update_data(title=title)
    await message.answer("Введите описание ивента:")


@router.message(CreateEventFSM.waiting_description)
async def admin_create_description(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    description = (message.text or "").strip()
    if len(description) < 5:
        await message.answer("Описание слишком короткое. Введите минимум 5 символов.")
        return
    await state.set_state(CreateEventFSM.waiting_start)
    await state.update_data(description=description)
    await message.answer(
        f"Введите дату начала в формате {DATETIME_INPUT_FORMAT} (UTC).\n"
        "Пример: 20.02.2026 12:00"
    )


@router.message(CreateEventFSM.waiting_start)
async def admin_create_start_dt(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    start_at = parse_datetime_utc(message.text or "")
    if start_at is None:
        await message.answer(f"Неверный формат. Используйте {DATETIME_INPUT_FORMAT}.")
        return
    await state.set_state(CreateEventFSM.waiting_end)
    await state.update_data(start_at=start_at.isoformat())
    await message.answer(
        f"Введите дату окончания в формате {DATETIME_INPUT_FORMAT} (UTC).\n"
        "Дата окончания должна быть позже старта."
    )


@router.message(CreateEventFSM.waiting_end)
async def admin_create_end_dt(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    end_at = parse_datetime_utc(message.text or "")
    if end_at is None:
        await message.answer(f"Неверный формат. Используйте {DATETIME_INPUT_FORMAT}.")
        return
    data = await state.get_data()
    start_at_raw = data.get("start_at")
    try:
        start_at = datetime.fromisoformat(start_at_raw)
    except Exception:
        await state.clear()
        await message.answer("Сессия создания сброшена. Начните заново через /admin.")
        return
    if end_at <= start_at:
        await message.answer("Дата окончания должна быть позже даты начала.")
        return
    await state.set_state(CreateEventFSM.waiting_prize_places)
    await state.update_data(end_at=end_at.isoformat())
    await message.answer("Сколько призовых мест? Введите число (например, 3).")


@router.message(CreateEventFSM.waiting_prize_places)
async def admin_create_prize_places(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите целое число.")
        return
    prize_places = int(raw)
    if not (1 <= prize_places <= 50):
        await message.answer("Введите число от 1 до 50.")
        return

    data = await state.get_data()
    try:
        submission_type = SubmissionType(data["submission_type"])
        title = str(data["title"])
        description = str(data["description"])
        start_at = datetime.fromisoformat(str(data["start_at"]))
        end_at = datetime.fromisoformat(str(data["end_at"]))
    except Exception:
        await state.clear()
        await message.answer("Сессия создания сброшена. Начните заново через /admin.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.create_event(
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            prize_places=prize_places,
            submission_type=submission_type,
            created_by_admin_id=message.from_user.id,
        )

    await state.clear()
    deep_link = f"https://t.me/{settings.bot_username}?start=join_{event.id}"
    extra = (
        f"\nСсылка быстрого участия: {deep_link}"
        if submission_type == SubmissionType.NONE
        else ""
    )
    await message.answer(
        f"Ивент создан.\nID: {event.id}\nНазвание: {escape(event.title)}{extra}",
        reply_markup=admin_main_keyboard(),
    )


@router.callback_query(lambda c: c.data == "admin:list")
async def admin_list_events(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        events = await repo.list_all_events()

    if callback.message:
        if not events:
            await callback.message.answer("Ивентов пока нет.", reply_markup=admin_main_keyboard())
        else:
            await callback.message.answer(
                "Список ивентов:",
                reply_markup=admin_events_list_keyboard(events),
            )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:toggle:"))
async def admin_toggle_event(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.toggle_event_active(event_id)

    if event is None:
        await callback.answer("Ивент не найден.", show_alert=True)
        return
    if callback.message:
        await callback.message.answer(
            event_manage_text(event),
            reply_markup=admin_event_manage_keyboard(event.id, event.is_active),
        )
    await callback.answer("Статус ивента обновлен.")


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:deleteask:"))
async def admin_delete_ask(callback: CallbackQuery, settings: Settings) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return
    if callback.message:
        await callback.message.answer(
            "Подтвердите удаление ивента.",
            reply_markup=admin_delete_confirm_keyboard(event_id),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:deleteyes:"))
async def admin_delete_yes(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        deleted = await repo.delete_event(event_id)

    if callback.message:
        if deleted:
            await callback.message.answer("Ивент удален.", reply_markup=admin_main_keyboard())
        else:
            await callback.message.answer("Ивент не найден.")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:deadline:"))
async def admin_deadline_start(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return
    await state.set_state(DeadlineFSM.waiting_new_deadline)
    await state.update_data(deadline_event_id=event_id)
    if callback.message:
        await callback.message.answer(
            f"Введите новый дедлайн в формате {DATETIME_INPUT_FORMAT} (UTC)."
        )
    await callback.answer()


@router.message(DeadlineFSM.waiting_new_deadline)
async def admin_deadline_finish(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    new_deadline = parse_datetime_utc(message.text or "")
    if new_deadline is None:
        await message.answer(f"Неверный формат. Используйте {DATETIME_INPUT_FORMAT}.")
        return
    if new_deadline <= datetime.now(timezone.utc):
        await message.answer("Дедлайн должен быть в будущем.")
        return

    data = await state.get_data()
    event_id = data.get("deadline_event_id")
    if not isinstance(event_id, int):
        await state.clear()
        await message.answer("Сессия изменена. Начните заново.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.update_event_deadline(event_id, new_deadline)

    await state.clear()
    if event is None:
        await message.answer("Ивент не найден.")
        return
    await message.answer(
        "Дедлайн обновлен.",
        reply_markup=admin_event_manage_keyboard(event.id, event.is_active),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:winners:"))
async def admin_winners_start(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)

    if event is None:
        await callback.answer("Ивент не найден.", show_alert=True)
        return

    await state.set_state(WinnersFSM.waiting_winners)
    await state.update_data(winners_event_id=event_id, winners_max=event.prize_places)
    if callback.message:
        await callback.message.answer(
            "Отправьте Telegram ID победителей через пробел "
            f"(макс. {event.prize_places}), в порядке мест.\n"
            "Пример: 123456789 987654321"
        )
    await callback.answer()


@router.message(WinnersFSM.waiting_winners)
async def admin_winners_finish(
    message: Message,
    state: FSMContext,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return

    data = await state.get_data()
    event_id = data.get("winners_event_id")
    winners_max = data.get("winners_max")
    if not isinstance(event_id, int) or not isinstance(winners_max, int):
        await state.clear()
        await message.answer("Сессия изменена. Начните заново.")
        return

    winner_tg_ids = _parse_ids(message.text or "")
    if not winner_tg_ids:
        await message.answer("Не удалось распознать ID. Повторите ввод.")
        return
    winner_tg_ids = winner_tg_ids[:winners_max]

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        assigned, missing = await repo.set_winners_by_tg_ids(
            event_id=event_id,
            winner_tg_ids=winner_tg_ids,
        )

    await state.clear()
    missing_text = ", ".join(str(x) for x in missing) if missing else "нет"
    await message.answer(
        "Победители обновлены.\n"
        f"Назначено мест: {len(assigned)}\n"
        f"ID без участия в ивенте: {missing_text}"
    )


@router.callback_query(lambda c: c.data and c.data.startswith("admin:event:export:"))
async def admin_export_submissions(
    callback: CallbackQuery,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return

    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)
        if event is None:
            await callback.answer("Ивент не найден.", show_alert=True)
            return
        submissions = await repo.list_event_submissions(event.id)

    for idx, record in enumerate(submissions, start=1):
        username = f"@{record.user.username}" if record.user.username else "без username"
        caption = (
            f"Экспорт работ | <b>{escape(event.title)}</b>\n"
            f"Работа #{idx}\n"
            f"Пользователь: {escape(record.user.full_name)} ({username})\n"
            f"Telegram ID: <code>{record.user.tg_id}</code>"
        )
        await send_submission_to_admins(
            bot,
            admin_ids=settings.admin_ids,
            submission_type=record.submission.submission_type,
            caption=caption,
            file_id=record.submission.file_id,
            text_content=record.submission.text_content,
        )

    if callback.message:
        await callback.message.answer(
            f"Выгрузка завершена. Отправлено работ: {len(submissions)}."
        )
    await callback.answer("Готово.")


@router.callback_query(
    lambda c: c.data
    and re.fullmatch(r"admin:event:\d+", c.data or "") is not None
)
async def admin_event_manage(
    callback: CallbackQuery,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if callback.from_user is None or not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    event_id = _extract_id(callback.data)
    if event_id is None:
        await callback.answer("Некорректный ID.")
        return
    async with session_scope(session_factory) as session:
        repo = Repo(session)
        event = await repo.get_event(event_id)

    if event is None:
        await callback.answer("Ивент не найден.", show_alert=True)
        return
    if callback.message:
        await callback.message.answer(
            event_manage_text(event),
            reply_markup=admin_event_manage_keyboard(event.id, event.is_active),
        )
    await callback.answer()


@router.message(F.text == "/cancel")
async def admin_cancel_message(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None or not _is_admin(message.from_user.id, settings):
        return
    await state.clear()
    await message.answer("Текущее действие отменено.", reply_markup=admin_main_keyboard())


def _extract_id(data: str | None) -> int | None:
    if not data:
        return None
    chunk = data.rsplit(":", 1)[-1]
    return int(chunk) if chunk.isdigit() else None


def _parse_ids(text: str) -> list[int]:
    values = re.findall(r"-?\d+", text)
    result: list[int] = []
    seen: set[int] = set()
    for raw in values:
        value = int(raw)
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result

