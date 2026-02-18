from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def is_within_period(*, now: datetime, start: datetime, end: datetime) -> bool:
    now_value = to_utc_naive(now)
    return to_utc_naive(start) <= now_value <= to_utc_naive(end)

