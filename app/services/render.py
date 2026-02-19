from __future__ import annotations

from datetime import datetime
from html import escape

from app.db.models import Event, Participation, SubmissionType


def format_dt(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M UTC")


def submission_type_human(submission_type: SubmissionType) -> str:
    mapping = {
        SubmissionType.PHOTO: "Нужно отправить 1 фото",
        SubmissionType.DOCUMENT: "Нужно отправить 1 файл",
        SubmissionType.TEXT: "Нужно отправить 1 текстовое сообщение",
        SubmissionType.NONE: "Только регистрация участия (без отправки работы)",
    }
    return mapping.get(submission_type, "Формат не указан")


def main_description(
    *,
    bot_name: str,
    channel_name: str,
    channel_url: str,
    developer_url: str,
) -> str:
    return (
        f"🎉 <b>{escape(bot_name)}</b>\n\n"
        f"Платформа конкурсов и ивентов канала "
        f"<a href=\"{escape(channel_url)}\">{escape(channel_name)}</a>\n\n"
        "Как пользоваться:\n"
        "1. Откройте активный ивент\n"
        "2. Нажмите «Принять участие»\n"
        "3. Выполните условия и отправьте работу\n\n"
        "Команда /my показывает ваши участия и результаты.\n"
        f"Контакт разработчика: <a href=\"{escape(developer_url)}\">{escape(developer_url)}</a>\n\n"
        "Выберите ивент ниже:"
    )


def event_card_text(event: Event) -> str:
    extra = ""
    if event.submission_type == SubmissionType.NONE:
        extra = (
            "\n\n🎲 Победители определяются случайно среди всех участников "
            "после завершения ивента."
        )
    return (
        f"🏆 <b>{escape(event.title)}</b>\n\n"
        f"🕒 <b>Старт:</b> {format_dt(event.start_at)}\n"
        f"🕒 <b>Финиш:</b> {format_dt(event.end_at)}\n\n"
        f"📌 <b>Описание</b>\n{escape(event.description)}\n\n"
        f"🥇 <b>Призовых мест:</b> {event.prize_places}\n"
        f"🧩 <b>Формат:</b> {escape(submission_type_human(event.submission_type))}"
        f"{extra}"
    )


def my_events_text(participations: list[Participation]) -> str:
    if not participations:
        return "У вас пока нет участий в ивентах."

    lines = ["📁 <b>Мои ивенты</b>", ""]
    for item in participations:
        event = item.event
        if item.winner_place:
            result = f"🏆 {item.winner_place} место"
        else:
            result = "⏳ результат не объявлен"
        lines.append(f"• {escape(event.title)} — {result}")
    lines.append("")
    lines.append("Нажмите на ивент ниже, чтобы открыть карточку.")
    return "\n".join(lines)


def event_manage_text(event: Event) -> str:
    state = "🟢 активен" if event.is_active else "🔴 неактивен"
    return (
        f"🛠 <b>Управление ивентом</b>\n\n"
        f"ID: <code>{event.id}</code>\n"
        f"Название: <b>{escape(event.title)}</b>\n"
        f"Статус: {state}\n"
        f"Старт: {format_dt(event.start_at)}\n"
        f"Финиш: {format_dt(event.end_at)}\n"
        f"Формат: {escape(submission_type_human(event.submission_type))}\n"
        f"Призовых мест: {event.prize_places}"
    )
