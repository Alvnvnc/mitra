"""Minimal scheduler: poll due commitments and run the pipeline.

v1 keeps this trivially small (once a day per commitment, checked every
``interval_s``); the dashboard takes over schedule editing in W3. One crashing
commitment must never take the loop down — errors are logged as events.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from mitra.ledger import Ledger
from mitra.runner import RunOutcome, run_commitment_once


def tick(
    ledger: Ledger,
    *,
    router: object | None = None,
    repo_root: str | Path | None = None,
    outbox_dir: str | Path | None = None,
    sender: object | None = None,
    now: datetime | None = None,
) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for commitment in ledger.due_commitments(now=now):
        try:
            outcomes.append(
                run_commitment_once(
                    ledger,
                    commitment.id,
                    router=router,
                    repo_root=repo_root,
                    outbox_dir=outbox_dir,
                    sender=sender,
                    now=now,
                )
            )
        except Exception as exc:  # noqa: BLE001 — keep the loop alive, log loudly
            ledger.log_event(
                "scheduler_error",
                commitment_id=commitment.id,
                detail=f"{type(exc).__name__}: {exc}",
            )
    return outcomes


def run_forever(
    ledger: Ledger,
    *,
    router: object | None = None,
    interval_s: int = 60,
    repo_root: str | Path | None = None,
    outbox_dir: str | Path | None = None,
    sender: object | None = None,
) -> None:
    print(f"[scheduler] mulai — tick tiap {interval_s}s. Ctrl-C untuk berhenti.")
    try:
        while True:
            for outcome in tick(
                ledger, router=router, repo_root=repo_root, outbox_dir=outbox_dir,
                sender=sender,
            ):
                print(f"[scheduler] {outcome.commitment_id} -> {outcome.state}: {outcome.detail}")
            time.sleep(interval_s)
    except KeyboardInterrupt:
        print("[scheduler] stop.")