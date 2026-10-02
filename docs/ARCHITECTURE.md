# Mitra — Architecture

Status: draft v0.1 (2026-10-02). This document is the contract for what we build
during the four weeks of the hackathon. Update it when a decision changes.

## 1. What this is

Mitra is a self-hosted, always-on personal AI. It runs on a VM the owner controls
(Nebius AI Cloud), talks to its owner through Telegram and a web dashboard, keeps
persistent memory that grows across sessions, executes reusable skills, and governs
all tool access with an explicit policy layer.

Hackathon hard rule: inference runs on **Nebius Token Factory** using **NVIDIA
Nemotron** open models. Everything else is ours (this is a "full custom" build —
no NemoClaw/Hermes; we implement the equivalent guarantees ourselves).

## 2. Design principles

1. **Own the whole thing** — open weights, open code (MIT), user-owned data in
   inspectable formats (Markdown + SQLite), on a VM the user controls.
2. **Memory is the product.** A chatbot with a system prompt is not a personal AI.
   Memory layers + consolidation + corrections are the core differentiator.
3. **Write path ≠ read path.** Chat only *reads* memory. Memory is only *written*
   by the nightly consolidation job or by explicit user action — and consolidation
   proposals land in an approval inbox before being applied.
4. **Human-readable first.** The self-model is Markdown the user can read and edit.
   SQLite is the ledger/audit; it is not the only source of truth.
5. **No hidden actions.** Every tool call is allowlisted, logged, and — for risky
   tools — approved. Deny by default.
6. **Budget-aware routing.** Cheap models for volume, the big model only where it
   pays off, with live cost visibility.

## 3. Component map

```
┌────────────────────────────────────────────────────────────────┐
│ Interfaces                                                     │
│   Telegram bot            Web dashboard (FastAPI + SSE)        │
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
| Episodic | `ledger.db`: events, messages, tasks, corrections, audit | capture hooks | retrieval |
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
consolidation job reads them and updates `preferences.md`.

Optional stretch (only if time permits): run the consolidation job on
**Nebius Serverless Jobs** instead of the VM cron — mentioned as encouraged in
the hackathon track.

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

## 6. Skills & tools

- A **skill** = manifest (`skill.yaml`: name, description, params, required tools,
  risk) + implementation (`skill.py`) or procedural playbook (`SKILL.md`).
- Built-in v1: `morning_brief`, `research_digest`, `memory_recall`, `journal`.
- **Learned skills**: after a complex task the agent can *propose* a playbook draft
  (Markdown) into the inbox; approval saves it for reuse. Generated code is never
  auto-executed — by design.
- **Tools**: `web_search` (Tavily), `memory_search`, `memory_write` (only via
  approved paths), `notes_read`, `scheduler_add`, `telegram_send`. Each tool
  declares required egress hosts and a risk level.

## 7. Policy engine (our replacement for OpenShell)

| Control | Implementation |
|---|---|
| Tool allowlist | session starts with an explicit tool set; unknown tool = denied |
| Egress allowlist | single `http_client` wrapper; exact host match, HTTPS only: `api.tokenfactory.nebius.com`, `api.tavily.com`, `api.telegram.org` |
| Approval gates | risky actions (writes outside `data/`, shell exec, non-allowlisted egress) require approval via Telegram buttons / dashboard modal; timeout = deny |
| Secrets discipline | keys read from env at execution time; never embedded in prompts or logs |
| Audit | every tool call + approval decision recorded in SQLite; surfaced in the dashboard |

## 8. Data layout

```
data/                       (gitignored — private)
  ledger.db                 events, messages, tasks, corrections, audit, embeddings
  self_model/               people.md, projects.md, priorities.md, preferences.md, patterns.md
  inbox/                    proposed memory diffs + proposed skills
  sessions/                 per-session snapshots / rolling summaries
```

The public demo instance uses synthetic seeded data (`scripts/seed_demo.py`, W4).
Real personal data never appears in the public repo or demo.

## 9. Interfaces

- **Telegram**: `/start`, `/brief`, `/memory <query>`, `/skills`; inline approval
  buttons; long answers stream via message edits.
- **Web dashboard**: chat (SSE streaming) + **Memory Inspector** (timeline,
  self-model pages, pending diffs) + Skills + Policy/Audit + Stats (routing,
  latency, cost). Single-user token auth (demo account proxy for judges).

## 10. Deployment

- Nebius AI Cloud VM (Ubuntu 24.04), Docker Compose:
  - `mitra` — web app + bot + scheduler in one service (single-user scale)
  - `caddy` — TLS termination for the dashboard
- Always-on: compose restart policy (`unless-stopped`); nightly consolidation via
  internal scheduler.
- Secrets on the VM live in `.env` (not in the image, not in git).

## 11. Failure modes & mitigations

| Failure | Mitigation |
|---|---|
| Token Factory latency/outage | retries (client `max_retries`), clear user-facing error, memory reads stay local |
| Telegram API friction | web dashboard is the primary demo surface; bot is secondary |
| VM restarts | compose restart policy; SQLite WAL mode; periodic backup of `data/` |
| Model catalog changes | model ids configurable via env; smoke test catches drift |
| Demo data privacy | synthetic seed only; `.gitignore` protects `data/` |

## 12. Open questions

- Embeddings now vs FTS5-only until W3 (fallback exists either way).
- TLS on the VM: real domain via Caddy vs sslip.io-style hostname — decide in W3.
- Final project name ("Mitra" is a working title).