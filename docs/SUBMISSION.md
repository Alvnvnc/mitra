# Devpost submission — copy, links, and the walkthrough video

Everything below is ready to paste. Replace `DEMO_URL` and `REPO_URL` once the
demo is deployed.

- **Demo:** <https://ip-172-26-13-244.tail40f715.ts.net:10000/> (synthetic instance, resettable)
- **Repository:** https://github.com/Alvnvnc/mitra
- **Track:** Personal AI
- **Video:** 3:06 (title card + captioned walkthrough + end card), structure below

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
  (Tavily), `memory_search`, `commitment_status`, `note_write` (medium risk,
  needs approval), `notify_send` (high risk, needs approval). Every spec declares
  risk and egress hosts.
- **Policy engine** (`policy.py`) checks the allowlist, the risk tier, approval
  state, and the egress host before a single byte leaves the process; denials are
  audited rather than dropped.
- **Agent** (`agent.py`) is a tool-calling chat loop with retrieval from the self-model
  and the ledger, a budget guard, and a trace that the UI renders per turn.
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

**Honest fallback.** Our Nebius API key returned `401 Unauthenticated` for the
whole build (verified directly against `/v1/models` on both documented base
URLs). We refused to fake live inference, so the app ships a deterministic local
composer that reads the *real* ledger and labels itself "Local demo model · no
API key" on every surface. The live path is implemented and tested with a stub;
`scripts/smoke_test.py` is the first command to run with a valid key.

## Accomplishments we're proud of

- Three invariants that hold under tests, not just under demo conditions — 44
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
`nvidia-nemotron` · `nebius-token-factory` · `tavily` · `ntfy` · `docker` ·
`caddy` · `vanilla-js` · `css`

---

# Walkthrough script (3:06)

> **A captioned picture track already exists:** `docs/media/demo-walkthrough.mp4`
> (3:06 including title and end cards, 1440×900, silent with burned-in captions,
> recorded from the deployed demo). Upload it as-is, or lay the narration below
> over it — the beats line up with the times in the table. Rebuild it with
> `python scripts/record_demo.py --out /tmp/demo.webm`, then
> `python scripts/build_video_assets.py` and
> `python scripts/mux_demo_video.py --raw /tmp/demo.webm`.

Screen recording, 1440×900 browser, demo instance running. Speak calmly; do not
narrate the UI, narrate the *guarantee*.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:02 | Title card | "Mitra: delegated work, verified." |
| 0:02–0:13 | Today view, hero + "4 things need you" | "This is Mitra. It runs recurring work for me and it proves what happened. Right now four things need a human decision — and it says so without me asking." |
| 0:13–0:31 | Scroll to needs-you, click **View notice** | "This commitment ran, passed its evidence check, produced a verified artifact — and then delivery failed. Mitra records `delivery_failed`, writes a notice, and keeps the result. Delivery is a separate stage from execution, by design." |
| 0:31–0:46 | Commitments → open *Morning research brief* | "Every commitment is one unit of delegated work: a schedule, a skill, and exactly one instruction version in force." |
| 0:46–1:28 | Runs table, evidence counts, instruction history | "Every run carries evidence. Two checks: the artifact exists, and it has the required sections. Green means both passed. The red row is real — the skill demanded three bullets, the artifact had two, and the gate refused to call it done. And instructions are versions: v3 becomes effective tomorrow. Tomorrow's run picks it up; today's cannot. That is enforced in the scheduler, not in a prompt." |
| 1:28–1:57 | Memory view → reject a proposal | "Chat cannot write memory. Consolidation proposes a change, with the diff and the source message ids. If I reject, the page stays byte-identical. Approving appends one bullet. The model never decides what it remembers." |
| 1:57–2:32 | Chat → new conversation → "Did yesterday's brief actually deliver?" → expand the trace | "Chat reads the real ledger, retrieves the memory pages it used, calls tools through the policy layer, and shows the sources, the trace and the cost of the turn. Note the label: this instance runs the local fallback model because our Token Factory key was rejected — the live path is Nemotron 3 on Nebius." |
| 2:32–2:46 | Audit → filter **denied** | "Every decision is here, including the refused ones. `web_fetch` was denied for a private address; `run_shell` for not being on the allowlist; a memory write because chat is read-only. A security claim you can't audit isn't a security claim." |
| 2:46–3:02 | Stats view | "Cost, reliability, interventions, and calls by model — measured per call, not estimated. This is what 'always-on and trustworthy' has to look like: a ledger you can read, and a system that tells on itself." |
| 3:02–3:06 | End card | — |

## Closing line

"Mitra is MIT licensed, runs as one container, and keeps everything in files you
own. It is a partner that keeps its promises in writing."

## Thumbnail

`docs/media/today.png`, cropped to the hero: "4 things need you." on warm paper,
with the delivery-failure banner visible. No text overlay needed; the type is the
design. The video title card (`.design/video/title.png`) works as a fallback.

## Swapping in a live Nebius key (before the deadline)

The demo instance currently reports `provider: demo`. To run it on Nemotron:

```bash
# on the host that serves the demo
cd mitra
printf 'NEBIUS_API_KEY=%s\n' "$KEY" >> .env
sudo docker compose -p mitra up -d            # recreate with the new env
curl -s localhost:8080/api/health             # expect "provider":"nebius"
.venv/bin/python scripts/smoke_test.py --all   # optional: per-tier latency check
```

The router probes the key at startup. When it authenticates, the sidebar model
card switches from "Local demo model" to "Nemotron · Nebius", replies are
labelled `nemotron` with real per-call cost, and the Stats view starts counting
actual spend. Nothing else changes — same ledger, same gate, same policy. The
synthetic-data banner stays, because the seeded commitments are still synthetic.

## Submission checklist

- [x] Demo live and reachable without a token (Tailscale Funnel, HTTPS)
- [ ] Video uploaded (YouTube/Vimeo, public or unlisted)
- [ ] Repository public, README first screen has a screenshot and the one-command run
- [ ] `docs/FEEDBACK.md` linked in the submission (feedback bonus)
- [ ] Built-with tags include: `nvidia`, `nemotron`, `nebius`, `tavily`, `fastapi`, `sqlite`
- [ ] Nebius key replaced and `provider: nebius` confirmed in `/api/health` before the deadline
