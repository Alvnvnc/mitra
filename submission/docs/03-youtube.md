# The demo video — YouTube upload sheet

The file is `video/mitra-demo.mp4`: **2:56**, 1440×900, silent, H.264, 3.7 MB,
captions burned in. Under the hackathon's 3-minute limit with 4 seconds of margin.

- Captions for YouTube: `video/mitra-demo.srt` (also `.vtt`)
- Video thumbnail: `video/thumbnail-youtube.png` (1280×720)

---

## Title (66 / 100 characters)

```
Mitra — a personal AI that proves its work (NVIDIA Nemotron on Nebius)
```

Alternatives if you want a different emphasis:

```
Mitra: delegated work, verified — NVIDIA Nemotron on Nebius Token Factory
```

```
I built a personal AI whose "done" is a database constraint | Mitra
```

## Description

```
Mitra is a self-hosted personal agent that takes over recurring work and proves
it happened. Its unit of work is the commitment: versioned instructions, runs
gated by deterministic checks, and a delivery state that is never assumed.

Live demo (no signup): https://mitra.pavernor.tech
Code (MIT): https://github.com/Alvnvnc/mitra
Feedback on the platform: https://github.com/Alvnvnc/mitra/blob/main/docs/FEEDBACK.md

Built for the NVIDIA × Nebius Global AI Hackathon, Personal AI track.
Inference runs on NVIDIA Nemotron through Nebius Token Factory:
  · Nemotron 3 Super for chat and tool calling
  · Nemotron 3 Ultra for planning and consolidation
  · Nemotron 3 Nano for extraction on the hot path
Every call is written to a ledger with its model, tokens, latency and cost, which
is what the Stats view is adding up.

What you are watching:
00:00 What Mitra is
00:19 A failure you can see
00:29 Delegated work
00:44 The evidence gate
01:14 Version truth
01:24 Memory waits for you
01:51 Grounded chat, live Nemotron
02:24 The audit log
02:37 Cost, measured

The seeded history is synthetic and labelled in the UI. The ledger, the evidence
gate, the policy engine and the inference are real — the chat turn in this video
is a live Nemotron call carrying its own ledger cost.

Chapters are the sections listed above; the video is silent with burned-in
captions, and an SRT is attached for search and accessibility.
```

## Tags (paste comma-separated)

```
nvidia, nemotron, nebius, token factory, personal ai, ai agent, self-hosted ai, ai assistant, fastapi, sqlite, agentic ai, ai hackathon, devpost, evidence, ai safety
```

## Settings

| Field | Value |
|---|---|
| Visibility | **Public** (the rules require a public YouTube video; unlisted is the fallback only if you must) |
| Audience | Not made for kids |
| Category | Science & Technology |
| Language | English |
| Captions | Upload `video/mitra-demo.srt` as English |
| Thumbnail | `video/thumbnail-youtube.png` |
| Playlist | none |
| Altered content | No — it is a screen recording of the running app |
| Comments | On is fine; off is also fine |

## Upload steps

1. <https://studio.youtube.com> → **Create → Upload videos** → select
   `video/mitra-demo.mp4`.
2. Title and description from above. Do not let YouTube auto-generate the
   description; paste it.
3. **Audience**: not made for kids → **Next**.
4. **Video elements**: upload the SRT under *Subtitles → English → Upload file*.
5. **Checks**: YouTube may flag "silent audio". That is expected — the video is
   captioned by design. Acknowledge it and continue.
6. **Visibility**: Public → **Publish**.
7. After it processes, set the thumbnail and copy the watch URL into
   `01-devpost-fields.md` and into Devpost's video field.

## Why it is silent

Burned-in captions carry the narration, so the video is identical with sound on
or off, works muted in an autoplay gallery, and has nothing to mis-hear. If you
later want a voiced version, the beat sheet in
[`docs/SUBMISSION.md`](../../docs/SUBMISSION.md) is timed to the same cut.
