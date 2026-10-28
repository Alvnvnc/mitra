# Feedback — Nebius Token Factory, NVIDIA Nemotron, Tavily

Written during the NVIDIA × Nebius Global AI Hackathon build (October 2026).
Two rules for this document: it only contains things we actually observed, and
anything we could not verify is labelled as such.

Context: Mitra calls inference through the OpenAI-compatible surface of Nebius
Token Factory (`src/mitra/models/router.py`) and web search through Tavily's
`POST /search` (`src/mitra/tools.py`). The key available during the build
returned `401`, so the *integration* is verified by tests with a stubbed
transport, while live latency and output quality are **not** claimed anywhere.

---

## Nebius Token Factory

### What worked well

**OpenAI compatibility is real, not aspirational.** Pointing the official
`openai` Python client at `https://api.tokenfactory.nebius.com/v1/` needed no
shim, no custom auth header, no response translation. For a project that routes
by purpose across three models, this is the difference between an afternoon and
a week.

**Model naming is explicit about family and size.** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
tells you the family, the parameter count and that it is MoE. We could encode a
routing table in config and reason about it (`fast` / `chat` / `reasoning`)
without benchmarking first.

**Separation of `fast`, `chat`, `reasoning` is a good product shape.** Most
providers give you one default and a price list. Having three sensible tiers
with different cost/latency profiles is what a personal agent actually needs:
extraction on every message, conversation most of the time, planning rarely.

### What cost us time

**A 401 with no diagnosis.** The response body is:

```json
{"detail": "Couldn't authenticate. Reason: Unable authenticate"}
```

That message is identical for an expired key, a revoked key, a key from the
wrong project, and a malformed key. We burned time re-checking our own code
before concluding the key itself was dead — we only settled it by calling
`GET /v1/models` directly with `curl` and with `httpx`, against both
`api.tokenfactory.nebius.com` and `api.studio.nebius.ai`.

*Suggestion:* return a machine-readable code (`key_expired`, `key_revoked`,
`project_mismatch`) and a hint in the body. Even `{"code": "unauthorized.key_invalid"}`
would have saved an hour.

**Two base URLs in circulation.** Documentation and examples variously use
`api.tokenfactory.nebius.com` and `api.studio.nebius.ai`. Both accepted our
request shape and both returned 401, so we could not determine which is
canonical for Token Factory today. We default to `api.tokenfactory.nebius.com`
in config and allow override via `NEBIUS_BASE_URL`.

*Suggestion:* state one canonical base URL per product surface, and make the
other a 301 (or document it as a legacy alias).

**No pricing or context metadata in `/v1/models`.** Our Stats view reports real
per-call cost, which means the router has to carry its own price table. If the
models endpoint returned context length and per-token pricing, a router could
configure itself and cost reporting would survive a model rollover without a
code change.

### What we would like next

- Per-response usage that includes the *billed* amount, not just tokens — it
  removes an entire class of "why does my dashboard disagree with my invoice".
- A documented, stable `finish_reason` contract for tool-call turns; we handle
  `tool_calls`, `stop` and length defensively, but that is guesswork.
- A sandbox/playground key with a hard spend cap. Hackathon keys die; a
  low-ceiling key that survives the judging window would have let this
  submission ship with live inference.

---

## NVIDIA Nemotron

**The family fits an agent, not just a chatbot.** Nano being an MoE with a small
active-parameter count is exactly the right shape for "classify this message and
extract two fields", which is the highest-volume call in Mitra. Super handles
conversation plus tool calls; Ultra is reserved for planning and consolidation
where latency is acceptable.

**Honest limitation:** because the key was dead, we cannot report on Nemotron's
tool-calling reliability, instruction-following under our system prompt, or
latency. We deliberately did not write marketing claims about model quality
anywhere in this repository. The code paths are exercised against a stub, and
the deterministic local composer exists precisely so the demo does not pretend.

*Suggestion:* a published "tool-calling conformance" note per model (parallel
calls yes/no, strict JSON schema support, max tools per turn) would let agent
builders pick a tier with evidence instead of trial and error.

---

## Tavily

**The API shape is right for tool use.** One `POST /search`, a flat `results[]`
with `title`, `url`, `content`, and a bounded result count. No pagination
ceremony, no HTML to strip. Wiring it as a governed tool took ~30 lines,
including the risk tier and egress allowlist.

**What we did with no key:** `web_search` returns a clearly-labelled cached lane
(`search_cache/*.json` in the demo dataset) instead of pretending to search, and
the Skills view states "No Tavily key on this instance. The tool returns a
clearly labelled cached demo lane rather than pretending to search." A judge can
therefore tell the difference between a live search and a fixture at a glance.
That is a design decision on our side, not a Tavily limitation — but it is the
behaviour we would recommend to anyone shipping a search tool into a demo.

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
| Nebius Token Factory | yes (stub + direct HTTP probes) | no — key returned 401 | Undiagnosable 401, two base URLs |
| NVIDIA Nemotron | yes (routing, cost accounting) | no — same key issue | No published tool-calling conformance |
| Tavily | yes (tool spec, egress allowlist) | no — no key on this instance | Missing per-result credibility metadata |

We would rather publish this table than a paragraph claiming everything worked.
