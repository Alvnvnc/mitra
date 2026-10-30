# Mitra

[![MIT License](https://img.shields.io/badge/license-MIT-1c5a41)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-mitra.pavernor.tech-1c5a41)](https://mitra.pavernor.tech)
[![Track](https://img.shields.io/badge/NVIDIA%20%C3%97%20Nebius-Personal%20AI-16150f)](https://nebiusglobalaihackathon.devpost.com/)

**A private, always-on personal AI that keeps its promises in writing.**

Built for the [NVIDIA × Nebius Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/) — **Personal AI Track**.
Inference runs on **NVIDIA Nemotron** models served by **Nebius Token Factory**; everything else — memory, scheduler, policy, evidence gate, dashboard — is this repository, MIT licensed, running on one VM you control.

**Live demo:** <https://mitra.pavernor.tech> — seeded synthetic history, live Nemotron inference, click through it.

![Today view](docs/media/today.png)

---

## The problem Mitra solves

Most "personal AI" is a chat window with a system prompt and amnesia. Ask it to take over recurring work and you get three new chores:

1. you have to re-explain the task every time the instructions change,
2. you cannot tell whether "done" means done or means *the model said so*,
3. failures are silent until you go looking for them.

Mitra is built around the **commitment** — a recurring piece of delegated work — and three invariants that are enforced in code, not in a prompt:

| Invariant | How it is enforced | Where |
|---|---|---|
| **O1 — only the currently approved instruction runs** | Instructions are append-only versions with an `effective_from`. The scheduler resolves the version effective *at run time*; a change dated "tomorrow" cannot leak into today's run. | `ledger.py`, `scheduler.py` |
| **O2 — "done" requires evidence that passed** | A run cannot reach `done` unless every evidence item (facts + artifact) has a *passed* check from the skill's deterministic `verify()`. The model's prose is never the proof. | `runner.py`, `ledger.complete_run` |
| **O3 — a failure surfaces without being asked** | Delivery is a separate stage from execution. A delivery failure becomes `delivery_failed` + a `NOTICE` in the outbox + a banner in the dashboard — never a silent gap. | `runner.py`, `delivery.py` |

Everything else follows from those three: an approval inbox for memory writes, a governor for every tool call, a ledger that records cost per call, and a dashboard that shows the ledger *as it is* rather than a summary of it.

## What is in this repository

```
src/mitra/
  ledger.py          SQLite ledger: commitments, instruction versions, runs, evidence,
                     delivery, sessions, messages, proposals, approvals, audit, model calls.
                     Enforces O1/O2/O3 as database-level invariants.
  runner.py          One run: resolve instruction → execute skill → check evidence →
                     complete or fail → deliver as a separate stage → notice on failure.
  scheduler.py       Due-commitment tick loop (in-process, single user by design).
  policy.py          Policy engine: allowlist, risk tiers, egress hosts, approvals, audit.
  tools.py           The only door to the outside world: web_search, memory_search,
                     commitment_status, artifact_read, note_write, notify_send.
  agent.py           Chat loop with tool calls, retrieval, budget guard, trace capture.
  consolidation.py   Nightly memory proposals from the last window — never direct writes.
  skills/            daily_digest, morning_brief, commitment_followup, research_digest.
  models/router.py   Purpose → model routing (fast / chat / reasoning) + cost accounting.
  models/demo.py     Deterministic local composer used when no API key is present.
  web/app.py         FastAPI app: dashboard, JSON API, SSE chat stream, security headers.
  web/static/        The dashboard — vanilla ES modules, no build step, self-hosted fonts.
docker/              Dockerfile entrypoint + Caddyfile for a TLS front door.
scripts/             serve.py, seed_demo.py, capture_screens.py, record_demo.py,
                     smoke_test.py, demo_vertical_slice.py, run_scheduler.py, ntfy_ping.py.
tests/               68 tests: ledger invariants, policy, agent, consolidation, skills,
                     rate limits, secret handling, HTTP surface.
docs/                architecture, problem statement, validation plan, media, feedback.
```

## Run it

### One command (Docker)

```bash
docker compose up -d --build
# → http://localhost:8080
```

The container seeds a synthetic demo instance on first boot (persona, commitments, 20 runs, proposals, audit trail), runs as a non-root user, and keeps state in a named volume. With no `NEBIUS_API_KEY` it uses the deterministic local model and labels itself as demo in the UI.

### From source

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# optional: NEBIUS_API_KEY, TAVILY_API_KEY, NTFY_TOPIC — everything degrades honestly without them
cp .env.example .env

.venv/bin/python scripts/seed_demo.py --fresh           # synthetic demo instance
MITRA_DATA_DIR=data/demo MITRA_DEMO_MODE=1 \
  .venv/bin/python scripts/serve.py --port 8080         # dashboard
.venv/bin/python scripts/run_scheduler.py --once       # one scheduler tick against real skills
.venv/bin/python -m pytest -q                          # 68 tests
```

### Deploying it publicly

`docker-compose.yml` publishes the app on `127.0.0.1` only — put a tunnel or a
reverse proxy in front and never publish `0.0.0.0:8080`. The live instance runs
behind Cloudflare Tunnel at <https://mitra.pavernor.tech>, with the exact wiring
in [docs/DEPLOY.md](docs/DEPLOY.md).

```bash
# .env on the server (mode 600)
NEBIUS_API_KEY=…            # the only real secret
MITRA_PROVIDER=auto         # Nebius, else the labelled local model
MITRA_DEMO_MODE=1           # banner + reset affordance
MITRA_BIND=127.0.0.1
MITRA_PORT=8099
MITRA_TRUST_PROXY=1         # behind the tunnel: meter real client IPs
MITRA_DAILY_BUDGET_USD=0.50
MITRA_ADMIN_TOKEN=…         # required for /api/demo/reset (openssl rand -hex 24)
```

`MITRA_DASHBOARD_TOKEN` remains available if you want to gate the whole
dashboard behind `?token=…` instead of rate-limiting a public one.

## Using Nemotron on Nebius Token Factory

Three purposes, three models, one router (`src/mitra/models/router.py`):

| Purpose | Model | Used for |
|---|---|---|
| `fast` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | extraction, classification, cheap tool-argument work |
| `chat` | `nvidia/nemotron-3-super-120b-a12b` | dashboard conversation, tool calling |
| `reasoning` | `nvidia/Nemotron-3-Ultra-550b-a55b` | planning, consolidation, research synthesis |

The router records every call — model, purpose, tokens, latency, cost — into the ledger, so the **Stats** view is a measurement, not an estimate. A daily budget ceiling (`MITRA_DAILY_BUDGET_USD`) stops runaway spend and surfaces the reason in the UI.

### Honest note about this build

Two things are fictional on the demo instance, and they are labelled:

- **the seeded history.** Commitments, runs, evidence, sessions and the persona ("Maya Rahman") are written by `demo_data.py`, so you have something to inspect. The banner on every page says so.
- **the push lane.** The delivery failure you see was seeded; live ntfy delivery needs `NTFY_TOPIC`, so it fails loudly instead of pretending.

Everything else is real. The live instance runs `provider: nebius`, and `/api/health` reports it:

```
$ curl -s https://mitra.pavernor.tech/api/health
{"ok":true,"version":"0.1.0","provider":"nebius","uptime_s":…}
```

Chat turns and skill runs hit `nvidia/nemotron-3-super-120b-a12b` (chat) and `nvidia/Nemotron-3-Ultra-550b-a55b` (planning) through Token Factory, and every call's tokens, latency and cost land in the ledger — the Stats view adds up the rows it can show you.

During the build the first API key returned `401 Unauthenticated` on both `api.tokenfactory.nebius.com` and `api.studio.nebius.ai`, so the router was written to *fail visibly*: `probe()` marks the instance degraded, the provider card says "Local demo model", and the fallback is a deterministic composer that reads the real ledger. It cannot invent a run, an approval or a cost. That path is still in the image and still tested — it is what runs if the key dies mid-demo.

### Protecting a public instance that holds a real key

A judged demo has to be clickable by strangers, and a clickable demo holds an API key. The instance is built so the key cannot be spent by one visitor, or by a crowd:

| Control | What it does |
|---|---|
| **No route to the app** | The container publishes `127.0.0.1:8099` only; Cloudflare Tunnel is the sole ingress. The port is not reachable from the internet (`connection refused`), so `CF-Connecting-IP` cannot be spoofed and there is no direct-origin bypass. |
| **Per-client limits** | 4s cooldown between chat turns, 6/hour, 20/day per address. Writes: 15/min. Counters key on the real client IP from `CF-Connecting-IP`, trusted only when `MITRA_TRUST_PROXY=1`. |
| **A global ceiling** | 80 chat turns/day across *all* addresses and 40 writes/min, so a botnet cycling IPs does not multiply the allowance. |
| **A hard money ceiling** | `MITRA_DAILY_BUDGET_USD=0.50`, checked before *every* model call — including scheduled skill runs, which use `complete()` rather than `chat()`. When it trips, the reason is shown in the UI. |
| **Admin actions are gated** | `/api/demo/reset` requires `MITRA_ADMIN_TOKEN` and is hidden in the UI unless you opened the page with `?admin=…` (which trades the secret for an HttpOnly cookie and redirects it out of the URL). A visitor cannot reseed the ledger — which matters, because the daily spend counter is derived from it. |
| **No key in any response** | A test walks the API and asserts the key string never appears; it lives only in `.env` (mode 600) and the process environment. |
| **Small surface** | `/api/docs` is off unless `MITRA_ENABLE_DOCS=1`, payloads are capped at 200 kB, chat input at 6000 chars. |
| **Headers** | CSP (`'self'` plus Cloudflare's RUM beacon), `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `no-store` on `/api/*`, `no-cache` on the shell and its code. |
| **Cache-busted code** | `/static/js/app.js?v=<mtime>-<size>`. A CDN that caches per content-encoding once served an old bundle against a new API; the URL now changes exactly when the file does. |

## The dashboard

Seven views, all reading the same ledger, in one shell: a quiet rail for
navigation, a sticky command bar (`⌘K` or `/` opens the palette), and one primary
surface per view with the supporting context in a right rail. Dense tables carry
the detail, and the demo banner stays pinned so synthetic data is never mistaken
for real work.

| View | What it is for |
|---|---|
| **Today** | What needs a human decision, what ran, what is broken, latest verified brief |
| **Chat** | Conversation with retrieval, a governed tool trace (including reading the brief a run actually wrote), per-turn cost, and a read-only write discipline |
| **Commitments** | The delegated work, its schedule, the instruction version in force |
| **Commitment detail** | Every run, every evidence item with its check result, delivery state, instruction history |
| **Memory** | Markdown self-model + the approval inbox (diff preview, approve → append, reject → untouched) |
| **Skills & tools** | Inspectable skills with their checks; every tool with risk tier, gate and egress host |
| **Audit** | Every decision, including the denied ones — that is the point |
| **Stats** | Cost, reliability, interventions, cost by purpose, calls by model |

| Memory (approval inbox) | Commitment detail | Audit |
|---|---|---|
| ![Memory](docs/media/memory.png) | ![Commitment detail](docs/media/commitment-detail.png) | ![Audit](docs/media/audit.png) |

| Chat | Skills & tools | Stats |
|---|---|---|
| ![Chat](docs/media/chat-reply.png) | ![Skills](docs/media/skills.png) | ![Stats](docs/media/stats.png) |

Mobile: layout collapses to a single column with a slide-over navigation rail (`docs/media/mobile-today.png`, `mobile-chat.png`, `mobile-memory.png`).

## Correctness, not vibes

- **Evidence gate.** `ledger.complete_run()` raises if any evidence item is unpassed. The runner has no path to `done` that skips it.
- **Version resolution.** `instruction_versions` are append-only; `resolve_instruction_version(commitment, at)` picks the version effective at the run timestamp. Tests cover "a change effective tomorrow does not apply today".
- **Delivery is separate.** `mark_delivery_failed()` never mutates the run's evidence; the verified artifact survives a delivery failure.
- **Policy before egress.** Every tool declares risk and egress hosts; `PolicyEngine` checks scheme, host, and private-address resolution through a single HTTP wrapper. Denials are audited, not dropped.
- **Memory writes need a human.** Chat is read-only against the self-model; consolidation only *proposes*.
- **Tests.** 68 tests covering ledger invariants, policy/approvals, the agent loop, consolidation, skill shape gates, rate limits, secret non-leakage, and the HTTP surface. `ruff check` and `ruff format --check` are clean.

## Limitations (deliberate)

- Single user, single process. The scheduler is in-process; scale-out is out of scope.
- Memory is lexical (SQLite + Markdown search), not embeddings. Retrieval quality is honest about what it found.
- Demo data is synthetic (persona "Maya Rahman"); the code paths, ledger, policy and gate are real.
- The ntfy lane fails in the demo on purpose — O3 is only believable if you can see a failure.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — invariants, data model, design principles
- [docs/PROBLEM_STATEMENT.md](docs/PROBLEM_STATEMENT.md) — the locked problem and objectives O1–O5
- [docs/VALIDATION_SCENARIOS.md](docs/VALIDATION_SCENARIOS.md) — how the promises are checked
- [docs/FEEDBACK.md](docs/FEEDBACK.md) — what we learned using Nebius, Nemotron, and Tavily
- [docs/SUBMISSION.md](docs/SUBMISSION.md) — Devpost copy and the 3-minute demo script

## License

MIT — see [LICENSE](LICENSE).
