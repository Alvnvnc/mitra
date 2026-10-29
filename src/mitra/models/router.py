"""Model router: choose and call NVIDIA Nemotron models on Nebius Token Factory.

Token Factory exposes an OpenAI-compatible API, so we use the official OpenAI
Python client pointed at the Token Factory endpoint. The router has four jobs:

1. Pick the right model for a purpose ("fast" | "chat" | "reasoning").
2. Normalise the response shape (content + tool calls + usage) for the agent.
3. Record latency, tokens and estimated cost for every call.
4. Stay demo-safe: if no key is configured — or Token Factory rejects the key —
   fall back to the deterministic local composer and *say so* in the usage log.
   A judge clicking the demo should see a working product, and an honest label,
   not a stack trace.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from mitra.config import get_settings
from mitra.models.demo import MODEL_ID as DEMO_MODEL_ID
from mitra.models.demo import DemoModel

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
    provider: str = "nebius"


@dataclass
class RouterStats:
    """In-process stats (persisted to the ledger when a ledger is attached)."""

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


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = "{}"


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    provider: str = "nebius"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    finish_reason: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.content.strip()) or bool(self.tool_calls)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class ModelRouter:
    """Purpose-based front door to Nebius Token Factory (with a demo fallback)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        models: dict[str, str] | None = None,
        *,
        provider: str | None = None,
        ledger: Any | None = None,
        session_id: str | None = None,
        daily_budget_usd: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.nebius_api_key).strip()
        self._base_url = base_url or settings.nebius_base_url
        self.models = models or settings.model_map()
        self._settings = settings
        self.ledger = ledger
        self.session_id = session_id
        self.daily_budget_usd = (
            daily_budget_usd
            if daily_budget_usd is not None
            else float(settings.mitra_daily_budget_usd or 0)
        )

        requested = (provider or settings.mitra_provider or "auto").lower()
        if requested not in {"auto", "nebius", "demo"}:
            raise ValueError(f"unknown provider {requested!r}; expected auto|nebius|demo")
        self.requested_provider = requested
        self.strict = requested == "nebius"
        self.demo = DemoModel()
        self._client: OpenAI | None = None
        self._degraded_reason: str | None = None

        if requested == "demo":
            self.provider = "demo"
            self._degraded_reason = "MITRA_PROVIDER=demo"
        elif not self._api_key:
            if self.strict:
                raise RuntimeError(
                    "NEBIUS_API_KEY is not set — copy .env.example to .env and fill it in, "
                    "or set MITRA_PROVIDER=demo for the offline demo."
                )
            self.provider = "demo"
            self._degraded_reason = "NEBIUS_API_KEY is empty"
        else:
            self.provider = "nebius"
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=120,
                max_retries=2,
            )
        self.stats = RouterStats()

    # ------------------------------------------------------------- metadata

    @property
    def degraded_reason(self) -> str | None:
        return self._degraded_reason

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "requested": self.requested_provider,
            "models": dict(self.models),
            "degraded_reason": self._degraded_reason,
            "budget_usd": self.daily_budget_usd,
        }

    def model_for(self, purpose: str) -> str:
        try:
            return self.models[purpose]
        except KeyError as exc:
            raise ValueError(
                f"unknown purpose {purpose!r}; expected one of {sorted(self.models)}"
            ) from exc

    # ------------------------------------------------------------- recording

    def _budget_used_today(self) -> float:
        if self.ledger is None:
            return 0.0
        summary = self.ledger.usage_summary(days=1)
        return float(summary.get("cost_usd") or 0.0)

    def _record(self, record: CallRecord) -> None:
        self.stats.add(record)
        if self.ledger is not None:
            self.ledger.record_model_call(
                provider=record.provider,
                model=record.model,
                purpose=record.purpose,
                latency_s=record.latency_s,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                cost_usd=record.cost_usd,
                session_id=self.session_id,
                finish_reason=record.finish_reason,
            )

    # ----------------------------------------------------------- public API

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
        """One chat completion; returns an OpenAI-shaped object.

        Kept for the skill and evaluation call sites. New code should prefer
        ``chat()``, which normalises tool calls and usage.
        """
        message_list = list(messages)
        if self.provider == "demo":
            return self._demo_completion(
                message_list, purpose=purpose, max_tokens=max_tokens, reason=self._degraded_reason
            )

        # The daily ceiling has to bind here too: skills and scheduled runs use
        # this path, and a single Ultra planning call costs more than a chat.
        if self.budget_exceeded():
            raise BudgetExceeded(
                f"daily inference budget of ${self.daily_budget_usd:.2f} reached — "
                "raise MITRA_DAILY_BUDGET_USD or wait for the UTC day to roll over"
            )

        model = self.model_for(purpose)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": message_list,
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
        try:
            if self._client is None:
                raise RuntimeError("nebius client not initialised")
            completion = self._client.chat.completions.create(**kwargs)
        except (APIStatusError, APIConnectionError, RateLimitError) as exc:
            return self._fallback_completion(
                message_list,
                purpose=purpose,
                max_tokens=max_tokens,
                exc=exc,
            )

        latency = time.perf_counter() - started
        usage = completion.usage
        prompt_tokens = (getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = (getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        self._record(
            CallRecord(
                model=model,
                purpose=purpose,
                latency_s=latency,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
                finish_reason=completion.choices[0].finish_reason if completion.choices else None,
                provider="nebius",
            )
        )
        return completion

    def _demo_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        max_tokens: int | None,
        reason: str | None,
    ) -> Any:
        started = time.perf_counter()
        completion = self.demo.completion(messages=messages, max_tokens=max_tokens, purpose=purpose)
        latency = time.perf_counter() - started
        usage = completion.usage
        self._record(
            CallRecord(
                model=DEMO_MODEL_ID,
                purpose=purpose,
                latency_s=latency,
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                cost_usd=0.0,
                finish_reason="stop",
                provider="demo",
            )
        )
        if reason:
            self._degraded_reason = reason
        return completion

    def _fallback_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        max_tokens: int | None,
        exc: Exception,
    ) -> Any:
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            reason = (
                f"Token Factory rejected the API key ({status}). "
                "Set a valid NEBIUS_API_KEY; the demo continues on the local model."
            )
        elif isinstance(exc, (APIConnectionError, RateLimitError)):
            reason = (
                f"Token Factory unavailable ({type(exc).__name__}). "
                "The demo continues on the local model."
            )
        else:
            reason = f"Token Factory error ({type(exc).__name__}: {_short_error(exc)})."
        self.provider = "demo"
        self._degraded_reason = reason
        if self.strict:
            raise exc
        return self._demo_completion(
            messages, purpose=purpose, max_tokens=max_tokens, reason=reason
        )

    def probe(self) -> None:
        """Fail early and visibly: one cheap call at startup, no silent demo mode."""
        if self.provider != "nebius" or self._client is None:
            return
        try:
            self._client.with_options(timeout=6, max_retries=0).models.list()
        except Exception as exc:  # noqa: BLE001 — probe only
            status = getattr(exc, "status_code", None)
            if status in (401, 403):
                reason = (
                    f"Token Factory rejected the API key ({status}). "
                    "Set a valid NEBIUS_API_KEY; the demo continues on the local model."
                )
            else:
                reason = (
                    f"Token Factory unreachable at startup ({type(exc).__name__}). "
                    "Falling back to the local demo model."
                )
            self.provider = "demo"
            self._degraded_reason = reason

    # -------------------------------------------------------------- agent API

    def chat(
        self,
        *,
        purpose: str = "chat",
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = 1200,
        response_format: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Normalised completion: content, tool calls, usage, provider."""
        if self.budget_exceeded():
            raise BudgetExceeded(
                f"daily inference budget of ${self.daily_budget_usd:.2f} reached — "
                "raise MITRA_DAILY_BUDGET_USD or wait for the UTC day to roll over"
            )

        if self.provider == "demo":
            started = time.perf_counter()
            reply = self.demo.chat(messages=messages, tool_schemas=tool_schemas, purpose=purpose)
            latency = time.perf_counter() - started
            prompt_tokens = max(1, sum(len(str(m.get("content") or "")) for m in messages) // 4)
            completion_tokens = max(1, len(reply.content) // 4)
            model = DEMO_MODEL_ID
            self._record(
                CallRecord(
                    model=model,
                    purpose=purpose,
                    latency_s=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=0.0,
                    finish_reason=reply.finish_reason,
                    provider="demo",
                )
            )
            tool_calls = [
                ToolCall(
                    id=str(tc.get("id") or "call_demo"),
                    name=str((tc.get("function") or {}).get("name") or ""),
                    arguments=_as_dict((tc.get("function") or {}).get("arguments")),
                    raw_arguments=str((tc.get("function") or {}).get("arguments") or "{}"),
                )
                for tc in reply.tool_calls
            ]
            return LLMResponse(
                content=reply.content,
                tool_calls=tool_calls,
                model=model,
                provider="demo",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_s=latency,
                finish_reason=reply.finish_reason,
            )

        model = self.model_for(purpose)
        completion = self.complete(
            purpose=purpose,
            messages=messages,
            tool_schemas=tool_schemas,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=extra_body,
        )
        choice = completion.choices[0] if completion.choices else None
        message = getattr(choice, "message", None)
        content = str(getattr(message, "content", "") or "")
        raw_calls = getattr(message, "tool_calls", None) or []
        tool_calls: list[ToolCall] = []
        for call in raw_calls:
            fn = getattr(call, "function", None)
            raw_args = str(getattr(fn, "arguments", "") or "{}")
            tool_calls.append(
                ToolCall(
                    id=str(getattr(call, "id", "") or ""),
                    name=str(getattr(fn, "name", "") or ""),
                    arguments=_as_dict(raw_args),
                    raw_arguments=raw_args,
                )
            )
        usage = getattr(completion, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        cost = (
            0.0
            if self.provider == "demo"
            else estimate_cost_usd(model, prompt_tokens, completion_tokens)
        )
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=DEMO_MODEL_ID if self.provider == "demo" else model,
            provider=self.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_s=0.0,
            finish_reason=getattr(choice, "finish_reason", None),
        )

    def budget_exceeded(self) -> bool:
        if not self.daily_budget_usd or self.ledger is None:
            return False
        return self._budget_used_today() >= self.daily_budget_usd


class BudgetExceeded(RuntimeError):
    """Daily inference budget reached (O4 guard for the public demo)."""


def _short_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:180]
