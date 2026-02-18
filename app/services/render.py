from __future__ import annotations

from datetime import datetime
from html import escape

from app.db.models import Event, Participation, SubmissionType


def format_dt(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M UTC")


def submission_type_human(submission_type: SubmissionType) -> str:
    mapping = {
        SubmissionType.PHOTO: "Нужно отправить фото",
        SubmissionType.DOCUMENT: "Нужно отправить файл",
        SubmissionType.TEXT: "Нужно отправить сообщение",
        SubmissionType.NONE: "Дополнительная отправка не требуется",
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
        f"<b>{escape(bot_name)}</b>\n\n"
        f"Привет! Это бот розыгрышей и конкурсов от <a href=\"{escape(channel_url)}\">{escape(channel_name)}</a>\n\n"
        f"Напишите команду /my, чтобы узнать в каких конкурсах ты принял участие!\n\n"
        f"По всем вопросам: <a href=\"{escape(developer_url)}\">{escape(developer_url)}</a>\n"
        "Ниже выберите активный ивент."
    )


def event_card_text(event: Event) -> str:
    return (
        f"<b>{escape(event.title)}</b>\n\n"
        f"Дата начала: {format_dt(event.start_at)}\n"
        f"Дата окончания: {format_dt(event.end_at)}\n\n"
        f"{escape(event.description)}\n\n"
        f"Призовые места: всего {event.prize_places}\n"
        f"Формат участия: {escape(submission_type_human(event.submission_type))}"
    )


def my_events_text(participations: list[Participation]) -> str:
    if not participations:
        return "Вы еще не участвуете ни в одном ивенте."

    lines = ["<b>Мои ивенты</b>", ""]
    for item in participations:
        event = item.event
        if item.winner_place:
            result = f"выигрыш: {item.winner_place} место"
        else:
            result = "выигрыш: не отмечен"
        lines.append(f"• {escape(event.title)} — {result}")
    lines.append("")
    lines.append("Нажмите на ивент ниже, чтобы открыть его карточку.")
    return "\n".join(lines)


def event_manage_text(event: Event) -> str:
    state = "активен" if event.is_active else "неактивен"
    return (
        f"<b>Управление ивентом</b>\n\n"
        f"ID: {event.id}\n"
        f"Название: {escape(event.title)}\n"
        f"Статус: {state}\n"
        f"Старт: {format_dt(event.start_at)}\n"
        f"Финиш: {format_dt(event.end_at)}\n"
        f"Формат: {escape(submission_type_human(event.submission_type))}\n"
        f"Призовые места: {event.prize_places}"
    )
