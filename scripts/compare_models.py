"""Compare Nemotron with other Token Factory models on Mitra's actual tasks.

The Devpost form asks "how did Nemotron compare to other models you have used for
similar tasks". This answers it with measurements instead of adjectives: three
tasks taken from Mitra's own workload, the same prompts and settings, three
models, scored on the properties the product depends on.

    NEBIUS_API_KEY=… python scripts/compare_models.py

Nothing here is used at runtime. It is an evidence tool, and its output is quoted
in docs/FEEDBACK.md.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from mitra.models.router import PRICE_PER_MILLION

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

MODELS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "deepseek-ai/DeepSeek-V4.1-Flash",
    "Qwen/Qwen3.5-397B-A17B",
]

SYSTEM = (
    "You are Mitra, a private, self-hosted personal AI. You are calm, specific and "
    "brief. Ground every factual claim in the state you are given; if it is not "
    "there, say so. Never invent a commitment, a run, a source or a memory."
)

FACTS = {
    "commitments": [
        {
            "id": "cmt_1",
            "title": "Morning research brief",
            "state": "active",
            "last_run": {"state": "done", "delivered_at": "2026-10-29T00:00:00Z"},
        },
        {
            "id": "cmt_2",
            "title": "Weekly nutrient literature scan",
            "state": "active",
            "last_run": {
                "state": "delivery_failed",
                "error": "ntfy http 503 (demo: push lane unavailable)",
                "delivered_at": None,
                "evidence": "passed",
            },
        },
        {
            "id": "cmt_3",
            "title": "Sunday review",
            "state": "paused",
            "last_run": {"state": "failed", "error": "evidence check failed: 2 bullets < 3"},
        },
    ]
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "commitment_status",
            "description": "Read the commitment ledger: schedule, current instruction, last run.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }
]


@dataclass
class Result:
    model: str
    task: str
    ok: bool
    detail: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def cost(model: str, prompt: int, completion: int) -> float:
    prices = PRICE_PER_MILLION.get(model)
    if not prices:
        return 0.0
    return (prompt * prices[0] + completion * prices[1]) / 1_000_000


def call(client: OpenAI, model: str, messages: list[dict[str, Any]], **kwargs) -> tuple[Any, float]:
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        **kwargs,
    )
    return response, round(time.perf_counter() - started, 2)


def task_tool_call(client: OpenAI, model: str) -> Result:
    """Does the model reach for the ledger instead of answering from vibes?"""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Did yesterday's morning brief actually deliver? Check."},
    ]
    response, latency = call(client, model, messages, tools=TOOLS)
    message = response.choices[0].message
    calls = message.tool_calls or []
    names = [call.function.name for call in calls]
    if calls:
        raw = calls[0].function.arguments or "{}"
        try:
            json.loads(raw)
            valid = True
        except json.JSONDecodeError:
            valid = False
    else:
        valid = False
    detail = f"tool_calls={names or 'none'}, args_valid={valid}"
    return Result(
        model=model,
        task="tool call",
        ok=bool(calls) and valid,
        detail=detail,
        latency_s=latency,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        cost_usd=cost(model, response.usage.prompt_tokens, response.usage.completion_tokens),
    )


SECTIONS = ("status", "selesai", "tertunda", "prioritas")


def task_shape(client: OpenAI, model: str) -> Result:
    """Does the model honour a four-section output contract?"""
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                "Write the owner's morning brief from these facts, using exactly these four "
                "labelled lines and nothing else: Status:, Selesai:, Tertunda:, Prioritas:. "
                "Maximum 45 words.\n\n" + json.dumps(FACTS)
            ),
        },
    ]
    response, latency = call(client, model, messages)
    text = response.choices[0].message.content or ""
    lowered = text.lower()
    found = [
        section
        for section in SECTIONS
        if re.search(rf"^\s*(?:[-•*]\s*)?\*{{0,2}}{section}", lowered, re.M)
    ]
    words = len(re.findall(r"\S+", text))
    detail = f"sections={len(found)}/4, words={words}"
    return Result(
        model=model,
        task="output shape",
        ok=len(found) == 4 and words <= 60,
        detail=detail,
        latency_s=latency,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        cost_usd=cost(model, response.usage.prompt_tokens, response.usage.completion_tokens),
    )


def task_grounding(client: OpenAI, model: str) -> Result:
    """Can it name the one commitment that is actually at risk?"""
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                "LIVE STATE:\n"
                + json.dumps(FACTS)
                + "\n\nWhich commitment is most at risk right now, and why? One sentence."
            ),
        },
    ]
    response, latency = call(client, model, messages)
    text = (response.choices[0].message.content or "").lower()
    named = "literature" in text
    explained = "delivery" in text or "ntfy" in text
    wrong = "morning research brief is most at risk" in text
    detail = f"named_risk={named}, explained={explained}, wrong_pick={wrong}"
    return Result(
        model=model,
        task="grounding",
        ok=named and explained and not wrong,
        detail=detail,
        latency_s=latency,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        cost_usd=cost(model, response.usage.prompt_tokens, response.usage.completion_tokens),
    )


def main() -> int:
    api_key = (os.environ.get("NEBIUS_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("set NEBIUS_API_KEY")
    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=60, max_retries=1)

    results: list[Result] = []
    for model in MODELS:
        for task in (task_tool_call, task_shape, task_grounding):
            try:
                result = task(client, model)
            except Exception as exc:  # noqa: BLE001 — a missing model must not stop the run
                result = Result(
                    model, task.__name__, False, f"error: {type(exc).__name__}", 0, 0, 0, 0
                )
            results.append(result)
            mark = "PASS" if result.ok else "FAIL"
            print(f"{mark}  {model:44} {result.task:14} {result.detail}  {result.latency_s}s")

    print("\n| Model | Task | Result | Latency | Tokens in/out | Cost |")
    print("|---|---|---|---:|---|---:|")
    for r in results:
        tokens = f"{r.prompt_tokens}/{r.completion_tokens}"
        money = f"${r.cost_usd:.5f}" if r.cost_usd else "n/a"
        print(
            f"| `{r.model.split('/')[-1]}` | {r.task} | "
            f"{'pass' if r.ok else 'fail'} — {r.detail} | {r.latency_s}s | {tokens} | {money} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
