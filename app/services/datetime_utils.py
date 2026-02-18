from __future__ import annotations

from datetime import datetime


DATETIME_INPUT_FORMAT = "%d.%m.%Y %H:%M"


def parse_datetime_utc(value: str) -> datetime | None:
    try:
        dt = datetime.strptime(value.strip(), DATETIME_INPUT_FORMAT)
    except ValueError:
        return None
    # We store UTC in DB as naive datetime for SQLite compatibility.
    return dt
