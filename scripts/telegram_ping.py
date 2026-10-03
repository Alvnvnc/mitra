#!/usr/bin/env python3
"""Minimal Telegram sender — baseline tool for validation scenario S2.

Deliberately the *simplest possible* scheduled-delivery setup (the "current
way"), not the future Mitra bot. Its job is to reveal baseline behavior:
does a scheduled message arrive — and does anyone notice when it doesn't?

Usage:
    # One-time setup: create a bot via @BotFather, put TELEGRAM_BOT_TOKEN in .env
    # Then send any message to your bot and discover the chat id:
    python scripts/telegram_ping.py --whoami

    # Send one message (this is what cron will run):
    python scripts/telegram_ping.py --text "Uji S2 - pesan terjadwal"

    # Print a sample cron line:
    python scripts/telegram_ping.py --cron-hint
"""

from __future__ import annotations

import argparse
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

import httpx

API_BASE = "https://api.telegram.org"


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set (see .env.example).")
        raise SystemExit(2)
    return token


def whoami(token: str) -> None:
    """Print chat ids seen by the bot (send your bot a message first)."""
    response = httpx.get(f"{API_BASE}/bot{token}/getUpdates", timeout=30)
    response.raise_for_status()
    updates = response.json().get("result", [])
    seen: dict[str, str] = {}
    for update in updates:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat", {})
        if chat.get("id"):
            label = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            seen[str(chat["id"])] = f"{chat.get('type')} / {label}"
    if not seen:
        print("Belum ada pesan terlihat. Kirim dulu pesan apa pun ke bot, lalu jalankan lagi.")
        return
    print("Chat id yang terlihat (masukkan salah satu ke TELEGRAM_CHAT_ID di .env):")
    for chat_id, label in seen.items():
        print(f"  {chat_id}  —  {label}")


def send(token: str, text: str) -> None:
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_TARGET") or ""
    ).strip()
    if not chat_id:
        print("ERROR: TELEGRAM_CHAT_ID is not set. Run --whoami first.")
        raise SystemExit(2)
    response = httpx.post(
        f"{API_BASE}/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    print(f"Sent ok={payload.get('ok')} message_id={payload.get('result', {}).get('message_id')}")


def cron_hint(repo_dir: str) -> None:
    print("Contoh baris cron (sesuaikan jam + path):")
    print(
        f"0 7 * * * cd '{repo_dir}' && .venv/bin/python scripts/telegram_ping.py "
        '--text "Uji S2 $(date +\\%F) - pesan pagi" >> /tmp/telegram_ping.log 2>&1'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline Telegram sender for validation S2")
    parser.add_argument(
        "--whoami", action="store_true", help="show chat ids (send the bot a message first)"
    )
    parser.add_argument("--text", help="message text to send")
    parser.add_argument("--cron-hint", action="store_true", help="print a sample cron line")
    args = parser.parse_args()

    if args.cron_hint:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cron_hint(repo_dir)
        return 0

    token = _token()
    if args.whoami:
        whoami(token)
    elif args.text:
        send(token, args.text)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())