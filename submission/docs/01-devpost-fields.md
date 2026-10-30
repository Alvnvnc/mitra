# Devpost — field by field

Copy each block as-is. Character counts are real (Devpost truncates the pitch at
200). Everything here matches the live instance and the repository as of the
submission.

---

## Project name

```
Mitra
```

## Elevator pitch (179 / 200 characters)

```
Mitra takes over recurring work and proves it happened: versioned instructions, an evidence gate that blocks "done" without passing checks, and failures that surface on their own.
```

Short variant, if you need room elsewhere (162 / 200):

```
A self-hosted personal agent that runs recurring work and proves it happened: versioned instructions, evidence-gated runs, and failures that surface on their own.
```

## Category / track

```
Personal AI
```

## "Try it out" links

| Label | URL |
|---|---|
| Live demo | `https://mitra.pavernor.tech` |
| Source code | `https://github.com/Alvnvnc/mitra` |
| Feedback write-up | `https://github.com/Alvnvnc/mitra/blob/main/docs/FEEDBACK.md` |

The demo needs no account and no token. It is a seeded synthetic instance with
live inference; the banner on every page says so.

## Video URL

```
<fill in after the YouTube upload — see 03-youtube.md>
```

## Thumbnail

Upload `images/devpost-thumbnail.png` (1440×960, 3:2). It is the real Today view
with the project name underneath, so it still reads at thumbnail size.

## Gallery / media order

Upload in this order; the first image is what judges see first in the gallery.

| # | File | Caption to paste |
|---|---|---|
| 1 | `images/01-today.png` | Today: what needs a decision, what ran, what is broken |
| 2 | `images/02-commitments.png` | Commitments, their schedule and the instruction version in force |
| 3 | `images/03-commitment-detail.png` | Runs, evidence checks, delivery state, instruction history |
| 4 | `images/04-memory.png` | The approval inbox: a memory write is proposed with a diff |
| 5 | `images/05-chat.png` | Live Nemotron chat with sources, tool trace and the cost of the turn |
| 6 | `images/06-audit.png` | Audit: denied tool calls are kept, not dropped |
| 7 | `images/07-stats.png` | Cost and reliability, counted per call from the ledger |
| 8 | `images/08-skills-tools.png` | Skills with their checks; tools with risk tier, gate and egress |
| 9 | `images/09-mobile.png` | The same dashboard on a phone |

## Built with (tags)

Type these into Devpost's "Built with" field, one per entry:

```
python
fastapi
sqlite
pydantic
uvicorn
openai
httpx
nvidia
nemotron
nebius
token-factory
cloudflare-tunnel
docker
vanilla-js
css
tavily
ntfy
```

If Devpost only accepts its suggestion list, the four that matter for the track
are `nvidia`, `nemotron`, `nebius`, `python` — add the rest as free text if the
field allows it.

## "If your project existed before the Submission Period"

Nothing to declare: Mitra was written during the hackathon. If the form asks
anyway, paste:

```
Mitra was built from scratch during the Submission Period; the first commit is
dated 2 October 2026 and the entire history is in the public repository. Nothing
in it predates the hackathon.
```

## Feedback (required by the rules)

Paste this into the feedback field or as the last section of the description:

```
Our notes on Nebius Token Factory, NVIDIA Nemotron and Tavily — measured latency,
token and cost numbers, two model behaviours we had to design around, and what we
would like next — are public at
https://github.com/Alvnvnc/mitra/blob/main/docs/FEEDBACK.md
```

## Extra information (if there is a free-text field)

```
Mitra is MIT licensed and runs as one container:

    docker compose up -d --build

State lives in a named volume; with no NEBIUS_API_KEY the app runs a labelled
deterministic fallback instead of pretending. The submitted instance runs live on
Nebius Token Factory (provider: nebius), with a $0.50 daily spend ceiling, a
per-visitor rate limit and an admin token on destructive actions.
```

## Links to double-check before submitting

- [ ] `https://mitra.pavernor.tech` loads in a private window (no cookie, no token)
- [ ] `/api/health` returns `"provider":"nebius"`
- [ ] `https://github.com/Alvnvnc/mitra` is public and shows "MIT license"
- [ ] README first screen has the screenshot, the demo link and the one-command run
- [ ] The YouTube video is public (or unlisted) and under 3:00
