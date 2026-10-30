# Devpost form — answers, in the order the form asks

Everything below is copy-paste. The ratings are defensible from measurements in
`docs/FEEDBACK.md`, not from vibes; where we could not verify something, the
answer says so.

---

## Code repository

```
https://github.com/Alvnvnc/mitra
```

The four things the form asks for, and where they are:

| Requirement | Where it is satisfied |
|---|---|
| Approved OSI license | MIT, `LICENSE` at the repo root; GitHub shows "MIT license" in the About panel and the README opens with a license badge |
| README with setup instructions | `README.md` → **Run it**: one `docker compose up -d --build`, plus a from-source path and the `.env` keys |
| How NVIDIA Nemotron is used | `README.md` → **Using Nemotron on Nebius Token Factory**: the three-tier table and why Token Factory accelerated the build |
| Other Nebius tools/services | `README.md` → **Nebius services used**: Token Factory yes; AI Cloud GPUs and Serverless Endpoints/Jobs explicitly not used, and why |

## Working demo

```
https://mitra.pavernor.tech
```

No account, no token. Seeded synthetic history (labelled by a banner on every
page), live inference: `/api/health` returns `"provider":"nebius"`.

---

## Which model(s) did you use, and why that size/variant?

```
We used three Nemotron models through Nebius Token Factory, one per purpose,
because Mitra's calls differ by an order of magnitude in cost:

• nvidia/nemotron-3-super-120b-a12b (120B total, 12B active MoE) — chat and tool
  calling. This is the model a person talks to: it has to hold a system prompt,
  read live ledger state, and emit valid tool-call JSON across up to four rounds.
  Super is the smallest tier that did that reliably; measured cost is ~$0.0005 per
  chat turn, ~$0.0015 for a turn with two tool rounds.

• nvidia/Nemotron-3-Ultra-550b-a55b (550B total, 55B active) — planning and
  consolidation, where the call is rare and the reasoning is the product. It costs
  ~14x Super per call (~$0.002), which is fine when it runs once a night.

• nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B (30B total, 3B active) — extraction and
  classification on the hot path, where a call must cost ~$0.0001.

Choosing by purpose rather than by "the biggest model" is what lets a public demo
run under a $0.50/day ceiling. All three were used out of the box, no fine-tuning.
```

## Nemotron output quality for our use case — 8 / 10

```
8/10.

What worked: instruction-following under a long system prompt (it respects
"ground every claim in live state" and refuses to invent runs), tool calling
(valid JSON arguments, four rounds deep, no malformed calls in 19 live chat calls),
grounding (asked which commitment is at risk, it named the delivery failure and
the cause, not the merely-paused one), and multilingual behaviour — it answers in
Indonesian when the user writes Indonesian and English when they write English.

What fell short, both found in production and now handled in code:
1. Structural drift: our evidence gate counts four labelled sections in a brief.
   Nemotron writes "Status: …" where the model we developed against wrote
   "- Status: …", so the first live run failed the gate on a formatting difference,
   not on content. We now normalise shape before asserting, and a missing section
   still fails.
2. Prose instead of a tool call: twice a turn ended with "I need to check the
   artifact. Let me look up yesterday's brief." — an announcement, no tool call.
   Treated naively that sentence becomes the answer. We detect it, nudge once,
   and only then accept the turn.

Both are fixable in the harness, and we did fix them, but an agent builder should
budget for them.
```

## Fine-tune, prompt-engineer, or out of the box?

```
Out of the box, with prompt engineering and code-side constraints. No fine-tuning,
no adapters, no LoRA.

The approach: the system prompt carries hard rules (ground claims in live state,
chat is read-only, "done" needs checked evidence, never reveal secrets, reply in
the user's language). Everything that must be guaranteed is enforced in code
instead of being asked for: an evidence gate that refuses to mark a run done
without passed checks, append-only instruction versions resolved at run time, a
policy engine that checks risk tier and egress before a tool runs, and a ledger
that records model, tokens, latency and cost per call.

Settings: temperature 0.2–0.3, max_tokens 600–1100, and
chat_template_kwargs {"enable_thinking": false} so chat latency stays predictable.
Tool schemas use additionalProperties: false. When the tool-round budget is spent,
the last call runs with no tools and asks for an answer from what was already
retrieved — so a turn ends in an answer, not an apology.
```

## How did Nemotron compare to other models you've used for similar tasks?

```
We ran the same three tasks from Mitra's workload against Nemotron 3 Super and two
other Token Factory models, same prompts, same settings, n=1 per cell — a
directional check, not a benchmark:

| Model | Tool call | 4-section shape | Grounding | Latency | Completion tokens |
|---|---|---|---|---|---|
| Nemotron 3 Super | pass | pass, 54 words | pass | 1.1–1.85 s | 31 / 105 / 54 |
| DeepSeek V4.1 Flash | pass (0.72 s) | pass, 31 words | pass | 0.72–1.71 s | 42 / 442 / 201 |
| Qwen3.5-397B-A17B | pass | pass, 41 words | fail (named the risk, no cause) | 0.99–1.64 s | 16 / 83 / 49 |

Reproduce: `python scripts/compare_models.py`.

What we take from it: all three can call a tool with valid JSON, so tool calling is
no longer a differentiator. Nemotron was the most token-efficient on the structured
brief — 105 completion tokens for 54 words, where DeepSeek spent 442 for 31 — and
it named the at-risk commitment *and* the cause. DeepSeek matched it on all three
tasks and was faster on the tool call; Qwen named the risk but not the cause. No
model was clearly better than Nemotron on Mitra's tasks, which is why the tiering
decision came down to cost and latency rather than quality.

We did not test these models inside the product at runtime — the router makes that
a config change, but the invariants were where the time went.
```

## Which Nebius platform capabilities were most valuable, and how did you use the infrastructure?

```
Token Factory's OpenAI-compatible inference API, used as the single inference path
for the whole product. The official openai Python client points at
https://api.tokenfactory.nebius.com/v1/ with no shim; tool calling, usage
accounting and finish_reason arrive where the client expects them. That is what
made a three-tier router practical in one file — switching between Nano, Super and
Ultra is a model-id string — and it is what makes cost measurable per call instead
of per invoice.

Deployment setup, honestly: inference is managed, so we did not provision a GPU.
The dashboard runs in one Docker container on a small VPS (2 vCPU, 8 GB), published
on loopback and reached through an existing Cloudflare Tunnel; the model calls go
out to Token Factory. Scaling is a deliberate non-goal at this size — the app is
single-process and SQLite-backed, and the interesting scaling lever is the daily
spend ceiling in the router, which is checked before every call.

We did not use Nebius AI Cloud GPU instances, Serverless Endpoints or Serverless
Jobs. For an always-on personal agent, a managed endpoint plus a cheap VM was the
right shape; Serverless Jobs would be the next step for nightly consolidation so
the VM could sleep.
```

## How likely are you to recommend running Nemotron on Nebius? — 9 / 10

```
9/10.

Because the integration cost is near zero and the three-tier catalogue matches what
an agent actually needs: cheap extraction, a capable chat/tool model, and a big
reasoning model for the rare hard call. We went from "key in hand" to "three models
routed by purpose, with per-call cost in a ledger" in an afternoon, and the numbers
we measured (Super ~$0.0005/turn, Ultra ~$0.002/call, 40 calls for $0.07) are what
let us leave a public demo open under a $0.50/day ceiling.

The point we hold back is the 401 we hit for most of the build: a single opaque
"Couldn't authenticate. Reason: Unable authenticate" for an expired key, a revoked
key, a wrong project and a malformed key is an hour of debugging you cannot spend.
```

## Experience running Nemotron inference on Nebius vs previous cloud/local environments — 9 / 10

```
9/10.

Compared with local inference (GPU box, model weights, VRAM planning, cold starts),
this was dramatically simpler: no weights to download, no quantization decisions, no
CUDA/driver matrix, and the model is reachable from any machine. Compared with other
hosted APIs, the difference is the OpenAI-compatible surface plus explicit tiering —
we did not have to re-learn an SDK or guess which "small" model is actually small.

One honest caveat about expectations: latency at our prompt sizes is dominated by
the network round trip, not the model. Nano and Super both averaged ~2.8 s across
live calls because a short prompt spends most of its wall clock on the round trip.
That is not a defect, but it is worth knowing before picking a tier for a latency
budget.
```

## Additional features or improvements that would have helped

```
1. Billed amount in the response usage block, not just tokens — it removes an
   entire class of "why does my dashboard disagree with my invoice".
2. Pricing and context length in /v1/models, so a router can configure itself and
   cost reporting survives a model rollover without a code change.
3. A documented finish_reason contract for tool-call turns. We only ever saw "stop",
   including turns that carried tool_calls.
4. Machine-readable auth errors (key_expired / key_revoked / project_mismatch)
   instead of one opaque "Unable authenticate".
5. A sandbox key with a hard spend cap that survives a judging window, so a
   submission does not have to ship a labelled fallback when a key dies.
```

## What you most hope to see from the Nemotron team next

```
A published tool-calling conformance note per model: parallel calls yes/no, strict
JSON-schema support, max tools per turn, typical behaviour when the model needs a
tool but emits prose instead (we hit this twice). Plus a short note on how each tier
handles output-shape contracts ("reply with exactly these four labelled lines") —
that is the property agent harnesses gate on, and today you discover it by failing
in production. A smaller agent-tuned variant that is explicitly optimised for
multi-round tool loops would also be more useful to us than another general chat
model.
```

## Did you use Tavily in your project?

**No.**

If there is a free-text box, add:

```
No — honest answer. Mitra has a governed web_search tool wired to Tavily
(POST /search, egress allowlisted to api.tavily.com, risk tier low), but no Tavily
key was configured on this instance. Rather than pretend to search, the tool returns
a clearly labelled cached lane ("Tavily is not configured on this instance") and the
Skills view says so. The integration is tested against a stub; no live Tavily call
was made, so we are not claiming the Tavily prize.
```

## Builders & Brews — IRL events city

Leave unselected / "not attending". We did not attend an IRL event, so we are not
eligible for the City Winner Award and should not claim it.

## Eligibility checkboxes

Both must be checked by you, and both are true:

- [x] You and any teammates are at least the age of majority where you reside
- [x] You and any teammates are not employees, representatives or agents of the
      Promotion Entities

## Which AI tools have you leveraged while working on this project?

```
A terminal coding agent (OpenCode) whose models were themselves served through
Nebius Token Factory, used for scaffolding, refactors and test authoring — and
NVIDIA Nemotron inside the product, for chat, tool calling, planning and
extraction. Every product decision, the three invariants, the policy engine and
the review of each diff were done by hand; the agent wrote code we then had to
test, and 68 tests are what kept it honest.
```

*(Adjust if you also used ChatGPT, Copilot, Cursor, etc. — list what is true.)*

## Level of learning derived from the project

Pick the highest honest option (likely "Significant" / "A lot"). Text if the form
offers one:

```
High. We started with "an agent is a loop with tools" and ended with a system where
completion is a database transition, instructions are append-only rows resolved at
run time, and every tool call is authorised and audited. The specific things we had
to learn by building: how to make "done" mean something without trusting the model,
how to keep a public demo with a real API key from being drainable, what actually
happens to a prompt when a model needs a tool but writes a sentence instead, and why
cost accounting has to be per call if you want to promise a budget.
```

## Did you gain AI value you can use in your career?

```
Yes. Two things transfer directly: (1) the pattern of putting guarantees in code
and constraints rather than prompts — evidence gates, append-only versions,
policy-checked tools — which applies to any agent product, and (2) the operational
side of running a keyed LLM app in public: rate limits keyed on the real client,
a hard spend ceiling checked on every call, an admin gate on destructive endpoints,
and a fallback that announces itself instead of faking success.
```

---

## Ratings at a glance

| Question | Answer |
|---|---|
| Nemotron output quality (1–10) | **8** |
| Recommend Nemotron on Nebius (1–10) | **9** |
| Experience vs previous cloud/local (1–10) | **9** |
| Used Tavily | **No** (no key; labelled cached lane, integration tested against a stub) |
| Built with NVIDIA model | **yes** — three Nemotron tiers, live |
| Nebius services | **Token Factory only** (no GPU instances, no Serverless) |
