# Feedback — Nebius Token Factory, NVIDIA Nemotron, Tavily

Written during the NVIDIA × Nebius Global AI Hackathon build (October 2026), and
updated once the live instance got a working Token Factory key.

Two rules for this document: it only contains things we actually observed, and
anything we could not verify is labelled as such. Numbers below come from the
project's own ledger — the same table the Stats view renders — not from memory.

Context: Mitra calls inference through the OpenAI-compatible surface of Nebius
Token Factory (`src/mitra/models/router.py`) and web search through Tavily's
`POST /search` (`src/mitra/tools.py`). The public instance at
<https://mitra.pavernor.tech> runs `provider: nebius`; the seeded history around
it is synthetic and says so in the UI.

---

## What we measured on a live key

40 model calls, one day, one small VM, three Nemotron tiers. Latency is
end-to-end from our process (same region as nothing in particular — a VPS in
Jakarta), and cost is what Token Factory's published rates produce for the token
counts we recorded.

| Model | Purpose | Calls | Latency avg (min–max) | Prompt tok | Completion tok | Cost | Effective $/M tok |
|---|---|---:|---|---:|---:|---:|---:|
| `nvidia/nemotron-3-super-120b-a12b` | chat + tool calling | 19 | 2.79 s (0.69–4.76) | 64,122 | 8,461 | $0.02685 | $0.37 |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | extraction / classify | 11 | 2.79 s (1.01–4.79) | 26,369 | 6,464 | $0.00313 | $0.095 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | planning / synthesis | 10 | 3.02 s (0.63–4.40) | 27,501 | 5,030 | $0.04259 | $1.31 |

All 40 calls returned `finish_reason: "stop"`. A chat turn with two tool rounds
costs about **$0.001–0.004**, which is what makes a public demo with a $0.50
daily ceiling safe to leave open.

Two things stand out. First, **the tier split is doing real work**: an Ultra
planning call costs ~14× a Nano extraction call, and we route accordingly
instead of paying Ultra prices for classification. Second, **latency is
network-floor bound, not model-size bound** — Nano and Super both average
~2.8 s because a short prompt spends most of its wall clock on the round trip,
not on tokens. That is worth knowing before choosing a model for a latency
budget: at this prompt size, the tier barely changes the clock.

## Nebius Token Factory

### What worked well

**OpenAI compatibility is real, not aspirational.** Pointing the official
`openai` Python client at `https://api.tokenfactory.nebius.com/v1/` needed no
shim, no custom auth header, no response translation. Token accounting, tool
calls and usage fields arrived where the client expected them. For a project
that routes by purpose across three models, this is the difference between an
afternoon and a week.

**Model naming is explicit about family and size.** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
tells you the family, the parameter count and that it is MoE. We encoded a
routing table in config and reasoned about it (`fast` / `chat` / `reasoning`)
before benchmarking anything.

**The three-tier shape fits an agent.** Most providers give you one default and
a price list. `fast`, `chat`, `reasoning` with different cost/latency profiles
is what a personal agent actually needs: extraction on every message,
conversation most of the time, planning rarely.

**Costs are consistent enough to budget against.** Our router carries its own
price table (see below); after 40 live calls the ledger's totals line up with
the published rates, which means an operator can set a daily ceiling and trust
it. We run `MITRA_DAILY_BUDGET_USD=0.50` and check it before *every* call,
including scheduled skill runs.

### What cost us time

**A 401 with no diagnosis.** For most of the build our key returned:

```json
{"detail": "Couldn't authenticate. Reason: Unable authenticate"}
```

That message is identical for an expired key, a revoked key, a key from the
wrong project, and a malformed key. We burned time re-checking our own code
before concluding the key itself was dead — we only settled it by calling
`GET /v1/models` directly with `curl` and with `httpx`, against both
`api.tokenfactory.nebius.com` and `api.studio.nebius.ai`. (A second key worked
immediately, so the integration was never the problem.)

*Suggestion:* return a machine-readable code (`key_expired`, `key_revoked`,
`project_mismatch`) and a hint in the body. Even `{"code": "unauthorized.key_invalid"}`
would have saved an hour.

**Two base URLs in circulation.** Documentation and examples variously use
`api.tokenfactory.nebius.com` and `api.studio.nebius.ai`. Both answer `/v1/models`
with the same catalogue, which is friendly, but it leaves you guessing which is
canonical. We default to `api.tokenfactory.nebius.com` and allow an override via
`NEBIUS_BASE_URL`.

*Suggestion:* state one canonical base URL per product surface, and document the
other as an alias.

**No pricing or context metadata in `/v1/models`.** Our Stats view reports real
per-call cost, which means the router has to carry its own price table. If the
models endpoint returned context length and per-token pricing, a router could
configure itself and cost reporting would survive a model rollover without a
code change.

**429s are undocumented in shape.** We rate-limit ourselves so we never hit the
provider's ceiling, so this is an absence of information rather than a
complaint: a documented `Retry-After` contract would let a tool layer back off
instead of guessing.

### What we would like next

- Per-response usage that includes the *billed* amount, not just tokens — it
  removes an entire class of "why does my dashboard disagree with my invoice".
- A documented, stable `finish_reason` contract for tool-call turns. We only
  ever saw `stop`, including turns that carried `tool_calls`; we handle
  `tool_calls`, `stop` and length defensively, but that is guesswork.
- A sandbox/playground key with a hard spend cap. A low-ceiling key that
  survives a judging window lets a submission ship with live inference instead
  of a labelled fallback.
- Streaming through the OpenAI surface: we did **not** test it (the dashboard
  streams its own SSE and calls the model without `stream=True`), so we make no
  claim either way.

---

## NVIDIA Nemotron

**The family fits an agent, not just a chatbot.** Nano being an MoE with a small
active-parameter count is the right shape for "classify this message and extract
two fields". Super handled a four-round tool-calling conversation without
malformed arguments. Ultra wrote the planning prose we use in consolidation.

**Observed behaviour worth reporting to other agent builders** — all three are
things we had to fix in code, and none of them are bugs:

1. **Structural drift between models.** Our evidence gate counts required
   sections in a brief (`Status`, `Selesai`, `Tertunda`, `Prioritas`). The local
   fallback model writes `- Status: …`; Nemotron writes `Status: …` without the
   bullet marker, and the first live run failed the gate for that reason alone.
   Anyone gating output *shape* should normalise before asserting, and should
   make sure a missing section still fails.
2. **A promise is not a tool call.** Twice, a turn ended with "I need to check
   the actual artifact. Let me look up yesterday's morning brief." — prose that
   announces an action, with no `tool_calls` in the response. Treated naively,
   that sentence becomes the final answer. We now detect the pattern, nudge once
   ("call the tool or answer from what you have"), and only then accept the turn.
3. **Prompt tokens dominate the bill in tool loops.** A four-round turn reached
   ~5–7k prompt tokens, each round resending the transcript. We cap tool results
   at 8k characters and cap rounds at 4, which bounds both cost and latency; a
   per-model note on the cost of tool-loop rounds would help builders set that
   cap deliberately.

**What we liked:** deterministic temperature-0.2 planning output, stable JSON in
tool arguments, and the fact that `chat_template_kwargs: {"enable_thinking": false}`
was accepted on every call — we never saw a reasoning block, which keeps chat
latency predictable. We did not benchmark the same prompts with thinking on, so
we make no claim about quality difference.

*Suggestion:* a published "tool-calling conformance" note per model (parallel
calls yes/no, strict JSON schema support, max tools per turn, whether prose-only
turns are common) would let agent builders pick a tier with evidence instead of
trial and error.

---

## Tavily

**The API shape is right for tool use.** One `POST /search`, a flat `results[]`
with `title`, `url`, `content`, and a bounded result count. No pagination
ceremony, no HTML to strip. Wiring it as a governed tool took ~30 lines,
including the risk tier and egress allowlist.

**Limitation of this instance, not of Tavily:** no Tavily key is configured on
the public demo. `web_search` therefore returns a clearly-labelled cached lane
(`search_cache/*.json` in the seeded dataset) instead of pretending to search,
and the Skills view states it. A judge can tell a live search from a fixture at a
glance. That is a design decision on our side — but it is the behaviour we would
recommend to anyone shipping a search tool into a demo.

**What we would like next**

- A `source_type` / credibility hint per result (`peer_reviewed`, `news`,
  `blog`, `vendor`) would let an agent qualify a claim without a second call.
  For a research digest that must separate finding from method from limitation,
  this is the missing field.
- Published rate limits and a documented retry contract (`Retry-After`) so a
  tool layer can back off correctly instead of guessing.
- A free tier that is explicit about monthly credits, so demos can state their
  search budget the way we state inference budget.

---

## Summary

| Surface | Integration verified | Live behaviour verified | Biggest friction |
|---|---|---|---|
| Nebius Token Factory | yes (live, 40 calls) | yes — latency, tokens, cost, per-model routing | Undiagnosable 401, two base URLs, no pricing in `/v1/models` |
| NVIDIA Nemotron | yes (three tiers, tool calling, cost accounting) | yes — chat, planning, four-round tool loops | Structural drift between models; prose-only "I'll check" turns |
| Tavily | yes (tool spec, egress allowlist) | no — no key on this instance, labelled cached lane | Missing per-result credibility metadata |

We would rather publish this table than a paragraph claiming everything worked.
