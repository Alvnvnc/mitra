# Mitra

**An always-on, private personal AI with persistent memory, reusable skills, and governed tool access — you own the whole stack.**

Built for the [NVIDIA x Nebius Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/) · **Personal AI Track** · submission deadline Oct 30, 2026.

> Working title: *Mitra* (Indonesian for "partner"). Under active development — see [docs/PLAN.md](docs/PLAN.md) for the build plan and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## What it is

Most "personal AI" is a chat window with a system prompt and amnesia. Mitra is the opposite:

- 🧠 **Memory that persists and grows** — an episodic ledger (SQLite) plus a human-readable *self-model* (Markdown you can read and edit), consolidated nightly, with an approval inbox before memory changes are applied.
- 🛠 **Reusable skills** — declarative skill manifests and playbooks; the assistant can propose new skills learned from your workflows.
- ⚖️ **Budget-aware model routing** — [NVIDIA Nemotron](https://developer.nvidia.com/topics/ai/Nemotron) via **Nebius Token Factory**: Nano for high-volume extraction, Super for everyday chat + tool calling, Ultra for hard planning. Live cost/latency stats in the dashboard.
- 🔐 **Governed tools, private data** — explicit tool/egress allowlists, approval prompts for risky actions, secrets never placed in prompts, full audit log. Your data stays in plain files on a VM you control (Nebius AI Cloud).
- 💬 **Where you live** — Telegram bot + web dashboard (chat, memory inspector, skills, audit, stats).
- 🔎 **Live web research** — [Tavily](https://tavily.com) as a runtime tool inside skills.

## How it works (short version)

```
Telegram  /  Web dashboard
        │
   interfaces (FastAPI)
        │
   agent core ── skill registry ── tool registry (policy + audit)
        │                │
   memory layers      Tavily / notes / scheduler
   (ledger + self-model + embeddings)
        │
   model router → Nebius Token Factory ── Nemotron Nano / Super / Ultra
```

Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quickstart (dev)

Prerequisites: Python 3.11+, a Nebius Token Factory API key ([setup guide](docs/SETUP_NEBIUS.md)).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # then set NEBIUS_API_KEY (and optionally TAVILY_API_KEY)

python scripts/smoke_test.py --all   # verifies Nemotron connectivity + latency
pytest -q                            # unit tests
```

The web app and Telegram bot land in week 3 of the plan — watch [docs/PLAN.md](docs/PLAN.md).

## Repository layout

```
docs/       problem statement, community research, architecture, plan, Nebius setup
scripts/    smoke_test.py (Token Factory connectivity check)
src/mitra/  config, model router, (growing) memory / agent / interfaces
tests/      unit tests
```

## Hackathon notes

- **NVIDIA open models used:** Nemotron 3 Nano 30B, Nemotron 3 Super 120B, Nemotron 3 Ultra 550B (and optionally Nemotron 3.5 Lightning) — served on **Nebius Token Factory** (OpenAI-compatible API).
- **Nebius services used:** Token Factory (inference) + Nebius AI Cloud (always-on VM hosting; optionally Serverless Jobs for the nightly consolidation).
- **Tavily:** runtime web search tool (Best Use of Tavily bonus).
- Feedback on Nebius & NVIDIA tooling: [docs/FEEDBACK.md](docs/FEEDBACK.md) *(coming in week 4)*.

## License

MIT — see [LICENSE](LICENSE).