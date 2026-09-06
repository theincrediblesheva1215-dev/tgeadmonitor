"""Одноразовая интерактивная авторизация. Печатает SESSION для .env."""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    load_dotenv()
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        me = await client.get_me()
        print(f"\nAuthorized as {me.first_name} (@{me.username})")
        print("\nAdd to .env:\nSESSION=" + client.session.save())


if __name__ == "__main__":
    asyncio.run(main())