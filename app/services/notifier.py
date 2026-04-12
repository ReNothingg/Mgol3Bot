from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.db.models import SubmissionAttachment, SubmissionAttachmentKind, SubmissionType


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


async def _send_attachment(
    bot: Bot,
    *,
    admin_id: int,
    attachment: SubmissionAttachment,
    caption: str | None = None,
) -> None:
    if attachment.kind == SubmissionAttachmentKind.DOCUMENT:
        await bot.send_document(admin_id, document=attachment.file_id, caption=caption)
        return
    await bot.send_photo(admin_id, photo=attachment.file_id, caption=caption)


async def send_submission_to_admin(
    bot: Bot,
    *,
    admin_id: int,
    submission_type: SubmissionType,
    caption: str,
    attachments: list[SubmissionAttachment] | None,
    text_content: str | None,
) -> None:
    if submission_type != SubmissionType.TEXT and attachments:
        first_attachment, *other_attachments = attachments
        await _send_attachment(
            bot,
            admin_id=admin_id,
            attachment=first_attachment,
            caption=caption,
        )
        for attachment in other_attachments:
            await _send_attachment(
                bot,
                admin_id=admin_id,
                attachment=attachment,
            )
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
    attachments: list[SubmissionAttachment] | None,
    text_content: str | None,
) -> None:
    for admin_id in admin_ids:
        try:
            await send_submission_to_admin(
                bot,
                admin_id=admin_id,
                submission_type=submission_type,
                caption=caption,
                attachments=attachments,
                text_content=text_content,
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            continue
