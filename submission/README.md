# Devpost submission package — Mitra

Everything a judge will see, prepared so submitting is copy, paste and upload.
Nothing here needs editing except the YouTube URL once the video is up.

| | |
|---|---|
| **Project** | Mitra — a private, always-on personal AI that keeps its promises in writing |
| **Track** | Personal AI |
| **Live demo** | <https://mitra.pavernor.tech> |
| **Repository** | <https://github.com/Alvnvnc/mitra> (MIT) |
| **Video** | 2:56, silent with burned-in captions, `video/mitra-demo.mp4` |

## Read in this order

1. **[docs/04-checklist.md](docs/04-checklist.md)** — the runbook, with the
   pre-flight commands and the deadline in WIB.
2. **[docs/03-youtube.md](docs/03-youtube.md)** — upload the video, then copy its
   URL.
3. **[docs/01-devpost-fields.md](docs/01-devpost-fields.md)** — every form field,
   character counts included.
4. **[docs/02-about-the-project.md](docs/02-about-the-project.md)** — the long
   story to paste, with markers for where each image goes.
5. **[docs/05-devpost-form-answers.md](docs/05-devpost-form-answers.md)** — the
   survey fields: model choice, ratings with justification, Tavily answer, AI
   tools, and the repo/demo compliance mapping.

## What is in the folder

```
submission/
├── docs/
│   ├── 01-devpost-fields.md        name, pitch (179 chars), links, tags, media order
│   ├── 02-about-the-project.md     the story: why, what, how, Nemotron, lessons
│   ├── 03-youtube.md               title, description, chapters, settings
│   ├── 04-checklist.md             runbook + verification commands
│   └── 05-devpost-form-answers.md  survey answers: models, ratings, Tavily, AI tools
├── images/
│   ├── devpost-thumbnail.png       1440×960 (3:2), real Today view + wordmark
│   ├── 01-today.png                gallery, in display order
│   ├── 02-commitments.png
│   ├── 03-commitment-detail.png
│   ├── 04-memory.png
│   ├── 05-chat.png
│   ├── 06-audit.png
│   ├── 07-stats.png
│   ├── 08-skills-tools.png
│   ├── 09-mobile.png
│   └── 10-mobile-chat.png
└── video/
    ├── mitra-demo.mp4              2:56 · 1440×900 · H.264 · 3.7 MB · silent
    ├── mitra-demo.srt              burned-in captions, retimed to this cut
    ├── mitra-demo.vtt
    └── thumbnail-youtube.png       1280×720
```

## How the media was made

No mockups: every screenshot is a capture of <https://mitra.pavernor.tech> at
1440×1000 @2x, taken with `scripts/capture_screens.py`. The video is a Playwright
screen recording of the same instance (`scripts/record_demo.py`), with title card,
caption strips and end card rendered from the dashboard's own self-hosted fonts
(`scripts/build_video_assets.py`) and muxed with ffmpeg
(`scripts/mux_demo_video.py`). The thumbnail is HTML rendered over the real
screenshot (`scripts/build_submission_assets.py`), so the type matches the product.

Regenerate any of it:

```bash
.venv/bin/python scripts/capture_screens.py --base https://mitra.pavernor.tech
.venv/bin/python scripts/build_submission_assets.py --base https://mitra.pavernor.tech
```

## Not included (you have to do these)

- The YouTube upload — it needs your Google account, and the rules require a
  **public** YouTube video.
- The Devpost submission form — it needs your Devpost login.
- Anything that requires accepting the Official Rules.

## Honesty notes a judge may check

- The seeded history (commitments, runs, costs, the persona "Maya Rahman") is
  synthetic, and the dashboard says so in a banner on every page.
- Inference is live: `/api/health` reports `"provider":"nebius"`, and chat turns
  are labelled `nemotron` with their ledger cost.
- No Tavily key is configured on the public demo, so `web_search` returns a
  clearly labelled cached lane instead of pretending to search. The Skills view
  states this.
- The public instance is rate-limited and spend-capped on purpose; a judge may
  see a `429` after ~6 chat turns in an hour. The message explains it and the
  rest of the dashboard keeps working.
