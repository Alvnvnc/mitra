#!/usr/bin/env python3
"""Smoke test: verify NEBIUS_API_KEY can reach Nemotron models on Nebius Token Factory.

Usage:
    export NEBIUS_API_KEY="..."     # or put it in .env (loaded below if available)
    python scripts/smoke_test.py            # tests the default trio
    python scripts/smoke_test.py --all      # also tests Nemotron 3.5 Lightning

Exit code 0 = all tested models responded; 1 = at least one failure; 2 = config error.
"""

from __future__ import annotations

import os
import sys
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # dotenv is optional; env vars work too
    pass

from openai import OpenAI

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
BASE_URL = (os.environ.get("NEBIUS_BASE_URL") or "").strip() or DEFAULT_BASE_URL

# (model id, role in Mitra's routing)
MODELS = [
    ("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "fast: extraction / classification"),
    ("nvidia/nemotron-3-super-120b-a12b", "chat: everyday + tool calling"),
    ("nvidia/Nemotron-3-Ultra-550b-a55b", "reasoning: hard planning"),
]
EXTRA = [
    ("nvidia/Nemotron-3_5-Lightning", "fast alternative: 1M context, same price as Nano"),
]

PROMPT = (
    "Reply with exactly one short sentence: what are you, and which model family do you belong to?"
)


def main() -> int:
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: NEBIUS_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 2

    models = MODELS + EXTRA if "--all" in sys.argv else MODELS
    client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=120, max_retries=1)

    print(f"endpoint: {BASE_URL}")
    failures = 0
    for model_id, role in models:
        print(f"\n=== {model_id}  ({role}) ===")
        started = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": PROMPT}],
                temperature=0.2,
                max_tokens=96,
            )
        except Exception as exc:  # noqa: BLE001 — smoke test wants the raw error
            failures += 1
            print(f"FAILED after {time.perf_counter() - started:.1f}s: {exc}")
            continue

        elapsed = time.perf_counter() - started
        text = (resp.choices[0].message.content or "").strip().replace("\n", " ")
        usage = resp.usage
        tok_in = getattr(usage, "prompt_tokens", 0) or 0
        tok_out = getattr(usage, "completion_tokens", 0) or 0
        print(f"ok in {elapsed:.1f}s | tokens in/out: {tok_in}/{tok_out}")
        print(f"response: {text[:200]}")

    print("\n" + ("ALL MODELS OK" if failures == 0 else f"{failures} model(s) FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())