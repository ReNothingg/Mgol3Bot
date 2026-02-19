from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.db.models import SubmissionType


async def notify_admins(bot: Bot, admin_ids: list[int], text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except (TelegramBadRequest, TelegramForbiddenError):
            continue


async def notify_user(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return True


async def send_submission_to_admin(
    bot: Bot,
    *,
    admin_id: int,
    submission_type: SubmissionType,
    caption: str,
    file_id: str | None,
    text_content: str | None,
) -> None:
    if submission_type == SubmissionType.PHOTO and file_id:
        await bot.send_photo(admin_id, photo=file_id, caption=caption)
        return
    if submission_type == SubmissionType.DOCUMENT and file_id:
        await bot.send_document(admin_id, document=file_id, caption=caption)
        return
    if submission_type == SubmissionType.TEXT:
        payload = text_content or "(пусто)"
        await bot.send_message(admin_id, f"{caption}\n\nТекст:\n{payload}")
        return
    await bot.send_message(admin_id, caption)


async def send_submission_to_admins(
    bot: Bot,
    *,
    admin_ids: list[int],
    submission_type: SubmissionType,
    caption: str,
    file_id: str | None,
    text_content: str | None,
) -> None:
    for admin_id in admin_ids:
        try:
            await send_submission_to_admin(
                bot,
                admin_id=admin_id,
                submission_type=submission_type,
                caption=caption,
                file_id=file_id,
                text_content=text_content,
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            continue
