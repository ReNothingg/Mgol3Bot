from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape

from aiogram import Bot

from app.config import Settings
from app.db.repo import Repo
from app.db.session import session_scope
from app.services.notifier import send_submission_to_admins
from app.services.render import format_dt


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
                await self.process_expired_events(bot)
            except Exception:
                # Keep loop alive and retry on the next interval.
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def process_expired_events(self, bot: Bot) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope(self.session_factory) as session:
            repo = Repo(session)
            events = await repo.list_expired_events_for_notify(now)
            for event in events:
                submissions = await repo.list_event_submissions(event.id)
                summary = (
                    f"🏁 Ивент завершен: <b>{escape(event.title)}</b>\n"
                    f"Период: {format_dt(event.start_at)} — {format_dt(event.end_at)}\n"
                    f"Получено работ: {len(submissions)}"
                )
                for admin_id in self.settings.admin_ids:
                    try:
                        await bot.send_message(admin_id, summary)
                    except Exception:
                        continue

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

                await repo.mark_event_closed_notified(event.id)

