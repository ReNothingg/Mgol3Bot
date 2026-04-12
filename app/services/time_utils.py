from __future__ import annotations

from datetime import datetime, timedelta, timezone


MSK_TZ = timezone(timedelta(hours=3), name="MSK")


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_msk(value: datetime) -> datetime:
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.astimezone(MSK_TZ)


def msk_to_utc_naive(value: datetime) -> datetime:
    msk_value = value.replace(tzinfo=MSK_TZ) if value.tzinfo is None else value.astimezone(MSK_TZ)
    return msk_value.astimezone(timezone.utc).replace(tzinfo=None)


def is_within_period(*, now: datetime, start: datetime, end: datetime) -> bool:
    now_value = to_utc_naive(now)
    return to_utc_naive(start) <= now_value <= to_utc_naive(end)

