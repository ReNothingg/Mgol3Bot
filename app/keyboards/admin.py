from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import Event, SubmissionType


def admin_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать ивент", callback_data="admin:create")
    kb.button(text="📋 Список ивентов", callback_data="admin:list")
    kb.adjust(1)
    return kb.as_markup()


def admin_create_type_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="1) 📷 Отправить фото", callback_data=f"admin:create:type:{SubmissionType.PHOTO.value}")
    kb.button(text="2) 📎 Отправить файл", callback_data=f"admin:create:type:{SubmissionType.DOCUMENT.value}")
    kb.button(text="3) 🎲 Просто участие", callback_data=f"admin:create:type:{SubmissionType.NONE.value}")
    kb.button(text="4) 💬 Отправить сообщение", callback_data=f"admin:create:type:{SubmissionType.TEXT.value}")
    kb.button(text="❌ Отмена", callback_data="admin:cancel")
    kb.adjust(1)
    return kb.as_markup()


def admin_events_list_keyboard(events: list[Event]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for event in events:
        state = "🟢" if event.is_active else "🔴"
        kb.button(text=f"{state} {event.title}", callback_data=f"admin:event:{event.id}")
    kb.button(text="Назад", callback_data="admin:menu")
    kb.adjust(1)
    return kb.as_markup()


def admin_event_manage_keyboard(event_id: int, is_active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="⏸ Деактивировать" if is_active else "▶️ Активировать",
        callback_data=f"admin:event:toggle:{event_id}",
    )
    kb.button(text="🗓 Изменить дедлайн", callback_data=f"admin:event:deadline:{event_id}")
    kb.button(text="🏆 Назначить победителей", callback_data=f"admin:event:winners:{event_id}")
    kb.button(text="📤 Выгрузить работы админам", callback_data=f"admin:event:export:{event_id}")
    kb.button(text="🗑 Удалить ивент", callback_data=f"admin:event:deleteask:{event_id}")
    kb.button(text="⬅️ К списку ивентов", callback_data="admin:list")
    kb.adjust(1)
    return kb.as_markup()


def admin_delete_confirm_keyboard(event_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"admin:event:deleteyes:{event_id}")
    kb.button(text="❌ Отмена", callback_data=f"admin:event:{event_id}")
    kb.adjust(1)
    return kb.as_markup()
