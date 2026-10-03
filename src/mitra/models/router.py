"""Model router: choose and call NVIDIA Nemotron models on Nebius Token Factory.

Token Factory exposes an OpenAI-compatible API, so we use the official OpenAI
Python client pointed at the Token Factory endpoint. The router has two jobs:

1. Pick the right model for a purpose ("fast" | "chat" | "reasoning").
2. Record latency + token usage + estimated cost for every call, so the web
   dashboard can show where the credits go.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from mitra.config import get_settings

# USD per 1M tokens: (input, output). Source: Token Factory model catalog
# (https://tokenfactory.nebius.com/model-catalog.md, Oct 2026). Refresh from
# /api/public/models_info when the catalog changes.
PRICE_PER_MILLION: dict[str, tuple[float, float]] = {
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost for a single call.

    Unknown model ids return 0.0 — callers that need strict accounting should
    treat a zero cost on a non-zero call as "unknown model".
    """
    prices = PRICE_PER_MILLION.get(model)
    if prices is None:
        return 0.0
    in_price, out_price = prices
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


@dataclass
class CallRecord:
    model: str
    purpose: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    finish_reason: str | None = None


@dataclass
class RouterStats:
    """In-process stats. Persisted to the ledger by the dashboard later."""

    calls: list[CallRecord] = field(default_factory=list)

    def add(self, record: CallRecord) -> None:
        self.calls.append(record)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def summary(self) -> dict[str, Any]:
        by_purpose: dict[str, dict[str, float]] = {}
        for c in self.calls:
            agg = by_purpose.setdefault(
                c.purpose, {"calls": 0.0, "cost_usd": 0.0, "latency_s": 0.0}
            )
            agg["calls"] += 1
            agg["cost_usd"] += c.cost_usd
            agg["latency_s"] += c.latency_s
        return {
            "calls": len(self.calls),
            "total_cost_usd": self.total_cost_usd,
            "by_purpose": by_purpose,
        }


class ModelRouter:
    """Purpose-based front door to Nebius Token Factory."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        models: dict[str, str] | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.nebius_api_key
        if not self._api_key:
            raise RuntimeError(
                "NEBIUS_API_KEY is not set — copy .env.example to .env and fill it in."
            )
        self._base_url = base_url or settings.nebius_base_url
        self.models = models or settings.model_map()
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=120,
            max_retries=2,
        )
        self.stats = RouterStats()

    def model_for(self, purpose: str) -> str:
        try:
            return self.models[purpose]
        except KeyError as exc:
            raise ValueError(
                f"unknown purpose {purpose!r}; expected one of {sorted(self.models)}"
            ) from exc

    def complete(
        self,
        *,
        purpose: str = "chat",
        messages: Iterable[dict[str, Any]],
        tool_schemas: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        """One chat completion; returns the OpenAI ChatCompletion object unchanged."""
        model = self.model_for(purpose)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if tool_schemas is not None:
            kwargs["tools"] = tool_schemas
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        if extra_body is not None:
            kwargs["extra_body"] = extra_body

        started = time.perf_counter()
        completion = self._client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - started

        usage = completion.usage
        prompt_tokens = (getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = (getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        self.stats.add(
            CallRecord(
                model=model,
                purpose=purpose,
                latency_s=latency,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
                finish_reason=completion.choices[0].finish_reason if completion.choices else None,
            )
        )
        return completion