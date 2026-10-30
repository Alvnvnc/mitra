# Submission checklist

Work top to bottom. Roughly 35 minutes, most of it waiting for YouTube to process.

**Deadline:** 30 October 2026, 10:00 PDT — that is **31 October 2026, 00:00 WIB**
(UTC+7). Submit with time to spare; Devpost does not accept late drafts.

---

## 0. Pre-flight (2 minutes)

Run these before touching Devpost. If any line is wrong, fix it first.

```bash
# the demo answers, with live inference
curl -s https://mitra.pavernor.tech/api/health
# {"ok":true,"version":"0.1.0","provider":"nebius","uptime_s":…}

# destructive actions are gated for strangers
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://mitra.pavernor.tech/api/demo/reset -H 'content-type: application/json' -d '{}'
# 403

# the shell carries a cache-busted bundle (no stale CDN copy)
curl -s https://mitra.pavernor.tech/ | grep -o 'app.js?v=[0-9-]*'

# the repository is public and the license is detected
gh repo view Alvnvnc/mitra --json isPrivate,licenseInfo,homepageUrl
```

- [ ] `/api/health` reports `"provider":"nebius"`
- [ ] `POST /api/demo/reset` without the admin token returns `403`
- [ ] `gh repo view` shows `"isPrivate": false`, `"key": "mit"`, homepage set
- [ ] `https://mitra.pavernor.tech` opens in a **private window** with no prompt
- [ ] The nightly reseed is installed: `ssh vps-alvn 'crontab -l'` → `17 3 * * * …/reseed.sh`

## 1. Upload the video (10 minutes, mostly processing)

Follow [`03-youtube.md`](03-youtube.md).

- [ ] `video/mitra-demo.mp4` uploaded — 2:56, under the 3-minute limit
- [ ] Title, description and tags pasted (not auto-generated)
- [ ] `video/mitra-demo.srt` uploaded as English captions
- [ ] Thumbnail set to `video/thumbnail-youtube.png`
- [ ] Visibility **Public**, audience "not made for kids"
- [ ] Watch URL copied

## 2. Create the Devpost project (2 minutes)

- [ ] <https://devpost.com/software/new> (or the hackathon's **Submit project** button)
- [ ] Name: `Mitra`
- [ ] Tagline / elevator pitch: the 179-character line from
      [`01-devpost-fields.md`](01-devpost-fields.md)
- [ ] Thumbnail: `images/devpost-thumbnail.png`
- [ ] Track: **Personal AI**

## 3. Fill the story (10 minutes)

- [ ] Paste [`02-about-the-project.md`](02-about-the-project.md) into **About the project**
- [ ] Upload the nine gallery images in the order listed in
      [`01-devpost-fields.md`](01-devpost-fields.md), each with its caption
- [ ] Add the video URL from step 1
- [ ] Add "Try it out" links: demo, repository, feedback write-up
- [ ] Add the **Built with** tags
- [ ] Paste the feedback paragraph (the rules ask for feedback explicitly)
- [ ] Fill the survey fields from [`05-devpost-form-answers.md`](05-devpost-form-answers.md):
      models and why, quality 8/10, recommend 9/10, experience 9/10, Tavily **No**,
      AI tools, learning level
- [ ] If asked about pre-existing work: use the "nothing to declare" block

## 4. Final read-through (5 minutes)

Open the preview and read it as a judge who has 60 seconds.

- [ ] First screen: name, one-sentence promise, a screenshot, the live demo link
- [ ] No broken image placeholders, no `TODO`, no local file paths
- [ ] Every claim is true — in particular: seeded history is labelled synthetic,
      and the demo really is running `provider: nebius`
- [ ] The video plays inline and is public
- [ ] Spell-check: *Mitra*, *Nemotron*, *Token Factory*, *Nebius*, *Devpost*

## 5. Submit (1 minute)

- [ ] Click **Submit project**
- [ ] Confirm the project page is public (open it in a private window)
- [ ] Screenshot the confirmation page and keep it
- [ ] Post the submission link wherever you want it seen

## 6. Keep it alive for judging

- [ ] Leave the container running: `ssh vps-alvn 'docker compose -p mitra ps'`
- [ ] The spend ceiling is `$0.50/day`; a judge's chat turn costs ~$0.001–0.004
- [ ] If the key ever dies, the UI flips to "Local demo model" and says why —
      the site stays up, so a dead key is a degraded demo, not a 502
- [ ] Watch `ssh vps-alvn 'tail -5 ~/mitra/reseed.log'` the morning after

---

## Files in this package

```
submission/
├── README.md                     ← index
├── docs/
│   ├── 01-devpost-fields.md      ← copy-paste per field, char counts
│   ├── 02-about-the-project.md   ← the long description, with image markers
│   ├── 03-youtube.md             ← title, description, chapters, settings
│   └── 04-checklist.md           ← this file
├── images/
│   ├── devpost-thumbnail.png     ← 1440×960, 3:2
│   ├── 01-today.png … 09-mobile.png
└── video/
    ├── mitra-demo.mp4            ← 2:56, silent, captioned
    ├── mitra-demo.srt / .vtt     ← captions for YouTube
    └── thumbnail-youtube.png     ← 1280×720
```
