# Mitra — delegated work, verified

A private, always-on personal AI that keeps its promises in writing.

**Live demo:** https://mitra.pavernor.tech · **Code (MIT):** https://github.com/Alvnvnc/mitra · **Track:** Personal AI

---

## Inspiration

Every "personal AI" demo ends the same way: an impressive conversation, then you close the tab and nothing persists. Ask it to take over something recurring — a weekly literature scan, a follow-up on a dataset request — and you inherit three new chores.

You re-explain the task every time the instructions change. You cannot tell whether "done" means done or means *the model said so*. And when delivery breaks, you find out days later, if at all.

We wanted the opposite: an agent whose memory is a file you can read, whose "done" is a database constraint, and whose failures find you. That is Mitra — Indonesian for *partner*, not *servant*.

## What it does

Mitra is a self-hosted personal agent with a dashboard, a scheduler, persistent memory and governed tools. Its unit of work is the **commitment**: a recurring piece of delegated work with versioned instructions, evidence-gated runs, and a delivery state that is never assumed.

Three invariants are enforced in code, not in a prompt:

1. **Only the currently approved instruction runs.** Instructions are append-only versions with an `effective_from`. The scheduler resolves the version effective at *run* time, so a change dated "tomorrow" cannot leak into today's run.
2. **"Done" requires evidence that passed.** A run cannot reach `done` unless every evidence item has a passed check from the skill's deterministic `verify()`. The model writes prose; the code owns the rules.
3. **Failures surface without being asked.** Delivery is a separate stage from execution. A delivery failure becomes `delivery_failed`, writes a `NOTICE` to the outbox, and raises a banner in the dashboard — never a silent gap.

Around those invariants: an **approval inbox** for memory writes, a **policy engine** that governs every tool call, **cost-aware routing** across three NVIDIA Nemotron tiers with per-call accounting, and seven dashboard views that show the ledger exactly as it is.

## How we built it

The spine is a **FastAPI + SQLite ledger**. Commitments, instruction versions, runs, evidence, delivery receipts, sessions, proposals, approvals, audit entries and model calls all live in one database, with the three invariants expressed as constraints and guarded transitions — `complete_run()` raises if any evidence is unpassed.

The **runner** executes one run as a short, inspectable pipeline: resolve the instruction → run the skill → record evidence → deterministic check → complete or fail → deliver as a separate stage → write a notice on failure.

**Skills** are plain units with `execute()` and `verify()`: `daily_digest`, `morning_brief`, `commitment_followup`, `research_digest`. A skill writes an artifact; the check decides whether that artifact is acceptable.

**Tools** are the only door to the outside world: `web_search` (Tavily), `memory_search`, `commitment_status`, `artifact_read` (the brief a run actually wrote), `note_write` and `notify_send` (approval required). Every spec declares its risk tier and egress hosts, and the policy engine checks allowlist, risk, approval state and destination host before a byte leaves the process. Denials are audited, not dropped.

The **agent** is a tool-calling chat loop with retrieval from the self-model and the ledger, a tool-round budget, and a per-turn trace the UI renders — sources, tools, tokens, dollars. If it spends its tool rounds, the last call runs with no tools and asks for an answer from what was already retrieved, so a turn ends in an answer rather than an apology.

The **dashboard** is vanilla ES modules and hand-written CSS with self-hosted fonts. No build step, so the whole product is one `docker compose up`.

## How we used NVIDIA Nemotron and Nebius Token Factory

Inference is the only thing Mitra does not run itself. Every model call goes through one router to Token Factory's OpenAI-compatible endpoint, and the router records model, purpose, tokens, latency and cost into the ledger on the way back.

* **`nvidia/nemotron-3-super-120b-a12b`** (120B total, 12B active) — chat and tool calling. The smallest tier that reliably held a long system prompt, live ledger state and valid tool-call JSON across four rounds. About **$0.0005** per turn.
* **`nvidia/Nemotron-3-Ultra-550b-a55b`** (550B, 55B active) — planning and consolidation, where the call is rare and reasoning is the product. About **$0.002** a call, once a night.
* **`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`** (30B, 3B active) — extraction and classification on the hot path, about **$0.0001** a call.

Routing by purpose instead of "the biggest model" is what lets a public demo run under a hard ceiling of **$0.50/day**, checked before every call including scheduled skill runs. In one day of live use the ledger recorded **40 calls for $0.07** — a measurement, not an estimate, because the same rows feed the Stats view.

Token Factory removed the integration risk entirely: the official `openai` client pointed at `https://api.tokenfactory.nebius.com/v1/` worked unmodified, and switching between the three tiers is a model-id string. We used no other Nebius service — no GPU instances, no Serverless Endpoints or Jobs — because inference is managed and the dashboard runs in one container on a small VPS.

## Challenges we ran into

**The hard part was not the model — it was making "done" mean something.** Early versions let the model's prose decide completion. The fix was structural: evidence items are rows, checks are deterministic functions, and `complete_run()` refuses to transition unless every check passed. The first live run then failed the gate for a reason we did not expect: Nemotron writes `Status: …` where the model we developed against wrote `- Status: …`. The gate was right and the formatting was wrong, so we now normalise shape before asserting — while making sure a genuinely missing section still fails.

**Version truth.** "Use my new instructions starting tomorrow" is easy to say and easy to get wrong. Instructions became append-only rows with `effective_from`, and the scheduler resolves the version against the *run* timestamp, not the current wall clock.

**A promise is not a tool call.** Twice, a live turn ended with "I need to check the artifact. Let me look up yesterday's brief." — prose that announces an action, with no tool call in the response. Treated naively, that sentence becomes the answer. We now detect the pattern, nudge once, and record the nudge in the trace.

**Inference that says what it is.** Our first Token Factory key returned `401` for most of the build. Rather than fake it, the router was written to fail visibly: it probes the key at startup, flips to a deterministic local composer that reads the real ledger, and labels every surface "Local demo model". That path is still tested and still in the image — a degraded demo, never a lying one.

**Keeping a keyed public demo safe.** A judged demo has to be clickable by strangers, and a clickable demo holds a real API key. The port is bound to loopback and reached only through a Cloudflare Tunnel, so the client address cannot be spoofed; chat is metered per visitor with a global daily ceiling, and the spend cap is checked on every call. Destructive actions need an admin token, and a test walks the API asserting the key never appears in a response.

## Accomplishments we're proud of

* Three invariants that hold under tests, not just under demo conditions — **68 tests**, including "a change effective tomorrow does not apply today", "completion without evidence raises", and "a delivery failure leaves the verified artifact intact".
* An approval inbox that shows the diff before writing memory — and a rejection path that leaves the page byte-identical.
* Cost accounting measured per call, so the Stats view can be trusted: when it says $0.07 across 40 calls, that is the ledger, not an estimate.
* A dashboard that tells on itself: the demo deliberately includes a failed run and a delivery failure, because invariant 3 is only believable if you can see it.
* One command to run: `docker compose up -d --build`, non-root container, seeded demo, healthcheck.
* A demo that is honest about what is synthetic: the seeded history carries a banner on every page, and each chat turn is labelled with the model that actually answered.

## What we learned

* **Constraints beat prompts.** Every guarantee that mattered became a database invariant or a deterministic check. Prompts describe; constraints enforce.
* **Failure is a feature.** Making delivery a separate stage doubled the honest surface area of the product and made the demo more convincing.
* **A fallback must be louder than the model.** When inference is unavailable, the UI has to say so everywhere, not in a footnote.
* **OpenAI-compatible APIs remove integration risk.** Swapping the base URL was the whole Nebius integration.
* **Latency is not a model-size problem.** At our prompt sizes Nano and Super both averaged ~2.8 seconds live, because a short prompt spends most of its wall clock on the round trip — worth knowing before choosing a tier for a latency budget.

## What's next

* Embedding-backed retrieval over the ledger (today it is lexical, and says so).
* A conformance suite that runs the same tool-calling prompts against all three Nemotron tiers and records where they differ.
* Multi-user households with per-person memory namespaces.
* Nebius Serverless Jobs for consolidation, so the VM can sleep between runs.

## Try it out

https://mitra.pavernor.tech — no signup, no token. The seeded history is synthetic and the banner says so; the ledger, evidence gate, policy engine and inference are real. Screenshots of every view are in the project gallery and in the repository README.

1. **Today** — what needs a decision right now. There is a deliberate delivery failure to look at: a run that passed its evidence check, produced a verified artifact, and then failed to deliver.
2. **Commitments → Morning research brief** — the run history, the evidence checks, and version 3 of the instruction that becomes effective tomorrow.
3. **Memory** — approve or reject a proposed memory write; the diff is shown before anything changes.
4. **Chat** — ask "Did yesterday's brief actually deliver?" and open the trace: sources, tool calls, model id, and the cost of that turn.
5. **Audit** — filter to `denied`. The refused tool calls are kept on purpose; a security claim you cannot audit is not a security claim.
6. **Stats** — cost and reliability, counted per call from the ledger.

## Feedback on the platform

Our notes on Token Factory, NVIDIA Nemotron and Tavily — measured latency, token and cost numbers, two model behaviours we had to design around, and what we would like next — are public at https://github.com/Alvnvnc/mitra/blob/main/docs/FEEDBACK.md

## Built with

`python` · `fastapi` · `sqlite` · `pydantic` · `uvicorn` · `openai` · `httpx` · `nvidia` · `nemotron-3-super` · `nemotron-3-ultra` · `nemotron-3-nano` · `nebius-token-factory` · `cloudflare-tunnel` · `docker` · `vanilla-js` · `css` · `tavily` · `ntfy`
