#!/usr/bin/env python3
"""Baseline push sender for validation S2/S4 — the simplest possible "current way".

This is deliberately NOT Mitra: one send function, no retry, no status, no
evidence. Its job is to reveal baseline behavior: can a cron job push a daily
message to your phone — and if it fails, does anyone notice? (Honest answer:
usually nobody.)

Setup (1 minute):
  1. NTFY_TOPIC in .env (see .env.example) — or use a separate test topic.
  2. Subscribe that topic in the ntfy app or at https://ntfy.sh/<topic>.

Usage:
    .venv/bin/python scripts/ntfy_ping.py --text "Uji S2 $(date +%F)"
    .venv/bin/python scripts/ntfy_ping.py --cron-hint
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


def _topic(required: bool = True) -> str:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic and required:
        print("ERROR: NTFY_TOPIC belum diisi di .env (lihat .env.example).")
        raise SystemExit(2)
    return topic


def send(topic: str, text: str) -> None:
    base = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    response = httpx.post(f"{base}/{topic}", content=text.encode("utf-8"), timeout=30)
    print(f"HTTP {response.status_code}")
    if response.status_code == 200:
        payload = response.json()
        print(f"Terkirim ke topik {payload.get('topic')} id={payload.get('id')}")
        return
    raise SystemExit(1)


def cron_hint(repo_dir: str, topic: str) -> None:
    print("Contoh baris cron (cara lama — tanpa status, tanpa retry, gagal = senyap):")
    print(
        f"30 21 * * * cd '{repo_dir}' && curl -s -d \"Uji S2 $(date +\\%F) - pesan malam\" "
        f"'https://ntfy.sh/{topic}' >> /tmp/ntfy_ping.log 2>&1"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline ntfy sender for validation S2/S4")
    parser.add_argument("--text", help="message text to send")
    parser.add_argument("--cron-hint", action="store_true", help="print a sample cron line")
    args = parser.parse_args()

    if args.cron_hint:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        topic = _topic(required=False) or "<topik-ntfy>"
        cron_hint(repo_dir, topic)
        return 0

    if args.text:
        send(_topic(), args.text)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())