from __future__ import annotations

import asyncio
from datetime import timedelta
from html import escape
import random

from aiogram import Bot

from app.config import Settings
from app.db.models import Event, Participation, SubmissionType
from app.db.repo import Repo
from app.db.session import session_scope
from app.services.notifier import notify_user, send_submission_to_admins
from app.services.render import format_dt
from app.services.time_utils import utcnow_naive


class EventCloser:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory,
        interval_seconds: int = 60,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self, bot: Bot) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._loop(bot))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self, bot: Bot) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_start_notifications(bot)
                await self.process_deadline_reminders(bot)
                await self.process_expired_events(bot)
            except Exception:
                # Keep loop alive and retry on the next interval.
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def process_start_notifications(self, bot: Bot) -> None:
        now = utcnow_naive()
        async with session_scope(self.session_factory) as session:
            repo = Repo(session)
            events = await repo.list_events_for_start_notify(now)
            for event in events:
                participations = await repo.list_event_participations(event.id)
                if participations:
                    text = (
                        f"🚀 <b>Ивент начался</b>: {escape(event.title)}\n"
                        f"Дедлайн: {format_dt(event.end_at)}\n\n"
                        "Откройте карточку ивента в боте, чтобы проверить условия."
                    )
                    await self._notify_participants(bot, participations, text)
                await repo.mark_event_start_notified(event.id)

    async def process_deadline_reminders(self, bot: Bot) -> None:
        now = utcnow_naive()
        border = now + timedelta(hours=24)
        async with session_scope(self.session_factory) as session:
            repo = Repo(session)
            events = await repo.list_events_for_24h_reminder(now, border)
            for event in events:
                participations = await repo.list_event_participations(event.id)
                if participations:
                    text = self._build_deadline_reminder_text(event)
                    await self._notify_participants(bot, participations, text)
                await repo.mark_event_24h_reminder_notified(event.id)

    async def process_expired_events(self, bot: Bot) -> None:
        now = utcnow_naive()
        async with session_scope(self.session_factory) as session:
            repo = Repo(session)
            events = await repo.list_expired_events_for_notify(now)
            for event in events:
                participations = await repo.list_event_participations(event.id)
                if event.submission_type == SubmissionType.NONE:
                    winners = await self._process_random_only_event(
                        bot=bot,
                        repo=repo,
                        event=event,
                        participations=participations,
                    )
                    participations = await repo.list_event_participations(event.id)
                    winner_tg_ids = await self._notify_winners_directly(
                        bot=bot,
                        event=event,
                        winners=winners,
                    )
                    await self._announce_results_to_participants(
                        bot=bot,
                        event=event,
                        participations=participations,
                        winners=winners,
                        skip_tg_ids=winner_tg_ids,
                    )
                else:
                    await self._process_submission_event(bot=bot, repo=repo, event=event)
                    winners = sorted(
                        [x for x in participations if x.winner_place is not None],
                        key=lambda x: x.winner_place or 9999,
                    )
                    await self._announce_results_to_participants(
                        bot=bot,
                        event=event,
                        participations=participations,
                        winners=winners,
                        skip_tg_ids=set(),
                    )

                await repo.mark_event_closed_notified(event.id)

    async def _process_random_only_event(
        self,
        *,
        bot: Bot,
        repo: Repo,
        event: Event,
        participations: list[Participation],
    ) -> list[Participation]:
        winners = sorted(
            [x for x in participations if x.winner_place is not None],
            key=lambda x: x.winner_place or 9999,
        )
        if not winners and participations:
            winners_count = min(event.prize_places, len(participations))
            winner_tg_ids = [
                item.user.tg_id
                for item in random.sample(participations, k=winners_count)
            ]
            await repo.set_winners_by_tg_ids(
                event_id=event.id,
                winner_tg_ids=winner_tg_ids,
            )
            participations = await repo.list_event_participations(event.id)
            winners = sorted(
                [x for x in participations if x.winner_place is not None],
                key=lambda x: x.winner_place or 9999,
            )

        summary = (
            f"🏁 <b>Ивент завершен</b>: {escape(event.title)}\n"
            f"Период: {format_dt(event.start_at)} — {format_dt(event.end_at)}\n"
            f"Формат: случайный розыгрыш среди участников\n"
            f"Всего участников: {len(participations)}"
        )
        await self._send_admin_text(bot, summary)

        if not winners:
            await self._send_admin_text(
                bot,
                "Победители не выбраны: недостаточно участников.",
            )
            return winners

        lines = [f"🎉 <b>Победители ивента «{escape(event.title)}»</b>"]
        for winner in winners:
            username = (
                f"@{winner.user.username}"
                if winner.user and winner.user.username
                else "без username"
            )
            full_name = winner.user.full_name if winner.user else "Unknown"
            lines.append(
                f"{winner.winner_place} место — {escape(full_name)} ({escape(username)}), "
                f"ID: <code>{winner.user.tg_id if winner.user else 'n/a'}</code>"
            )
        await self._send_admin_text(bot, "\n".join(lines))
        return winners

    async def _process_submission_event(self, *, bot: Bot, repo: Repo, event: Event) -> None:
        submissions = await repo.list_event_submissions(event.id)
        summary = (
            f"🏁 <b>Ивент завершен</b>: {escape(event.title)}\n"
            f"Период: {format_dt(event.start_at)} — {format_dt(event.end_at)}\n"
            f"Получено работ: {len(submissions)}"
        )
        await self._send_admin_text(bot, summary)

        for idx, record in enumerate(submissions, start=1):
            username = f"@{record.user.username}" if record.user.username else "без username"
            caption = (
                f"Ивент: <b>{escape(event.title)}</b>\n"
                f"Работа #{idx}\n"
                f"Пользователь: {escape(record.user.full_name)} ({username})\n"
                f"Telegram ID: <code>{record.user.tg_id}</code>"
            )
            await send_submission_to_admins(
                bot,
                admin_ids=self.settings.admin_ids,
                submission_type=record.submission.submission_type,
                caption=caption,
                file_id=record.submission.file_id,
                text_content=record.submission.text_content,
            )

    async def _notify_winners_directly(
        self,
        *,
        bot: Bot,
        event: Event,
        winners: list[Participation],
    ) -> set[int]:
        notified: set[int] = set()
        for winner in winners:
            if winner.user is None:
                continue
            text = (
                f"🎉 <b>Поздравляем!</b>\n"
                f"Вы заняли <b>{winner.winner_place} место</b> в ивенте "
                f"«{escape(event.title)}».\n\n"
                "С вами свяжутся администраторы по поводу приза."
            )
            sent = await notify_user(bot, winner.user.tg_id, text)
            if sent:
                notified.add(winner.user.tg_id)
        return notified

    async def _announce_results_to_participants(
        self,
        *,
        bot: Bot,
        event: Event,
        participations: list[Participation],
        winners: list[Participation],
        skip_tg_ids: set[int],
    ) -> None:
        if not participations:
            return

        winner_lines = []
        winner_tg_ids: set[int] = set()
        for winner in winners:
            if winner.user is None:
                continue
            winner_tg_ids.add(winner.user.tg_id)
            username = f"@{winner.user.username}" if winner.user.username else "без username"
            winner_lines.append(
                f"{winner.winner_place} место — {escape(winner.user.full_name)} ({escape(username)})"
            )
        winners_text = "\n".join(winner_lines) if winner_lines else "Пока не назначены."

        for participation in participations:
            user = participation.user
            if user is None or user.tg_id in skip_tg_ids:
                continue

            if winners and participation.winner_place:
                text = (
                    f"🎉 <b>Итоги ивента «{escape(event.title)}»</b>\n"
                    f"Вы заняли <b>{participation.winner_place} место</b>."
                )
            elif winners and user.tg_id not in winner_tg_ids:
                text = (
                    f"🏁 <b>Итоги ивента «{escape(event.title)}»</b>\n"
                    "Спасибо за участие!\n\n"
                    f"Победители:\n{winners_text}"
                )
            else:
                text = (
                    f"🏁 Ивент «{escape(event.title)}» завершен.\n"
                    "Результаты будут объявлены отдельно администраторами."
                )
            await notify_user(bot, user.tg_id, text)

    async def _notify_participants(
        self,
        bot: Bot,
        participations: list[Participation],
        text: str,
    ) -> None:
        for participation in participations:
            if participation.user is None:
                continue
            await notify_user(bot, participation.user.tg_id, text)

    def _build_deadline_reminder_text(self, event: Event) -> str:
        if event.submission_type == SubmissionType.NONE:
            return (
                f"⏰ <b>Напоминание по ивенту «{escape(event.title)}»</b>\n"
                f"До завершения осталось меньше 24 часов.\n"
                f"Дедлайн: {format_dt(event.end_at)}"
            )
        return (
            f"⏰ <b>Напоминание по ивенту «{escape(event.title)}»</b>\n"
            f"До дедлайна меньше 24 часов.\n"
            f"Дедлайн: {format_dt(event.end_at)}\n\n"
            "Если вы еще не отправили работу, успейте сделать это вовремя."
        )

    async def _send_admin_text(self, bot: Bot, text: str) -> None:
        for admin_id in self.settings.admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                continue
