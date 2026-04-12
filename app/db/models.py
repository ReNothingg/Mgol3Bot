from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SubmissionType(str, Enum):
    PHOTO = "photo"
    DOCUMENT = "document"
    TEXT = "text"
    NONE = "none"


class SubmissionAttachmentKind(str, Enum):
    PHOTO = "photo"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class SubmissionAttachment:
    kind: SubmissionAttachmentKind
    file_id: str


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    participations: Mapped[list["Participation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    prize_places: Mapped[int] = mapped_column(Integer, default=3)
    submission_type: Mapped[SubmissionType] = mapped_column(
        SQLEnum(SubmissionType, native_enum=False, length=20),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    start_notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reminder_24h_notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    closed_notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by_admin_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    participations: Mapped[list["Participation"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )


class Participation(Base):
    __tablename__ = "participations"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_participation_user_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    winner_place: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship(back_populates="participations")
    event: Mapped[Event] = relationship(back_populates="participations")
    submission: Mapped["Submission | None"] = relationship(
        back_populates="participation",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("participation_id", name="uq_submission_participation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participation_id: Mapped[int] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"),
        index=True,
    )
    submission_type: Mapped[SubmissionType] = mapped_column(
        SQLEnum(SubmissionType, native_enum=False, length=20),
    )
    file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    participation: Mapped[Participation] = relationship(back_populates="submission")

    @property
    def attachments(self) -> list[SubmissionAttachment]:
        if self.attachments_json:
            try:
                payload = json.loads(self.attachments_json)
            except json.JSONDecodeError:
                payload = None
            attachments = _decode_attachments(payload)
            if attachments:
                return attachments
        if self.file_id:
            legacy_kind = (
                SubmissionAttachmentKind.DOCUMENT
                if self.submission_type == SubmissionType.DOCUMENT
                else SubmissionAttachmentKind.PHOTO
            )
            return [SubmissionAttachment(kind=legacy_kind, file_id=self.file_id)]
        return []

    def set_attachments(self, attachments: list[SubmissionAttachment]) -> None:
        self.file_id = attachments[0].file_id if attachments else None
        self.attachments_json = (
            json.dumps(
                [
                    {
                        "kind": attachment.kind.value,
                        "file_id": attachment.file_id,
                    }
                    for attachment in attachments
                ]
            )
            if attachments
            else None
        )


def _decode_attachments(payload: object) -> list[SubmissionAttachment]:
    if not isinstance(payload, list):
        return []

    attachments: list[SubmissionAttachment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        file_id = item.get("file_id")
        kind_raw = item.get("kind")
        if not isinstance(file_id, str) or not file_id:
            continue
        try:
            kind = SubmissionAttachmentKind(str(kind_raw))
        except ValueError:
            continue
        attachments.append(SubmissionAttachment(kind=kind, file_id=file_id))
    return attachments
