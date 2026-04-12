from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import (
    Event,
    Participation,
    Submission,
    SubmissionAttachment,
    SubmissionType,
    User,
)
from app.services.time_utils import to_utc_naive, utcnow_naive


@dataclass(slots=True)
class EventSubmissionRecord:
    submission: Submission
    participation: Participation
    user: User


class Repo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(
        self,
        tg_id: int,
        username: str | None,
        full_name: str,
    ) -> User:
        user = await self.get_user_by_tg_id(tg_id)
        if user is None:
            user = User(tg_id=tg_id, username=username, full_name=full_name)
            self.session.add(user)
            await self.session.flush()
            return user

        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if changed:
            await self.session.flush()
        return user

    async def get_user_by_tg_id(self, tg_id: int) -> User | None:
        stmt = select(User).where(User.tg_id == tg_id)
        return (await self.session.scalars(stmt)).first()

    async def create_event(
        self,
        *,
        title: str,
        description: str,
        start_at: datetime,
        end_at: datetime,
        prize_places: int,
        submission_type: SubmissionType,
        created_by_admin_id: int,
    ) -> Event:
        event = Event(
            title=title,
            description=description,
            start_at=start_at,
            end_at=end_at,
            prize_places=prize_places,
            submission_type=submission_type,
            is_active=True,
            start_notified=False,
            reminder_24h_notified=False,
            closed_notified=False,
            created_by_admin_id=created_by_admin_id,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def delete_event(self, event_id: int) -> bool:
        stmt = delete(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def get_event(self, event_id: int) -> Event | None:
        stmt = select(Event).where(Event.id == event_id)
        return (await self.session.scalars(stmt)).first()

    async def list_events_for_main(self, now: datetime) -> list[Event]:
        stmt = (
            select(Event)
            .where(
                and_(
                    Event.is_active.is_(True),
                    Event.start_at <= now,
                    Event.end_at >= now,
                )
            )
            .order_by(Event.end_at.asc(), Event.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_all_events(self) -> list[Event]:
        stmt = select(Event).order_by(Event.created_at.desc(), Event.id.desc())
        return list((await self.session.scalars(stmt)).all())

    async def list_events_for_start_notify(self, now: datetime) -> list[Event]:
        stmt = (
            select(Event)
            .where(
                and_(
                    Event.is_active.is_(True),
                    Event.start_notified.is_(False),
                    Event.start_at <= now,
                    Event.end_at > now,
                )
            )
            .order_by(Event.start_at.asc(), Event.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def mark_event_start_notified(self, event_id: int) -> None:
        stmt = (
            update(Event)
            .where(Event.id == event_id)
            .values(start_notified=True)
        )
        await self.session.execute(stmt)

    async def list_events_for_24h_reminder(self, now: datetime, reminder_border: datetime) -> list[Event]:
        stmt = (
            select(Event)
            .where(
                and_(
                    Event.is_active.is_(True),
                    Event.reminder_24h_notified.is_(False),
                    Event.end_at > now,
                    Event.end_at <= reminder_border,
                )
            )
            .order_by(Event.end_at.asc(), Event.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def mark_event_24h_reminder_notified(self, event_id: int) -> None:
        stmt = (
            update(Event)
            .where(Event.id == event_id)
            .values(reminder_24h_notified=True)
        )
        await self.session.execute(stmt)

    async def list_expired_events_for_notify(self, now: datetime) -> list[Event]:
        stmt = (
            select(Event)
            .where(
                and_(
                    Event.end_at <= now,
                    Event.closed_notified.is_(False),
                )
            )
            .order_by(Event.end_at.asc(), Event.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def mark_event_closed_notified(self, event_id: int) -> None:
        stmt = (
            update(Event)
            .where(Event.id == event_id)
            .values(closed_notified=True, is_active=False)
        )
        await self.session.execute(stmt)

    async def toggle_event_active(self, event_id: int) -> Event | None:
        event = await self.get_event(event_id)
        if event is None:
            return None
        event.is_active = not event.is_active
        await self.session.flush()
        return event

    async def update_event_deadline(self, event_id: int, new_end_at: datetime) -> Event | None:
        event = await self.get_event(event_id)
        if event is None:
            return None
        event.end_at = to_utc_naive(new_end_at)
        if to_utc_naive(new_end_at) > utcnow_naive():
            event.closed_notified = False
            event.reminder_24h_notified = False
        await self.session.flush()
        return event

    async def get_participation(self, *, user_tg_id: int, event_id: int) -> Participation | None:
        stmt = (
            select(Participation)
            .join(User, Participation.user_id == User.id)
            .where(and_(User.tg_id == user_tg_id, Participation.event_id == event_id))
        )
        return (await self.session.scalars(stmt)).first()

    async def join_event(
        self,
        *,
        user_tg_id: int,
        username: str | None,
        full_name: str,
        event_id: int,
    ) -> tuple[Participation, bool]:
        user = await self.get_or_create_user(user_tg_id, username, full_name)
        stmt = select(Participation).where(
            and_(
                Participation.user_id == user.id,
                Participation.event_id == event_id,
            )
        )
        existing = (await self.session.scalars(stmt)).first()
        if existing is not None:
            return existing, False

        participation = Participation(
            user_id=user.id,
            event_id=event_id,
        )
        self.session.add(participation)
        await self.session.flush()
        return participation, True

    async def list_user_participations(self, user_tg_id: int) -> list[Participation]:
        stmt = (
            select(Participation)
            .join(User, Participation.user_id == User.id)
            .where(User.tg_id == user_tg_id)
            .options(joinedload(Participation.event))
            .order_by(Participation.joined_at.desc(), Participation.id.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_event_participations(self, event_id: int) -> list[Participation]:
        stmt = (
            select(Participation)
            .where(Participation.event_id == event_id)
            .options(joinedload(Participation.user))
            .order_by(Participation.joined_at.asc(), Participation.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_submission(self, participation_id: int) -> Submission | None:
        stmt = select(Submission).where(Submission.participation_id == participation_id)
        return (await self.session.scalars(stmt)).first()

    async def save_submission(
        self,
        *,
        participation_id: int,
        submission_type: SubmissionType,
        attachments: list[SubmissionAttachment] | None = None,
        text_content: str | None = None,
    ) -> Submission | None:
        existing = await self.get_submission(participation_id)
        if existing is not None:
            return None

        submission = Submission(
            participation_id=participation_id,
            submission_type=submission_type,
            text_content=text_content,
        )
        submission.set_attachments(attachments or [])
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def list_event_submissions(self, event_id: int) -> list[EventSubmissionRecord]:
        stmt = (
            select(Submission, Participation, User)
            .join(Participation, Submission.participation_id == Participation.id)
            .join(User, Participation.user_id == User.id)
            .where(Participation.event_id == event_id)
            .order_by(Submission.created_at.asc(), Submission.id.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            EventSubmissionRecord(
                submission=row[0],
                participation=row[1],
                user=row[2],
            )
            for row in rows
        ]

    async def set_winners_by_tg_ids(
        self,
        *,
        event_id: int,
        winner_tg_ids: list[int],
    ) -> tuple[list[Participation], list[int]]:
        clear_stmt = (
            update(Participation)
            .where(Participation.event_id == event_id)
            .values(winner_place=None)
        )
        await self.session.execute(clear_stmt)

        assigned: list[Participation] = []
        missing: list[int] = []
        for place, tg_id in enumerate(winner_tg_ids, start=1):
            stmt = (
                select(Participation)
                .join(User, Participation.user_id == User.id)
                .where(and_(Participation.event_id == event_id, User.tg_id == tg_id))
            )
            participation = (await self.session.scalars(stmt)).first()
            if participation is None:
                missing.append(tg_id)
                continue
            participation.winner_place = place
            assigned.append(participation)

        await self.session.flush()
        return assigned, missing
