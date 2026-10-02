#!/usr/bin/env python3
"""Harness evaluasi model Mitra v0.

- Hanya check objektif (tanpa LLM judge di v0).
- Kasus di ``evals/cases.json``; output mentah disimpan ke ``evals/results/``.
- Memakai Nebius Token Factory (NEBIUS_API_KEY dari .env).

Usage:
    .venv/bin/python evals/run_evals.py
    .venv/bin/python evals/run_evals.py --case instruct-latest-wins
    .venv/bin/python evals/run_evals.py --models-all    # paksa semua model (debug)
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from mitra.config import get_settings
from mitra.models.router import estimate_cost_usd

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"
RESULTS_DIR = ROOT / "evals" / "results"


def extract_json(text: str):
    """Parse JSON dari jawaban model; toleran terhadap code fence dan teks pembungkus."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except Exception:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def run_checks(checks, text: str, tool_names: list[str]):
    outcomes = []
    for check in checks:
        kind = check["type"]
        if kind == "contains_all":
            passed = all(v.lower() in text.lower() for v in check["values"])
        elif kind == "contains_any":
            passed = any(v.lower() in text.lower() for v in check["values"])
        elif kind == "not_contains":
            passed = all(v.lower() not in text.lower() for v in check["values"])
        elif kind == "tool_called":
            passed = check["value"] in tool_names
        elif kind == "json_field_in":
            parsed = extract_json(text)
            passed = False
            if isinstance(parsed, dict):
                value = str(parsed.get(check["field"], "")).lower()
                passed = any(expected.lower() in value for expected in check["values"])
        else:
            passed = False
        outcomes.append({"check": check, "passed": passed})
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness evaluasi model Mitra v0")
    parser.add_argument("--case", help="jalankan hanya satu case id")
    parser.add_argument(
        "--models-all", action="store_true", help="paksa semua model untuk setiap case"
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.nebius_api_key:
        print("ERROR: NEBIUS_API_KEY kosong. Isi .env dulu.")
        return 2
    client = OpenAI(
        base_url=settings.nebius_base_url,
        api_key=settings.nebius_api_key,
        timeout=120,
        max_retries=1,
    )

    cases = json.loads(CASES_PATH.read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"case tidak ditemukan: {args.case}")
            return 2

    all_models = [
        settings.mitra_model_fast,
        settings.mitra_model_chat,
        settings.mitra_model_reasoning,
        "nvidia/Nemotron-3_5-Lightning",
    ]

    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    total_cost = 0.0
    for case in cases:
        models = all_models if args.models_all else case["models"]
        for model in models:
            kwargs = {
                "model": model,
                "messages": case["messages"],
                "temperature": case.get("temperature", 0.2),
                "max_tokens": case.get("max_tokens", 400),
            }
            if "tools" in case:
                kwargs["tools"] = case["tools"]
            if "response_format" in case:
                kwargs["response_format"] = case["response_format"]
            if "extra_body" in case:
                kwargs["extra_body"] = case["extra_body"]
            started = time.perf_counter()
            error = None
            text = ""
            tool_names: list[str] = []
            finish_reason = None
            has_reasoning_field = False
            prompt_tokens = completion_tokens = 0
            try:
                resp = client.chat.completions.create(**kwargs)
                latency = time.perf_counter() - started
                choice = resp.choices[0]
                message = choice.message
                text = message.content or ""
                tool_names = [tc.function.name for tc in (message.tool_calls or [])]
                finish_reason = choice.finish_reason
                has_reasoning_field = bool(getattr(message, "reasoning_content", None))
                usage = resp.usage
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            except Exception as exc:  # noqa: BLE001
                latency = time.perf_counter() - started
                error = str(exc)

            cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
            total_cost += cost
            if error:
                outcomes = [{"check": c, "passed": False} for c in case["checks"]]
            else:
                outcomes = run_checks(case["checks"], text, tool_names)
            passed = all(o["passed"] for o in outcomes)
            records.append(
                {
                    "case_id": case["id"],
                    "model": model,
                    "passed": passed,
                    "checks": outcomes,
                    "error": error,
                    "latency_s": round(latency, 2),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": round(cost, 6),
                    "tool_calls": tool_names,
                    "finish_reason": finish_reason,
                    "has_reasoning_field": has_reasoning_field,
                    "response_excerpt": text.strip()[:220],
                }
            )
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {case['id']} :: {model}")
            if not passed:
                for outcome in outcomes:
                    if not outcome["passed"]:
                        print(f"    check gagal: {outcome['check']}")
                if error:
                    print(f"    error: {error}")
                elif text:
                    print(f"    jawaban: {text.strip()[:160].replace(chr(10), ' ')}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = run_at.replace(":", "").replace("-", "")
    out_path = RESULTS_DIR / f"run-{stamp}.json"
    summary = {
        "run_at": run_at,
        "cases": len({r["case_id"] for r in records}),
        "calls": len(records),
        "passed": sum(1 for r in records if r["passed"]),
        "failed": sum(1 for r in records if not r["passed"]),
        "total_cost_usd": round(total_cost, 6),
    }
    out_path.write_text(json.dumps({"summary": summary, "records": records}, indent=2, ensure_ascii=False))
    print("=" * 60)
    print(f"ringkasan: {summary['passed']}/{summary['calls']} lulus | biaya ~${summary['total_cost_usd']:.4f}")
    print(f"hasil mentah: {out_path.relative_to(ROOT)}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())