"""Synthetic demo instance for the judges (and for screenshots).

Everything here is fictional and clearly labelled in the UI: the persona, the
runs, the costs and the research results are sample data. The *code paths* are
the real ones — the ledger invariants, the approval inbox and the policy engine
all run exactly as they would on a real instance.

    python scripts/seed_demo.py --fresh
    MITRA_DATA_DIR=data/demo .venv/bin/uvicorn mitra.web.app:create_app --factory
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mitra.ledger import Ledger
from mitra.memory.selfmodel import SelfModel

WIB = ZoneInfo("Asia/Jakarta")
PERSONA = "Maya Rahman"

PAGES: dict[str, dict[str, object]] = {
    "people.md": {
        "title": "People",
        "body": (
            f"- **{PERSONA}** — owner of this instance. Solo researcher, works in "
            "blocks of deep focus before noon.\n"
            "- **Dr. Ellis Tan** — collaborator at the AgriSens lab. Reviews methods, "
            "prefers written context before calls.\n"
            "- **Rani** — field coordinator in Riau. Sends plot photos and harvest logs."
        ),
    },
    "projects.md": {
        "title": "Projects",
        "body": (
            "- **Sentinel-2 nutrient estimation** — estimating nitrogen and potassium "
            "status in oil palm plots from Sentinel-2 imagery; current stage: validation "
            "dataset assembly.\n"
            "- **Mitra** — this personal agent. Goal: delegate recurring research chores "
            "without losing oversight."
        ),
    },
    "priorities.md": {
        "title": "Priorities",
        "body": (
            "- Ship the Mitra hackathon submission (deadline 30 Oct, 10:00 PDT).\n"
            "- Close the AgriSens dataset request — it blocks the November validation run.\n"
            "- Keep mornings free for writing; batch admin after 16:00."
        ),
    },
    "preferences.md": {
        "title": "Preferences",
        "body": (
            "- English for anything published; Indonesian for personal notes and reminders.\n"
            "- Briefs must be short, factual, and state uncertainty explicitly. No pep talk.\n"
            "- Prefers to see the source and the check that passed, not just “done”."
        ),
    },
    "patterns.md": {
        "title": "Patterns",
        "body": (
            "- Deep work 08:00-11:00 WIB; replies are slower after 21:00.\n"
            "- Tends to postpone dataset emails; a 16:30 follow-up lands well.\n"
            "- Sunday reviews are longer and more reflective than weekday briefs."
        ),
    },
}

COMMITMENTS = [
    {
        "title": "Morning research brief",
        "schedule": "07:00",
        "skill": "morning_brief",
        "channel": "outbox",
        "versions": [
            (
                "Summarize repository activity and today's commitments in at most 160 words.",
                {"max_words": 160},
            ),
            (
                "Include one line about inference cost and flag any failed run from the last 24h. Max 180 words.",
                {"max_words": 180},
            ),
        ],
        "scheduled_version": (
            "Weekdays: three bullets max. Sundays: add a short reflection on the week. Max 200 words.",
            {"max_words": 200},
        ),
        "runs": [1, 1, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1],
    },
    {
        "title": "Weekly nutrient literature scan",
        "schedule": "09:00",
        "skill": "research_digest",
        "channel": "ntfy",
        "versions": [
            (
                "Find two new peer-reviewed papers on Sentinel-2 nitrogen estimation in oil palm. Summarize method and limitation.",
                {"max_words": 220, "min_sources": 2},
            ),
        ],
        "scheduled_version": None,
        "runs": [1, 0, 1],
    },
    {
        "title": "Dataset request follow-up",
        "schedule": "16:30",
        "skill": "commitment_followup",
        "channel": "outbox",
        "versions": [
            (
                "Check whether the AgriSens dataset request moved. If not, draft a short follow-up and list what is blocked.",
                {"max_words": 120},
            ),
        ],
        "scheduled_version": None,
        "runs": [1, 1, 1, 2, 1, 1, 0, 1, 1, 1, 1, 1],
    },
    {
        "title": "Sunday review",
        "schedule": "18:00",
        "skill": "daily_digest",
        "channel": "outbox",
        "versions": [
            (
                "Review the week: what shipped, what slipped, and one decision for next week.",
                {"max_words": 180},
            ),
        ],
        "scheduled_version": None,
        "runs": [1, 0],
        "state": "paused",
    },
]


def _reply_meta(sources: list[str], *, provider: str = "demo") -> dict[str, object]:
    """Metadata a seeded assistant turn would have written in a live turn."""
    return {
        "provider": provider,
        "cost_usd": 0.0,
        "sources": sources,
        "trace": [
            {"stage": "retrieve", "label": f"{len(sources)} memory sources, ~135 tokens"},
            {"stage": "model", "label": "mitra/local-demo · 752+186 tok"},
            {"stage": "done", "label": "local demo model · $0.0000"},
        ],
    }


SESSIONS = [
    {
        "title": "Dataset request to AgriSens",
        "days_ago": 2,
        "messages": [
            (
                "user",
                "Where did the AgriSens dataset request stop? I don't want to re-read the thread.",
            ),
            (
                "assistant",
                "Last recorded action was the 16:30 follow-up run on Monday: it produced a draft and marked the run done with evidence. No reply is logged after that, so the request is still open — I won't call it resolved.",
                _reply_meta(["projects.md", "message:agrisens-thread#12"]),
            ),
            (
                "user",
                "Okay. Remember that I prefer a short written follow-up before I call Ellis on Thursday.",
            ),
            (
                "assistant",
                "Noted as a candidate memory. I won't write it to the self-model myself; it will appear in the approval inbox after consolidation so you can accept or reject it.",
                _reply_meta(["people.md", "preferences.md", "message:agrisens-thread#16"]),
            ),
        ],
    },
    {
        "title": "Literature scan: nitrogen indices",
        "days_ago": 5,
        "messages": [
            (
                "user",
                "Search for recent work on Sentinel-2 nitrogen indices in oil palm. I need method and limitation, not hype.",
            ),
            (
                "assistant",
                "I found two usable sources through the web search tool. Both report red-edge indices, but one is a single-plantation study with no cross-site validation — the limitation matters more than the accuracy number.",
                _reply_meta(["projects.md", "web_search:sentinel-2-red-edge"]),
            ),
            ("user", "Save the comparison as a note for the methods section."),
            (
                "assistant",
                "That is a write outside the memory inbox, so it needs approval. I've queued the note in the approval inbox; once you approve it, the file is written under data/notes.",
                _reply_meta(["projects.md"]),
            ),
        ],
    },
    {
        "title": "Yesterday's failed brief",
        "days_ago": 1,
        "messages": [
            ("user", "Did the brief run yesterday? The push never arrived."),
            (
                "assistant",
                "The run happened and produced a result, but delivery failed on the ntfy lane — the ledger shows delivery_failed, not done, and a fallback notice was written. The verified result is still on disk; I can re-deliver it now.",
                _reply_meta(["commitment:Weekly nutrient literature scan", "outbox:NOTICE"]),
            ),
            ("user", "So the task itself was fine."),
            (
                "assistant",
                "Correct: the evidence check passed. Delivery is a separate stage in this system by design, which is why you're seeing a delivery failure instead of a silent gap.",
                _reply_meta(["commitment:Weekly nutrient literature scan"]),
            ),
        ],
    },
    {
        "title": "Submission week plan",
        "days_ago": 0,
        "messages": [
            ("user", "What actually needs a decision from me today?"),
            (
                "assistant",
                "Three memory proposals are waiting in the approval inbox, plus one queued notification approval. The paused Sunday review is not counted as a decision — it stays paused until you decide.",
                _reply_meta(["priorities.md", "preferences.md", "approvals:pending"]),
            ),
            ("user", "Which one is actually blocking the submission?"),
            (
                "assistant",
                "The AgriSens dataset request. The 16:30 follow-up delivered, but no reply is logged after it, and the November validation run needs that export before it can start. The other two proposals change how briefs are written — they improve the work, they do not gate it.",
                _reply_meta(
                    [
                        "projects.md",
                        "message:agrisens-thread#12",
                        "commitment:Dataset request follow-up",
                    ]
                ),
            ),
        ],
    },
]

PROPOSALS = [
    {
        "page": "people.md",
        "kind": "person",
        "title": "Ellis prefers written context before calls",
        "body": "Dr. Ellis Tan prefers a short written follow-up before Thursday calls.",
        "rationale": "Stated directly by the owner; affects how follow-ups are drafted.",
        "refs": [14, 15],
    },
    {
        "page": "preferences.md",
        "kind": "preference",
        "title": "Weekday briefs: three bullets",
        "body": "Weekday briefs should stay at three bullets; longer reflections are for Sundays only.",
        "rationale": "Repeated correction across two briefs this week.",
        "refs": [22, 31],
    },
    {
        "page": "projects.md",
        "kind": "project",
        "title": "Dataset request is the critical path",
        "body": "The AgriSens dataset request is the critical path for the November validation run.",
        "rationale": "Confirmed twice while planning the week; useful when prioritising work.",
        "refs": [8, 19],
    },
]

APPROVAL = {
    "tool": "notify_send",
    "args": {
        "text": "Morning brief is ready (3 bullets, evidence verified). Open the dashboard to see the sources.",
    },
}

SEARCH_CACHE = {
    "default": {
        "query": "Sentinel-2 nitrogen estimation oil palm",
        "results": [
            {
                "title": "Sentinel-2 — Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Sentinel-2",
                "content": "Sentinel-2 is a European Space Agency optical imaging mission with 13 spectral bands, including red-edge bands used for vegetation indices.",
                "score": 0.91,
            },
            {
                "title": "Oil palm — Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Oil_palm",
                "content": "Oil palm is a major tropical crop; nutrient management, especially nitrogen and potassium, strongly affects yield.",
                "score": 0.88,
            },
            {
                "title": "Precision agriculture — Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Precision_agriculture",
                "content": "Precision agriculture uses remote sensing and site-specific management to match inputs to crop needs.",
                "score": 0.81,
            },
        ],
        "note": "Cached demo sources (Tavily is not configured on this instance).",
    }
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _at(days_ago: int, hour: int, minute: int) -> float:
    now = datetime.now(WIB)
    day = (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if day > now:
        day -= timedelta(days=1)
    return day.timestamp()


def _insert_run(
    ledger: Ledger,
    *,
    commitment_id: str,
    version_id: int,
    at: float,
    state: str,
    title: str,
    index: int,
    delivery_channel: str,
    failure: str | None = None,
    artifacts: Path,
) -> str:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    ledger._conn.execute(
        "INSERT INTO task_runs (id, commitment_id, instruction_version_id, run_at, state, error,"
        " delivered_at, delivery_receipt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            commitment_id,
            version_id,
            at,
            state,
            failure,
            at + 22 if state == "done" and delivery_channel == "outbox" else None,
            json.dumps({"lane": "outbox", "demo": True}) if state == "done" else None,
        ),
    )
    ledger._conn.commit()

    stamp = datetime.fromtimestamp(at, tz=WIB).strftime("%Y%m%d-%H%M%S")
    facts_path = artifacts / f"facts-{stamp}-{index}.json"
    artifact_path = artifacts / f"brief-{stamp}-{index}.md"
    facts_path.write_text(
        json.dumps(
            {
                "seeded": True,
                "commitment": title,
                "window_hours": 24,
                "note": "Synthetic demo facts — no real repository scan.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    artifact_path.write_text(
        f"# {title} — {datetime.fromtimestamp(at, tz=WIB):%Y-%m-%d}\n\n"
        "- Selesai: the scheduled run produced a result inside the instruction budget.\n"
        "- Tertunda: the AgriSens dataset reply is still open.\n"
        "- Prioritas: confirm the validation split, then ship the submission.\n\n"
        "> Synthetic demo artifact. The production skill writes the same shape from real facts.\n",
        encoding="utf-8",
    )

    passed = state == "done" or (state == "delivery_failed")
    evidence_ids = []
    for kind, path, summary in (
        ("facts", facts_path, "activity facts (source of the summary)"),
        ("artifact", artifact_path, "rendered brief"),
    ):
        cursor = ledger._conn.execute(
            "INSERT INTO evidence (run_id, kind, path, sha256, summary, check_result,"
            " check_detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                kind,
                str(path),
                _sha(path.read_text(encoding="utf-8")),
                summary,
                "passed" if passed else "failed",
                f"OK: 3 bullets, {len(artifact_path.read_text())} chars (demo)"
                if passed
                else "3 bullets > limit of 2 (demo failure)",
                at + 18,
            ),
        )
        evidence_ids.append(cursor.lastrowid)

    if state in {"done", "delivery_failed"}:
        ledger._conn.execute(
            "UPDATE task_runs SET evidence_id = ? WHERE id = ?", (evidence_ids[-1], run_id)
        )
    ledger._conn.commit()
    return run_id


def seed(data_dir: str | Path, *, fresh: bool = False) -> Path:
    root = Path(data_dir)
    if fresh and root.exists():
        # Clear the contents instead of the directory itself: the data dir is a
        # volume mount in the container and cannot be removed, only emptied.
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "outbox").mkdir(exist_ok=True)
    (root / "notes").mkdir(exist_ok=True)
    (root / "search_cache").mkdir(exist_ok=True)

    selfmodel = SelfModel(root / "self_model")
    for name, page in PAGES.items():
        selfmodel.write(
            name,
            str(page["body"]),
            frontmatter={"title": page["title"], "owner": PERSONA, "synthetic": True},
        )

    ledger = Ledger(root / "ledger.db")
    random.seed(42)

    now = time.time()
    commitments: dict[str, str] = {}
    for spec in COMMITMENTS:
        commitment_id = ledger.add_commitment(
            title=str(spec["title"]),
            skill=str(spec["skill"]),
            schedule=str(spec["schedule"]),
            timezone_name="Asia/Jakarta",
            delivery_channel=str(spec["channel"]),
        )
        commitments[str(spec["title"])] = commitment_id
        if spec.get("state") == "paused":
            ledger._conn.execute(
                "UPDATE commitments SET state = 'paused' WHERE id = ?", (commitment_id,)
            )
        versions = list(spec["versions"])
        version_ids = []
        for offset, (content, params) in enumerate(versions):
            effective = _at(30 - offset * 14, 0, 0)
            version_ids.append(
                ledger.add_instruction_version(
                    commitment_id,
                    content=str(content),
                    params=dict(params),
                    effective_from=effective,
                )
            )
        scheduled = spec.get("scheduled_version")
        if scheduled:
            ledger.add_instruction_version(
                commitment_id,
                content=str(scheduled[0]),
                params=dict(scheduled[1]),
                effective_from=now + 18 * 3600,
            )
        # Runs: walk back from yesterday to keep today's schedule honest.
        run_days = len(spec["runs"])
        for index in range(run_days):
            outcome = spec["runs"][index]
            days_ago = run_days - index
            hour, minute = (int(p) for p in str(spec["schedule"]).split(":"))
            at = _at(days_ago, hour, minute)
            state = "done" if outcome == 1 else ("failed" if outcome == 0 else "delivery_failed")
            failure = None
            if state == "failed":
                failure = "evidence check failed: 3 bullets > limit of 2 (demo failure)"
            elif state == "delivery_failed":
                failure = "ntfy http 503 (demo: push lane unavailable)"
            _insert_run(
                ledger,
                commitment_id=commitment_id,
                version_id=version_ids[-1],
                at=at,
                state=state,
                title=str(spec["title"]),
                index=index,
                delivery_channel=str(spec["channel"]),
                failure=failure,
                artifacts=root / "artifacts",
            )
        if spec.get("state") != "paused":
            hour, minute = (int(p) for p in str(spec["schedule"]).split(":"))
            _insert_run(
                ledger,
                commitment_id=commitment_id,
                version_id=version_ids[-1],
                at=_at(0, hour, minute),
                state="done" if spec["channel"] == "outbox" else "delivery_failed",
                title=str(spec["title"]),
                index=99,
                delivery_channel=str(spec["channel"]),
                failure=None if spec["channel"] == "outbox" else "ntfy http 503 (demo)",
                artifacts=root / "artifacts",
            )

    # Conversations (real ledger rows: search + chat work on them).
    message_refs: list[int] = []
    for session in SESSIONS:
        session_id = f"ses_demo_{uuid.uuid4().hex[:8]}"
        ledger.ensure_session(session_id, str(session["title"]))
        base = now - int(session["days_ago"]) * 86400 - 3 * 3600
        for i, message in enumerate(session["messages"]):
            role, content = message[0], message[1]
            extra = message[2] if len(message) > 2 else {}
            mid = ledger.log_message(
                session_id,
                role,
                content,
                at=base + i * 420,
                meta={"seeded": True, **extra},
            )
            message_refs.append(mid)
        ledger._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (base + (len(session["messages"]) - 1) * 420 + 60, session_id),
        )
    ledger._conn.commit()

    # Pending proposals + one approved example.
    for proposal in PROPOSALS:
        page = str(proposal["page"])
        before = selfmodel.read(page).body.strip()
        ledger.add_proposal(
            kind=str(proposal["kind"]),
            page=page,
            title=str(proposal["title"]),
            body=str(proposal["body"]),
            before=before,
            after=f"{before}\n- {proposal['body']}\n",
            rationale=str(proposal["rationale"]),
            source_refs=[int(r) for r in proposal["refs"] if r <= len(message_refs)],
        )
    approved_id = ledger.add_proposal(
        kind="pattern",
        page="patterns.md",
        title="Batch admin after 16:00",
        body="Admin and email work is batched after 16:00, not during morning deep work.",
        before=selfmodel.read("patterns.md").body.strip(),
        after=selfmodel.read("patterns.md").body.strip()
        + "\n- Admin and email work is batched after 16:00, not during morning deep work.\n",
        rationale="Observed across the last three weeks of sessions.",
        source_refs=[message_refs[-1]] if message_refs else [],
    )
    ledger.decide_proposal(approved_id, decision="approved")

    ledger.add_approval(tool=APPROVAL["tool"], args=APPROVAL["args"], session_id="ses_demo")

    # Model usage: labelled `seed`, never presented as live Nemotron spend.
    models = [
        ("nvidia/nemotron-3-super-120b-a12b", "chat", 0.30, 0.90),
        ("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "fast", 0.06, 0.24),
        ("nvidia/Nemotron-3-Ultra-550b-a55b", "reasoning", 1.00, 3.00),
    ]
    for day in range(7, -1, -1):
        for _ in range(random.randint(2, 9)):
            model, purpose, price_in, price_out = random.choice(models)
            prompt = random.randint(500, 5200)
            completion = random.randint(120, 900)
            at = now - day * 86400 - random.randint(0, 20) * 3600
            ledger.record_model_call(
                provider="seed",
                model=model,
                purpose=purpose,
                latency_s=round(random.uniform(0.6, 4.8), 2),
                prompt_tokens=prompt,
                completion_tokens=completion,
                cost_usd=(prompt * price_in + completion * price_out) / 1_000_000,
                session_id="ses_demo",
                finish_reason="stop",
                at=at,
            )

    audit_rows = [
        ("tool_call", "web_search", "allowed", "low", {"query": "Sentinel-2 nitrogen oil palm"}),
        ("tool_exec", "web_search", "executed", "low", {"ms": 890, "ok": True}),
        ("tool_call", "note_write", "approval_required", "medium", {"chars": 1840}),
        ("tool_approval", "approval:1", "approved", "high", {"lane": "dashboard"}),
        ("tool_exec", "note_write", "executed", "medium", {"ms": 12, "ok": True}),
        ("tool_call", "run_shell", "denied", "high", {"reason": "unknown tool 'run_shell'"}),
        (
            "tool_call",
            "web_fetch",
            "denied",
            "high",
            {
                "url": "http://169.254.169.254/latest/meta-data/",
                "reason": "private address blocked by egress policy",
            },
        ),
        (
            "tool_call",
            "memory_write",
            "denied",
            "medium",
            {"page": "priorities.md", "reason": "chat is read-only; a proposal is required"},
        ),
        ("consolidation", "window:24h", "executed", "low", {"created": 3, "method": "model"}),
        ("memory_edit", "projects.md", "executed", "medium", {"chars": 412}),
        ("tool_call", "notify_send", "approval_required", "high", {"lane": "ntfy"}),
        ("manual_run", commitments["Morning research brief"], "executed", "low", {}),
        ("scheduler_error", "tick", "executed", "medium", {"error": "host asleep at 07:00"}),
    ]
    for index, (action, target, decision, risk, detail) in enumerate(audit_rows):
        ledger.record_audit(
            action=action,
            target=target,
            decision=decision,
            risk=risk,
            detail=detail,
            actor="user" if "approval" in action or "memory" in action else "mitra",
            at=now - (len(audit_rows) - index) * 37 * 60,
        )

    for name, payload in SEARCH_CACHE.items():
        (root / "search_cache" / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Explicit statements make the consolidation demo produce something real.
    ledger.log_message(
        "ses_demo",
        "user",
        "Remember that I prefer Indonesian for personal notes, English for anything I publish.",
        at=now - 5400,
        meta={"seeded": True, "correction": True},
    )

    commitment_name = commitments["Weekly nutrient literature scan"]
    notice = root / "outbox" / f"NOTICE-{datetime.now(UTC):%Y%m%d-%H%M%S}-demo01.md"
    notice.write_text(
        "# Commitment disruption\n\n"
        f"- commitment: Weekly nutrient literature scan (`{commitment_name}`)\n"
        "- stage: delivery\n"
        "- error: ntfy http 503 (demo: push lane unavailable)\n"
        "- result kept: the verified digest is still in `artifacts/`\n\n"
        "Action: re-deliver or check the ntfy topic. Delivery failure does not invalidate "
        "the verified result.\n",
        encoding="utf-8",
    )

    ledger.log_event(
        "demo_seeded",
        detail={"persona": PERSONA, "synthetic": True, "commitments": len(commitments)},
    )

    # Seeding writes every event within the same second, which makes a believable
    # history look fake. Spread the seeded events over the previous day, keeping
    # their insertion order; runtime events keep their real timestamps.
    rows = ledger._conn.execute("SELECT id FROM events ORDER BY id").fetchall()
    window_start = now - 27 * 3600
    step = (27 * 3600 - 240) / max(1, len(rows) - 1)
    for offset, row in enumerate(rows):
        ledger._conn.execute(
            "UPDATE events SET at = ? WHERE id = ?", (window_start + offset * step, row["id"])
        )
    ledger._conn.commit()
    ledger.close()
    return root
