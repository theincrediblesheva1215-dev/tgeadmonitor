"""Секреты и runtime-настройки. Только из окружения (.env), никогда из кода."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class SettingsError(Exception):
    pass


def _req(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SettingsError(f"Environment variable {name} is required")
    return value


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session: str
    bot_token: str
    owner_chat_id: int
    config_dir: Path
    data_dir: Path
    db_path: Path
    log_level: str
    store_all_messages: bool

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        return cls(
            api_id=int(_req("API_ID")),
            api_hash=_req("API_HASH"),
            session=os.getenv("SESSION", "").strip(),
            bot_token=_req("BOT_TOKEN"),
            owner_chat_id=int(_req("OWNER_CHAT_ID")),
            config_dir=Path(os.getenv("CONFIG_DIR", "config")),
            data_dir=data_dir,
            db_path=Path(os.getenv("DB_PATH", str(data_dir / "leads.db"))),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            store_all_messages=os.getenv("STORE_ALL_MESSAGES", "1") == "1",
        )