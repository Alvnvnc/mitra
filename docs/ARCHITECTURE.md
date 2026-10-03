# Mitra — Architecture

Status: draft v0.2 (2026-10-04) — aligned with `docs/PROBLEM_STATEMENT.md` v1.0
(internal gap analysis R1–R6, 2026-10-02) + S1 findings. Pending the W1 validation
gate before implementation. The vertical slice (§4 commitments tables + runner +
delivery) was implemented as a draft on 2026-10-03 at the user's request to
de-risk W2; this does not waive the gate — validation data may still change the
rules. This document is the contract for the build; update it when a decision
changes.

## 1. What this is

Mitra is a self-hosted, always-on personal AI. It runs on a VM the owner controls
(Nebius AI Cloud), talks to its owner through a web dashboard and push
notifications (ntfy.sh; a Telegram bot stays optional), keeps persistent memory
that grows across sessions, executes reusable skills, and governs
all tool access with an explicit policy layer.

Hackathon hard rule: inference runs on **Nebius Token Factory** using **NVIDIA
Nemotron** open models. Everything else is ours (this is a "full custom" build —
no NemoClaw/Hermes; we implement the equivalent guarantees ourselves).

The locked problem (`docs/PROBLEM_STATEMENT.md` v1.0) is the oversight burden:
keeping instructions current, verifying execution, and chasing results. The
architecture therefore treats the **commitment** (a recurring piece of delegated
work) as the central unit and must keep three things true: only the current
approved instructions are used, "done" claims carry verified evidence, and
failures surface without the user asking.

### Objective traceability

| Objective (PROBLEM_STATEMENT §6) | Components |
|---|---|
| O1 current instructions | `commitments` + `instruction_versions`, scheduler resolve rule (§4) |
| O2 evidence-bound claims | `task_runs` + `evidence` check before any completion claim (§4) |
| O3 failures surface | delivery status separate from run status + push notifications, ≤1h target (§9, §11) |
| O4 net benefit | intervention counters + maintenance time vs W1 baseline (§5, §9) |
| O5 open infrastructure | model router → Nebius Token Factory, Nemotron family (§5) |

## 2. Design principles

1. **Own the whole thing** — open weights, open code (MIT), user-owned data in
   inspectable formats (Markdown + SQLite), on a VM the user controls.
2. **Correct context, not just stored context.** Memory is a mechanism, not the
   product. The product is fewer manual interventions: the assistant always
   resolves the *current approved* instruction version, and when context is missing
   it says so deterministically (S1 finding, 2026-10-02).
3. **Write path ≠ read path.** Chat only *reads* memory. Memory is only *written*
   by the nightly consolidation job or by explicit user action — and consolidation
   proposals land in an approval inbox before being applied.
4. **Human-readable first.** The self-model is Markdown the user can read and edit.
   SQLite is the ledger/audit; it is not the only source of truth.
5. **No hidden actions.** Every tool call is allowlisted, logged, and — for risky
   tools — approved. Deny by default.
6. **Budget-aware routing.** Cheap models for volume, the big model only where it
   pays off, with live cost visibility.
7. **No silent archaeology.** When context is missing, the agent admits it and asks.
   It never hunts through the user's files, vaults, or stores to reconstruct
   context (S1 finding, 2026-10-02: an agent searched a private vault instead of
   asking).

## 3. Component map

```
┌────────────────────────────────────────────────────────────────┐
│ Interfaces                                                     │
│   Push: ntfy.sh (default) Web dashboard (FastAPI + SSE)        │
└───────────────┬────────────────────────────┬───────────────────┘
                │                            │
┌───────────────▼────────────────────────────▼───────────────────┐
│ Agent core                                                     │
│   planner / router / executor loop                             │
│   skill registry        tool registry                          │
└───────┬─────────────────────────┬──────────────────────────────┘
        │                         │
┌───────▼─────────────────┐  ┌────▼─────────────────────────────┐
│ Memory layer            │  │ Governance                       │
│   working (session)     │  │   policy engine (allowlists,     │
│   episodic ledger (SQL) │  │   approval gates, secrets)       │
│   embeddings index      │  │   audit log                      │
│   self-model (Markdown) │  └────┬─────────────────────────────┘
│   consolidation + inbox │       │
└───────┬─────────────────┘       │
        │                         │
┌───────▼─────────────────────────▼──────────────────────────────┐
│ Model router → Nebius Token Factory (OpenAI-compatible)        │
│   fast: Nemotron 3 Nano / 3.5 Lightning                        │
│   chat: Nemotron 3 Super 120B                                  │
│   reasoning: Nemotron 3 Ultra 550B                             │
└────────────────────────────────────────────────────────────────┘
```

## 4. Memory model

### Layers

| Layer | Store | Written by | Read by |
|---|---|---|---|
| Working | session buffer + rolling summary (`sessions/`) | every turn | every turn |
| Episodic | `ledger.db`: events, messages, commitments, instruction_versions, task_runs, evidence, corrections, audit | capture hooks | retrieval |
| Embeddings | `ledger.db`: vectors as JSON blobs | capture hooks / consolidation | retrieval |
| Semantic (self-model) | `self_model/*.md` (YAML frontmatter) | consolidation (approved), user edits | retrieval, dashboard |
| Inbox | `inbox/` (proposed diffs, proposed skills) | consolidation, agent | user (approve/reject) |

### Retrieval

Hybrid, bounded, and testable:

```
score = fts5_relevance + cosine_similarity + recency_decay
context = top_k(score, budget_tokens)
```

Context assembly lives in one function (`memory/retrieval.py`) so it can be unit
tested and tuned. The agent never gets "all memory" dumped into its prompt.

### Consolidation (the nightly job)

```
window (last 24h events)
  → extract candidate facts/updates        (fast model, structured JSON)
  → diff against current self-model        (deterministic code)
  → write proposals to inbox               (never auto-apply)
  → user approves/rejects in dashboard/Telegram
  → apply: update self_model/*.md + ledger entry (provenance = source event ids)
```

Corrections from the user are first-class ledger events and always win; the
consolidation job reads them and updates `preferences.md` and the affected
commitment definitions (`instruction_versions`).

Optional stretch (only if time permits): run the consolidation job on
**Nebius Serverless Jobs** instead of the VM cron — mentioned as encouraged in
the hackathon track.

### Commitments & instruction versions

The central unit is a **commitment**: a recurring piece of delegated work
(nightly digest, weekly report, follow-up). Data model (SQLite):

| Table | Fields (essential) |
|---|---|
| `commitments` | id, title, schedule, skill, delivery channel, state |
| `instruction_versions` | id, commitment_id, content, `effective_from`, `approved_by/at`, `source_event_ids`, `supersedes_id` |
| `task_runs` | id, commitment_id, `instruction_version_id` used, run_at, state (`queued/running/done/failed/delivery_failed`), `evidence_id` |
| `evidence` | id, run_id, kind (file/message/receipt), path/hash/summary, check result |

Rules:

- The scheduler **always resolves the latest approved instruction version** at run
  time (O1/M2). No run may use a superseded version.
- Urgent corrections can be approved synchronously (no waiting for the nightly
  cycle); nightly consolidation stays for non-urgent proposals (R1).
- A completion claim is only produced when the run has **evidence that passed its
  check** (O2/M3).
- Delivery is its own state: `done` ≠ `delivered` ≠ `read` (O3).

### Embeddings

`Qwen/Qwen3-Embedding-8B` on Token Factory ($0.01 / 1M input tokens). At personal
scale (thousands of rows) vectors are stored in SQLite and cosine similarity runs
in-process. Fallback if time is tight: FTS5 + recency only — the interface does
not change.

## 5. Model routing

| Purpose | Default model | Model ID | Price in/out per 1M | Used for |
|---|---|---|---|---|
| fast | Nemotron 3 Nano 30B | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | $0.06 / $0.24 | extraction, classification, consolidation prep, titles |
| fast (alt) | Nemotron 3.5 Lightning | `nvidia/Nemotron-3_5-Lightning` | $0.06 / $0.24 | long-context fast jobs (1M context) |
| chat | Nemotron 3 Super 120B | `nvidia/nemotron-3-super-120b-a12b` | $0.30 / $0.90 | everyday chat, tool calling, drafting |
| reasoning | Nemotron 3 Ultra 550B | `nvidia/Nemotron-3-Ultra-550b-a55b` | $1.00 / $3.00 | planning, research synthesis, hard reasoning |

- Router API: `complete(purpose=..., messages=..., tool_schemas=..., ...)`.
- Every call records model, purpose, latency, tokens, estimated cost
  (`CallRecord` / `RouterStats` already implemented) → persisted to the ledger →
  surfaced in dashboard stats.
- Price table lives in code; refresh against `/api/public/models_info` when the
  catalog changes (non-blocking check).
- Structured output (evals, 2026-10-02): Lightning requires
  `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` (cleanest fix:
  19 output tokens vs 470/1113 alternatives); Nano is the safe default for
  extraction.
- Same setting applies to Super for routine digests (2026-10-03): with thinking
  on, `finish_reason` was `length` at 800 tokens (reasoning ate the budget,
  empty `content`); off → `stop`, 249 tokens, clean bullets. Keep thinking on
  only for `reasoning`-purpose work.

## 6. Skills & tools

- A **skill** = manifest (`skill.yaml`: name, description, params, required tools,
  risk) + implementation (`skill.py`) or procedural playbook (`SKILL.md`).
- Built-in v1: `morning_brief`, `research_digest`, `memory_recall`,
  `commitment_followup` (due/failed/undelivered states, ties to §4 tables).
  `journal` → out of v1 scope (no problem-statement basis; candidate v2).
- **Learned skills**: after a complex task the agent can *propose* a playbook draft
  (Markdown) into the inbox; approval saves it for reuse. Generated code is never
  auto-executed — by design.
- **Tools**: `web_search` (Tavily), `memory_search`, `memory_write` (only via
  approved paths), `notes_read`, `scheduler_add`, `notify_send` (ntfy.sh;
  Telegram bot lane optional). Each tool declares required egress hosts and a
  risk level.

## 7. Policy engine (our replacement for OpenShell)

| Control | Implementation |
|---|---|
| Tool allowlist | session starts with an explicit tool set; unknown tool = denied |
| Egress allowlist | single `http_client` wrapper; exact host match, HTTPS only: `api.tokenfactory.nebius.com`, `api.tavily.com`, `ntfy.sh`, `api.telegram.org` (optional) |
| Approval gates | risky actions (writes outside `data/`, shell exec, non-allowlisted egress) require approval via Telegram buttons / dashboard modal; timeout = deny |
| Secrets discipline | keys read from env at execution time; never embedded in prompts or logs |
| Audit | every tool call + approval decision recorded in SQLite; surfaced in the dashboard |
| Context gaps | deterministic: state "unknown" and ask; searching user storage outside the declared allowlist is forbidden (S1 finding) |

## 8. Data layout

```
data/                       (gitignored — private)
  ledger.db                 events, messages, commitments, instruction_versions, task_runs, evidence, corrections, audit, embeddings
  self_model/               people.md, projects.md, priorities.md, preferences.md, patterns.md
  inbox/                    proposed memory diffs + proposed skills
  sessions/                 per-session snapshots / rolling summaries
```

The public demo instance uses synthetic seeded data (`scripts/seed_demo.py`, W4).
Real personal data never appears in the public repo or demo.

## 9. Interfaces

- **Push (default)**: ntfy.sh topic; receipt = ntfy message id (accepted ≠ read).
- **Telegram bot (optional)**: `/start`, `/brief`, `/memory <query>`, `/skills`;
  inline approval buttons; long answers stream via message edits.
- **Web dashboard**: chat (SSE streaming) + **Memory Inspector** (timeline,
  self-model pages, pending diffs) + **Commitments** (status, instruction history,
  evidence, delivery) + Skills + Policy/Audit + Stats (routing, latency, cost,
  interventions vs W1 baseline). Failure notifications are pushed (dashboard +
  ntfy push), target ≤1h (M4).

## 10. Deployment

- Nebius AI Cloud VM (Ubuntu 24.04), Docker Compose:
  - `mitra` — web app + bot + scheduler in one service (single-user scale)
  - `caddy` — TLS termination for the dashboard
- Always-on: compose restart policy (`unless-stopped`); nightly consolidation via
  internal scheduler.
- Secrets on the VM live in `.env` (not in the image, not in git).

## 11. Failure modes & mitigations

| Failure | Stage (process/storage/delivery) | Mitigation |
|---|---|---|
| Scheduled run fails | process | recorded in `task_runs`; push notification ≤1h (M4); explicit retry policy |
| Consolidation/storage fails | storage | transaction + WAL; failure event + push; no silent downgrade (community finding #49200) |
| Result not delivered | delivery | delivery state + receipt; fallback notification lane; ≤1h target |
| Approval timeout | process | pending item stays visible; reminder to a fallback lane; deny-by-default for risky actions |
| Token Factory latency/outage | process | retries (client `max_retries`), clear user-facing error, memory reads stay local |
| Push lane failure (ntfy/Telegram) | delivery | delivery_failed + fallback NOTICE (≤1h); dashboard is the primary demo surface |
| VM restarts | storage | compose restart policy; SQLite WAL mode; periodic backup of `data/` |
| Model catalog changes | process | model ids configurable via env; smoke test catches drift |
| Demo data privacy | storage | synthetic seed only; `.gitignore` protects `data/` |

## 12. Open questions

- Embeddings now vs FTS5-only until W3 (fallback exists either way).
- TLS on the VM: real domain via Caddy vs sslip.io-style hostname — decide in W3.
- Final project name ("Mitra" is a working title).
- W1 gate outcome may adjust §4 rules (S2/S4 data pending; interviews pending).
- Notification lane decided (2026-10-04): ntfy.sh default; Telegram bot stays optional.