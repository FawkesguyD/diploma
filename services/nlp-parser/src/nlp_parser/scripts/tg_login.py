from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


async def _login(api_id: int, api_hash: str, phone: str) -> str:
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        code = input("Telegram code: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = getpass.getpass("2FA password: ")
            await client.sign_in(password=password)
    session = client.session.save()
    await client.disconnect()
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Telethon StringSession for nlp-parser.")
    parser.add_argument("--api-id", type=int, required=True)
    parser.add_argument("--api-hash", required=True)
    parser.add_argument("--phone", required=True, help="Phone in E.164 format, e.g. +79991234567")
    args = parser.parse_args()
    session = asyncio.run(_login(args.api_id, args.api_hash, args.phone))
    print()
    print("TG_SESSION=" + session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
