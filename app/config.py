from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


def _parse_admin_ids(raw: str) -> list[int]:
    admin_ids: list[int] = []
    for chunk in raw.split(","):
        candidate = chunk.strip()
        if not candidate:
            continue
        if candidate.lstrip("-").isdigit():
            admin_ids.append(int(candidate))
    return admin_ids


def _parse_positive_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    if value.isdigit():
        return max(1, int(value))
    return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    bot_username: str
    required_channel: str
    required_channel_url: str
    admin_ids: list[int]
    database_url: str
    bot_name: str
    channel_name: str
    developer_url: str
    max_photo_attachments: int
    max_document_attachments: int


@lru_cache
def get_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Environment variable BOT_TOKEN is required.")

    return Settings(
        bot_token=bot_token,
        bot_username=os.getenv("BOT_USERNAME", "mgol3bot").strip().lstrip("@"),
        required_channel=os.getenv("REQUIRED_CHANNEL", "@LMeansLyceum3").strip(),
        required_channel_url=os.getenv(
            "REQUIRED_CHANNEL_URL",
            "https://t.me/LMeansLyceum3",
        ).strip(),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db").strip(),
        bot_name=os.getenv("BOT_NAME", "К — значит конкурс").strip(),
        channel_name=os.getenv("CHANNEL_NAME", "Л — значит Лицей 🤟").strip(),
        developer_url=os.getenv("DEVELOPER_URL", "https://t.me/daich").strip(),
        max_photo_attachments=_parse_positive_int(
            os.getenv("MAX_PHOTO_ATTACHMENTS"),
            default=10,
        ),
        max_document_attachments=_parse_positive_int(
            os.getenv("MAX_DOCUMENT_ATTACHMENTS"),
            default=1,
        ),
    )

