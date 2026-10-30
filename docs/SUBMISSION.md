# Devpost submission — copy, links, and the walkthrough video

> **The submission package is [`submission/`](../submission/README.md).** That
> folder holds the paste-ready field copy, the gallery, the 2:56 video cut and
> the upload sheets. This file keeps the longer-form context, the video beat
> sheet and the deployment notes.

- **Demo:** <https://mitra.pavernor.tech> — seeded synthetic history, **live Nemotron inference** through Nebius Token Factory
- **Repository:** https://github.com/Alvnvnc/mitra
- **Track:** Personal AI
- **Video:** 2:56 (title card + captioned walkthrough + end card), structure below

---

## Name and tagline

**Mitra** — a private, always-on personal AI that keeps its promises in writing.

## Elevator pitch (≤ 200 chars)

Mitra takes over recurring work and proves it happened: versioned instructions, an evidence gate that blocks "done" without passing checks, and failures that surface on their own.

---

## Inspiration

Every "personal AI" demo ends the same way: an impressive conversation, then you
close the tab and nothing persists. Ask it to take over something recurring — a
weekly literature scan, a follow-up on a dataset request — and you inherit three
new chores. You re-explain the task when instructions change. You can't tell
whether "done" means done or means the model said so. And when delivery breaks,
you find out days later, if at all.

We wanted the opposite: an agent whose memory is a file you can read, whose
"done" is a database constraint, and whose failures find you. That is Mitra —
Indonesian for *partner*, not *servant*.

## What it does

Mitra is a self-hosted personal agent with a dashboard, a scheduler, persistent
memory and governed tools. Its unit of work is the **commitment**: a recurring
piece of delegated work with versioned instructions, evidence-gated runs, and a
delivery state that is never assumed.

Three invariants are enforced in code, not in a prompt:

1. **Only the currently approved instruction runs.** Instructions are append-only
   versions with an `effective_from`. The scheduler resolves the version
   effective at run time — a change dated "tomorrow" cannot leak into today's run.
2. **"Done" requires evidence that passed.** A run cannot reach `done` unless
   every evidence item has a passed check from the skill's deterministic
   `verify()`. The model writes prose; the code owns the rules.
3. **Failures surface without being asked.** Delivery is a separate stage from
   execution. A delivery failure becomes `delivery_failed`, writes a `NOTICE`
   to the outbox, and raises a banner in the dashboard — never a silent gap.

Around those: an **approval inbox** for memory writes (chat is read-only; nightly
consolidation only proposes, with a diff and source message ids), a **policy
engine** that governs every tool call (risk tier, egress allowlist, approvals,
audit — including denials), **cost-aware routing** across three Nemotron tiers
with per-call accounting, and seven dashboard views that show the ledger as it is.

## How we built it

- **FastAPI + SQLite ledger** (`src/mitra/ledger.py`) is the spine. Commitments,
  instruction versions, runs, evidence, delivery receipts, sessions, proposals,
  approvals, audit entries and model calls all live in one database, with the
  three invariants expressed as constraints and guarded transitions
  (`complete_run()` raises if evidence is unpassed).
- **Runner** (`runner.py`) executes one run: resolve instruction → run skill →
  record evidence → deterministic check → complete or fail → deliver as a
  separate stage → write a notice on failure.
- **Skills** are inspectable units with `execute()` and `verify()`:
  `daily_digest`, `morning_brief`, `commitment_followup`, `research_digest`.
- **Tools** are the only door to the outside world (`tools.py`): `web_search`
  (Tavily), `memory_search`, `commitment_status`, `artifact_read` (the brief a
  run actually wrote), `note_write` (medium risk,
  needs approval), `notify_send` (high risk, needs approval). Every spec declares
  risk and egress hosts.
- **Policy engine** (`policy.py`) checks the allowlist, the risk tier, approval
  state, and the egress host before a single byte leaves the process; denials are
  audited rather than dropped.
- **Agent** (`agent.py`) is a tool-calling chat loop with retrieval from the self-model
  and the ledger, a budget guard, and a trace that the UI renders per turn. It can
  read the artifact a run produced, so "what did the brief say?" is answered from
  the file, not from a memory of the file; if it spends its tool rounds, the last
  call is a no-tools synthesis, so the turn ends in an answer rather than an
  apology.
- **Dashboard** (`web/`) is vanilla ES modules and hand-written CSS with
  self-hosted fonts — no build step, so the whole product is one `docker compose up`.
- **Models** (`models/router.py`) route by purpose: Nemotron 3 Nano for extraction,
  Super for chat and tool calls, Ultra for planning and consolidation, on Nebius
  Token Factory's OpenAI-compatible API.

## Challenges we ran into

**The hard part was not the model — it was making "done" mean something.**
Early versions let the model's prose decide completion. The fix was structural:
evidence items are rows, checks are deterministic functions, and
`complete_run()` refuses to transition unless every check passed.

**Version truth.** "Use my new instructions starting tomorrow" is easy to say and
easy to get wrong. Instructions became append-only rows with `effective_from`,
and the scheduler resolves the version against the *run* timestamp, not the
current wall clock.

**Inference that says what it is.** The submitted instance runs live:
`/api/health` reports `provider: nebius`, chat turns hit
`nvidia/nemotron-3-super-120b-a12b`, and planning runs `Nemotron-3-Ultra`. The
first key we were issued returned `401` for most of the build, so the router was
built to *fail visibly* — it probes at startup, flips to a deterministic local
composer that reads the real ledger, and labels every surface "Local demo model".
That path stays in the image, and it is what runs if the key dies mid-demo:
a degraded demo, never a lying one.

## Accomplishments we're proud of

- Three invariants that hold under tests, not just under demo conditions — 63
  tests, including "a change effective tomorrow does not apply today",
  "completion without evidence raises", and "a delivery failure leaves the
  verified artifact intact".
- An approval inbox that shows the diff before writing memory — and a rejection
  path that leaves the page byte-identical.
- Cost accounting that is measured per call (model, tokens, latency, dollars),
  so the Stats view can be trusted.
- A dashboard that tells on itself: the demo instance deliberately includes a
  failed run and a delivery failure, because O3 is only believable if you can see it.
- One command to run: `docker compose up`, non-root container, seeded demo,
  healthcheck, optional Caddy TLS.

## What we learned

- **Constraints beat prompts.** Every guarantee that mattered became a database
  invariant or a deterministic check. Prompts describe; constraints enforce.
- **Failure is a feature.** Making delivery a separate stage doubled the honest
  surface area of the product and made the demo more convincing.
- **A fallback must be louder than the model.** When inference is unavailable,
  the UI has to say so everywhere, not in a footnote.
- **OpenAI-compatible APIs remove integration risk.** Swapping the base URL was
  the whole Nebius integration.

## What's next

- Live inference verification on a funded Token Factory key, with tool-calling
  conformance tests against all three Nemotron tiers.
- Embedding-backed retrieval over the ledger (today it is lexical and says so).
- Multi-user households with per-person memory namespaces.
- Serverless Jobs for consolidation so the VM can sleep.

## Built with

`python` · `fastapi` · `sqlite` · `pydantic` · `uvicorn` · `openai` · `httpx` ·
`nvidia-nemotron` · `nebius-token-factory` · `cloudflare-tunnel` · `tavily` · `ntfy` ·
`docker` · `vanilla-js` · `css`

---

# Walkthrough script (2:56 cut)

> **A captioned picture track already exists:** `submission/video/mitra-demo.mp4`
> (2:56 including title and end cards, 1440×900, silent with burned-in captions,
> recorded against the live instance at <https://mitra.pavernor.tech> — the chat
> turn in it is a real Nemotron call, labelled `nemotron` with its ledger cost).
> Upload it as-is, or lay the narration below over it — the beats line up with
> the times in the table. Rebuild it with
> `python scripts/record_demo.py --base https://mitra.pavernor.tech --out /tmp/demo.webm`,
> then `python scripts/build_video_assets.py --base https://mitra.pavernor.tech`
> and `python scripts/mux_demo_video.py --raw /tmp/demo.webm`.

Screen recording, 1440×900 browser, demo instance running. Speak calmly; do not
narrate the UI, narrate the *guarantee*.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:02 | Title card | "Mitra: delegated work, verified." |
| 0:02–0:12 | Today view, hero + "4 things need you" | "This is Mitra. It runs recurring work for me and it proves what happened. Right now four things need a human decision — and it says so without me asking. The history is seeded; the inference underneath is live Nemotron." |
| 0:12–0:29 | Scroll to needs-you, click **View notice** | "This commitment ran, passed its evidence check, produced a verified artifact — and then delivery failed. Mitra records `delivery_failed`, writes a notice, and keeps the result. Delivery is a separate stage from execution, by design." |
| 0:29–0:44 | Commitments → open *Morning research brief* | "Every commitment is one unit of delegated work: a schedule, a skill, and exactly one instruction version in force." |
| 0:44–1:23 | Runs table, evidence counts, instruction history | "Every run carries evidence. Two checks: the artifact exists, and it has the required sections. Green means both passed. The red row is real — the skill demanded three bullets, the artifact had two, and the gate refused to call it done. And instructions are versions: v3 becomes effective tomorrow. Tomorrow's run picks it up; today's cannot. That is enforced in the scheduler, not in a prompt." |
| 1:23–1:51 | Memory view → reject a proposal | "Chat cannot write memory. Consolidation proposes a change, with the diff and the source message ids. If I reject, the page stays byte-identical. Approving appends one bullet. The model never decides what it remembers." |
| 1:51–2:24 | Chat → new conversation → "Did yesterday's brief actually deliver?" → expand the trace | "Chat reads the real ledger, retrieves the memory pages it used, calls tools through the policy layer, and shows the sources, the trace and the cost of the turn. Note the labels: `nemotron`, the model id, and six hundredths of a cent — that number is a row in the ledger, not an estimate. This is live Nemotron on Nebius." |
| 2:24–2:37 | Audit → filter **denied** | "Every decision is here, including the refused ones. `web_fetch` was denied for a private address; `run_shell` for not being on the allowlist; a memory write because chat is read-only. A security claim you can't audit isn't a security claim." |
| 2:37–2:52 | Stats view | "Cost, reliability, interventions, and calls by model — measured per call, not estimated. This is what 'always-on and trustworthy' has to look like: a ledger you can read, and a system that tells on itself." |
| 2:52–2:56 | End card | — |

## Closing line

"Mitra is MIT licensed, runs as one container, and keeps everything in files you
own. It is a partner that keeps its promises in writing."

## Thumbnail

`submission/images/devpost-thumbnail.png` (1440×960): the Today view with the
project name beneath it. `docs/media/today.png` also works, cropped to the hero:
with the delivery-failure banner visible. No text overlay needed; the type is the
design. The video title card (`.design/video/title.png`) works as a fallback.

## How the public instance is protected

A judged demo has to be clickable by strangers, and a clickable demo holds an API
key. The instance runs on a VPS behind an existing Cloudflare Tunnel, published
on `127.0.0.1:8099` only — the port refuses external connections, so the tunnel
is the single ingress and `CF-Connecting-IP` can be trusted to meter real
visitors.

| Control | Value |
|---|---|
| Chat per visitor | 4 s cooldown, 6/hour, 20/day |
| Chat across all visitors | 80/day |
| Writes | 15/min per visitor, 40/min globally |
| Hard spend ceiling | `MITRA_DAILY_BUDGET_USD=0.50`, checked before every model call, scheduled skill runs included |
| Admin actions | `/api/demo/reset` needs `MITRA_ADMIN_TOKEN`; the UI hides it unless you open `/?admin=…` (HttpOnly cookie, query string scrubbed) |
| Key exposure | only in `.env` (mode 600) and the process env; a test walks the API and asserts the key never appears in a response |
| Surface | `/api/docs` off, 200 kB payload cap, 6 000 char chat cap, CSP + `nosniff` + `DENY` framing |

Full wiring, rotation steps and a post-deploy checklist: [DEPLOY.md](DEPLOY.md).

## Swapping in a live Nebius key

```bash
ssh vps-alvn
cd ~/mitra
sed -i 's/^NEBIUS_API_KEY=.*/NEBIUS_API_KEY=NEW_KEY/' .env   # mode stays 600
docker compose -p mitra up -d                                # recreate, not rebuild
curl -s http://127.0.0.1:8099/api/health                     # "provider":"nebius"
```

The router probes the key at startup. If it authenticates, the sidebar card reads
"Nemotron · Nebius · live inference", replies are labelled `nemotron` with real
per-call cost, and the Stats view counts actual spend. If it does not, the card
says "Local demo model" and the reason — the site stays up. The synthetic-data
banner stays either way, because the seeded commitments are still synthetic.

## Submission checklist

- [x] Demo live on a real domain over HTTPS, no token needed to click through: <https://mitra.pavernor.tech>
- [x] `provider: nebius` confirmed in `/api/health` with a real key
- [x] Rate limits, spend ceiling and the admin gate exercised against the public URL
- [ ] Video uploaded (YouTube, public) — `submission/video/mitra-demo.mp4`
- [ ] Repository public, README first screen has a screenshot and the one-command run
- [ ] `docs/FEEDBACK.md` linked in the submission (feedback bonus)
- [ ] Built-with tags include: `nvidia`, `nemotron`, `nebius`, `cloudflare`, `fastapi`, `sqlite`
