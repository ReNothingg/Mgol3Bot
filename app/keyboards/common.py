from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Event, Participation, SubmissionType


def subscription_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url=channel_url)
    kb.button(text="✅ Проверить подписку", callback_data="sub:check")
    kb.adjust(1)
    return kb.as_markup()


def main_menu_keyboard(events: list[Event]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not events:
        kb.button(text="📭 Сейчас нет активных ивентов", callback_data="event:noop")
    for event in events:
        kb.button(text=f"🎯 {event.title}", callback_data=f"event:open:{event.id}")
    kb.adjust(1)
    return kb.as_markup()


def event_keyboard(
    *,
    event: Event,
    participation: Participation | None,
    has_submission: bool,
    is_open_now: bool,
    is_started: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if participation is None:
        if is_open_now:
            kb.button(text="✅ Принять участие", callback_data=f"event:join:{event.id}")
        elif not is_started:
            kb.button(text="⏳ Ивент еще не начался", callback_data="event:noop")
        else:
            kb.button(text="⛔ Ивент закрыт", callback_data="event:noop")
    else:
        if event.submission_type == SubmissionType.NONE:
            kb.button(text="✅ Вы участвуете", callback_data="event:noop")
        elif has_submission:
            kb.button(text="✅ Работа отправлена", callback_data="event:noop")
        else:
            if not is_started:
                kb.button(text="⏳ Прием работ еще не начался", callback_data="event:noop")
            elif not is_open_now:
                kb.button(text="⛔ Прием работ завершен", callback_data="event:noop")
            else:
                text_by_type = {
                    SubmissionType.PHOTO: "📷 Отправить фото",
                    SubmissionType.DOCUMENT: "📎 Отправить файл",
                    SubmissionType.TEXT: "💬 Отправить сообщение",
                }
                kb.button(
                    text=text_by_type.get(event.submission_type, "Отправить работу"),
                    callback_data=f"event:submit:{event.id}",
                )
    kb.button(text="⬅️ Главное меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def submission_cancel_keyboard(event_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=f"event:cancel:{event_id}")
    return kb.as_markup()


def my_events_keyboard(participations: list[Participation]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for participation in participations:
        event = participation.event
        kb.button(text=f"🎯 {event.title}", callback_data=f"event:open:{event.id}")
    kb.button(text="⬅️ Главное меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()
