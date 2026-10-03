"""Delivery lanes — deliberately separate from result production (O3).

A result can exist with verified evidence and still fail to reach the user; the
ledger models that as its own state (``delivery_failed``), and the runner writes
a fallback notice so the failure surfaces without the user asking.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from mitra.config import get_settings

TELEGRAM_API = "https://api.telegram.org"


@dataclass
class DeliveryResult:
    ok: bool
    lane: str
    receipt: dict[str, Any] | None = None
    error: str | None = None


def send_telegram(
    text: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: float = 30,
) -> DeliveryResult:
    settings = get_settings()
    token = (token if token is not None else settings.telegram_bot_token).strip()
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return DeliveryResult(False, "telegram", error="TELEGRAM_BOT_TOKEN belum diisi")

    chat_id = (
        chat_id
        or os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_TARGET")
        or ""
    ).strip()
    if not chat_id:
        return DeliveryResult(False, "telegram", error="TELEGRAM_CHAT_ID/TARGET belum diisi")

    try:
        response = httpx.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=timeout,
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # network down, bad gateway, quota, non-JSON body — all delivery-stage
        return DeliveryResult(False, "telegram", error=f"{type(exc).__name__}: {exc}")

    if payload.get("ok"):
        result = payload.get("result", {})
        return DeliveryResult(
            True,
            "telegram",
            receipt={"message_id": result.get("message_id"), "chat_id": str(chat_id)},
        )
    return DeliveryResult(
        False, "telegram", error=f"telegram api: {payload.get('description', 'unknown')}"
    )


def deliver(
    channel: str,
    text: str,
    *,
    sender: Callable[..., DeliveryResult] | None = None,
) -> DeliveryResult:
    """Deliver via ``channel``. ``sender`` is the test-injection seam."""
    if sender is not None:
        return sender(channel=channel, text=text)
    if channel == "telegram":
        return send_telegram(text)
    if channel == "outbox":
        return DeliveryResult(True, "outbox", receipt={"lane": "outbox"})
    return DeliveryResult(False, channel, error=f"kanal tidak dikenal: {channel!r}")