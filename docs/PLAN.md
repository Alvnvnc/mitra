# Mitra — Build plan

**Submission deadline: Oct 30, 2026, 10:00 PDT** (≈ Oct 31, 00:00 WIB). Judging
Dec 1–15; winners announced Jan 11. Solo build, no physical hardware.

## Problem (locked 2026-10-02)

Users of a personal AI who delegate recurring commitments through conversation still carry the
oversight burden: keeping instructions current, verifying that tasks actually ran, and chasing
results or failures. This erodes the net benefit of delegation and lowers trust.

- Full statement — scope, assumptions, objectives, metrics, falsification conditions:
  [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) (Indonesian; English version before submission).
- Supporting evidence: [COMMUNITY_RESEARCH.md](COMMUNITY_RESEARCH.md).

**Alignment rule:** every feature must answer two questions — which cause does it address, and
which success metric does it improve? Features that cannot answer both are cut.

## Locked decisions (2026-10-02)

| Decision | Choice | Notes |
|---|---|---|
| Problem | Delegation oversight burden (locked 2026-10-02) | [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) |
| Track | Personal AI | best fit; judges want memory across sessions + real actions |
| Build approach | Full custom (no NemoClaw/Hermes) | we implement the policy/security layer ourselves |
| Hosting | New VM on Nebius AI Cloud | always-on agent; inference on Token Factory |
| Interfaces | ntfy.sh push + web dashboard (Telegram bot optional) | web dashboard is the judges' demo surface |
| License | MIT | visible at the top of the repo page |
| Stack | Python 3.11+, FastAPI, SQLite (WAL), Docker Compose | |
| Embeddings | Qwen3-Embedding-8B via Token Factory | fallback: FTS5 + recency only |
| Web search | Tavily | best-effort $3k bonus award (runtime call) |
| Name | "Mitra" (working title) | Indonesian for "partner"; rename is cheap now |

## Milestones

### W1 — Oct 2–9 — Foundation & problem validation
- [ ] Claim credits: code `NEBIUS-DEVPOST-GLOBAL26` + Nebius Builders Program (+$25 + Tavily/AI Cloud credits)
- [x] Token Factory API key → `python scripts/smoke_test.py --all` responds for all 4 models (verified 2026-10-02: 4/4 OK, 0.7–2.1s)
- [x] `git init` + public GitHub repo with MIT visible at top
- [x] Dev env on laptop: `pip install -e ".[dev]"`, `pytest -q` green
- [ ] Run the [validation scenarios S1–S5](VALIDATION_SCENARIOS.md); record baseline M1–M5 in `validation/observation_log.csv` — progress: S1 ✅ (2026-10-02), S3 ✅ (2 runs), S5 🔄, S2 baseline window done 5–9 Oct with two silent incidents (7 Oct +7h25m late; 9 Oct missed entirely) — now awaiting user-side observations + interviews (kit ready) before the gate
- [ ] Create the Nebius AI Cloud VM (CPU preset, Ubuntu 24.04, public IP) — can slip to W2
- **Exit:** baseline recorded + decision gate passed; smoke test OK; repo public; VM reachable via SSH.

### W2 — Oct 10–16 — Memory core
- [ ] Ledger schema + migrations; event ingestion (messages, tasks, tool calls)
- [ ] Self-model store (Markdown + frontmatter read/write)
- [ ] Consolidation v1 (fast model): window → facts → approval inbox → apply
- [ ] Retrieval v1 (FTS5 + embeddings hybrid; bounded context builder)
- [ ] Model router wired into the agent loop; cost/latency persisted
- [ ] Skills v1 + Tavily `web_search` tool; policy engine v1 (allowlist + audit)
- **Exit:** conversation persists across restarts; consolidation produces diffs; tests for memory + policy.

### W3 — Oct 17–23 — Always-on & interfaces
- [ ] Telegram bot — optional lane (commands, approvals, streaming)
- [ ] Web dashboard: chat + Memory Inspector + Skills + Policy/Audit + Stats
- [ ] Scheduler: morning brief 07:00, consolidation 23:30, weekly review Sunday
- [ ] Docker Compose + TLS (Caddy) on the VM; restart policies
- **Exit:** system runs 72h unattended; dashboard reachable from the internet.

### W4 — Oct 24–30 — Ship
- [ ] Demo instance with synthetic seed + demo access; rate limit
- [ ] 3-minute video: memory across sessions, a real action (Tavily research → note), routing stats, explicit Nebius/NVIDIA usage
- [ ] Judge-ready README (setup, architecture, model usage, feedback notes)
- [ ] Devpost: description, video URL, demo URL, repo URL, feedback section
- [ ] Submit by **Oct 28** (2-day buffer)
- **Exit:** submitted; fallback recording plan for demo instability.

## Bonus targets

| Bonus | Prize | How |
|---|---|---|
| Best Use of Tavily | $3,000 | `web_search` tool makes real runtime calls inside skills |
| Most Valuable Feedback | $100 + NVIDIA swag (×10) | honest feedback section on Nebius + NVIDIA tooling |
| City Winner | $500 (×20) | only if attending a Builders & Brews event (nearest: Singapore / Kuala Lumpur / Da Nang) |

Note: per the rules, a submission can win **(1 Overall Award OR 1 Track Award)
+ 1 Bonus Award** — Tavily/feedback bonuses stack with a track result.

## Risks

| Risk | Mitigation |
|---|---|
| Problem hypothesis wrong | falsification conditions in [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md); validate scenarios early in W1 |
| Solo scope creep | weekly exit criteria; cut "nice" features, protect the demo path |
| AI Cloud credits not granted | a small CPU VM is inexpensive; monitor billing; stop when idle until W3 |
| Token budget | routing keeps personal-volume cost in the single-digit $/month range; cost dashboard proves it |
| Demo fragility | record the video on a stable build; canned fallback data |
| Judges' environment blocks Telegram | ntfy.sh push is the default lane; dashboard is the primary demo URL |

## Budget sketch (personal volume)

- Super-heavy usage: ~50k input + 10k output/day → ≈ $0.024/day ≈ $0.70/month.
- Nightly consolidation on Nano: cents/month.
- Occasional Ultra planning/research: well under $1/month at low call volume.
- Embeddings (Qwen3-Embedding-8B): $0.01/1M tokens — negligible.
- **Total:** low single-digit $/month → the $25–$50 credits are plenty, and the
  dashboard makes the leanness visible (it is part of the story).

## Immediate checklist (this week)

- [ ] `cp .env.example .env` → set `NEBIUS_API_KEY`
- [ ] `python scripts/smoke_test.py --all`
- [ ] Try the three models in the Token Factory playground; note latency
- [ ] Read `docs/SETUP_NEBIUS.md`; create the VM
- [ ] Register a Devpost submission draft (solo)