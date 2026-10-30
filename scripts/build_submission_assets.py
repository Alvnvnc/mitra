"""Render the Devpost submission media from the live dashboard screenshots.

Everything here is derived from real captures of the running instance, plus two
designed cards that reuse the dashboard's own self-hosted fonts, so the media
looks like the product instead of like a slide deck.

Outputs, all under ``submission/``:

* ``images/0N-*.png``               gallery, 1600x1000, ordered for Devpost
* ``images/devpost-thumbnail.png``  3:2 (1440x960) project thumbnail
* ``video/thumbnail-youtube.png``   1280x720 video thumbnail

Run after ``scripts/capture_screens.py``:

    python scripts/build_submission_assets.py --base https://mitra.pavernor.tech
"""

from __future__ import annotations

import argparse
import base64
import pathlib
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
OUT = ROOT / "submission" / "images"
CHROME = str(pathlib.Path.home() / ".local" / "bin" / "google-chrome")

# (source screenshot, output name, what the image is for)
GALLERY = [
    ("today.png", "01-today.png", "Today: what needs a decision"),
    ("commitments.png", "02-commitments.png", "Commitments and the instruction in force"),
    ("commitment-detail.png", "03-commitment-detail.png", "Runs, evidence, delivery, versions"),
    ("memory.png", "04-memory.png", "Approval inbox with a diff"),
    ("chat-reply.png", "05-chat.png", "Live Nemotron chat with sources, trace and cost"),
    ("audit.png", "06-audit.png", "Audit log, denials included"),
    ("stats.png", "07-stats.png", "Measured cost and reliability"),
    ("skills.png", "08-skills-tools.png", "Skills and governed tools"),
]

GALLERY_SIZE = (1600, 1000)


def crop_for_gallery(path: Path) -> Image.Image:
    """Screenshots are 2880x2000; 1600x1000 is 16:10, so trim the bottom edge."""
    with Image.open(path) as image:
        width, height = image.size
        target = GALLERY_SIZE[0] / GALLERY_SIZE[1]
        if width / height > target:
            new_width = int(height * target)
            left = (width - new_width) // 2
            image = image.crop((left, 0, left + new_width, height))
        else:
            new_height = int(width / target)
            image = image.crop((0, 0, width, new_height))
        return image.convert("RGB").resize(GALLERY_SIZE, Image.LANCZOS)


THUMB_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/fonts/fonts-local.css">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; width: 1440px; height: 960px; }
  body { position: relative; background: #faf9f5; font-family: "Inter Tight", system-ui, sans-serif;
         color: #16150f; overflow: hidden; }
  .top { position: relative; height: 448px; overflow: hidden; }
  .shot { display: block; width: 1440px; height: auto; }
  .fade { position: absolute; left: 0; right: 0; bottom: 0; height: 96px;
          background: linear-gradient(180deg, rgba(250,249,245,0) 0%, #faf9f5 92%); }
  .edge { position: absolute; left: 60px; right: 60px; bottom: 0; height: 1px; background: #e4dfd2; }
  .band { position: absolute; left: 60px; right: 60px; bottom: 44px;
          display: flex; align-items: flex-end; justify-content: space-between; gap: 40px; }
  .mark { color: #1c5a41; width: 32px; height: 32px; margin-bottom: 12px; }
  h1 { font-family: "Fraunces", Georgia, serif; font-size: 60px; line-height: 0.98;
       font-weight: 600; letter-spacing: -0.035em; margin: 0; }
  h1 em { font-style: italic; color: #1c5a41; }
  .sub { margin-top: 18px; font-size: 19px; line-height: 1.5; color: #4a463b; max-width: 720px; }
  .right { text-align: right; padding-bottom: 6px; }
  .kicker { font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: 0.18em;
            text-transform: uppercase; color: #6d685b; margin-bottom: 12px; }
  .tags { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
  .tag { font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: 0.06em;
         text-transform: uppercase; color: #3f3d34; border: 1px solid #ddd8c9; border-radius: 999px;
         padding: 6px 11px; background: #fff; white-space: nowrap; }
  .tag.solid { background: #16150f; border-color: #16150f; color: #faf9f5; }
</style></head><body>
  <div class="top">
    <img class="shot" src="__SHOT__" alt="">
    <div class="fade"></div>
    <div class="edge"></div>
  </div>
  <div class="band">
    <div>
      <svg class="mark" viewBox="0 0 32 32"><path d="M16 3.5 28.5 16 16 28.5 3.5 16z" fill="none"
        stroke="currentColor" stroke-width="1.4"/><circle cx="16" cy="16" r="4.2" fill="currentColor"/></svg>
      <h1>Mitra.<br><em>Delegated work, verified.</em></h1>
      <p class="sub">Runs are gated by deterministic checks. Memory waits for your
        approval. A failed delivery surfaces on its own — with the artifact kept.</p>
    </div>
    <div class="right">
      <div class="kicker">NVIDIA \u00d7 Nebius · Personal AI</div>
      <div class="tags">
        <span class="tag solid">Live demo</span>
        <span class="tag">Nemotron · Token Factory</span>
      </div>
    </div>
  </div>
</body></html>
"""

YT_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/fonts/fonts-local.css">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; width: 1280px; height: 720px; }
  body { background: #faf9f5; font-family: "Inter Tight", system-ui, sans-serif; color: #16150f;
         display: grid; place-items: center; overflow: hidden;
         background-image: radial-gradient(circle at 14% 18%, #efece1 0, transparent 55%),
                           radial-gradient(circle at 86% 82%, #e6eee5 0, transparent 52%); }
  .card { width: 100%; padding: 0 84px; }
  .mark { color: #1c5a41; width: 46px; height: 46px; margin-bottom: 22px; }
  h1 { font-family: "Fraunces", Georgia, serif; font-size: 96px; line-height: 0.9;
       font-weight: 600; letter-spacing: -0.04em; margin: 0 0 14px; }
  h1 em { font-style: italic; color: #1c5a41; }
  .sub { font-size: 24px; color: #4a463b; max-width: 900px; line-height: 1.35; }
  .rule { width: 100%; height: 1px; background: #ddd8c9; margin: 30px 0 18px; }
  .meta { display: flex; gap: 10px; align-items: center; }
  .tag { font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: 0.08em;
         text-transform: uppercase; color: #6d685b; border: 1px solid #ddd8c9;
         border-radius: 999px; padding: 7px 12px; background: #fff; white-space: nowrap; }
  .tag.solid { background: #16150f; border-color: #16150f; color: #faf9f5; }
  .tag.live { color: #1c5a41; border-color: #bcd6c6; background: #eef5f0; }
</style></head><body>
  <div class="card">
    <svg class="mark" viewBox="0 0 32 32"><path d="M16 3.5 28.5 16 16 28.5 3.5 16z" fill="none"
      stroke="currentColor" stroke-width="1.4"/><circle cx="16" cy="16" r="4.2" fill="currentColor"/></svg>
    <h1>Mitra.<br><em>Delegated work, verified.</em></h1>
    <p class="sub">A private agent whose "done" is a database constraint, whose memory waits for your approval,
      and whose failures find you.</p>
    <div class="rule"></div>
    <div class="meta">
      <span class="tag solid">3 min demo</span>
      <span class="tag live">Nemotron · live inference</span>
      <span class="tag">NVIDIA \u00d7 Nebius</span>
    </div>
  </div>
</body></html>
"""


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:8099",
        help="any reachable Mitra instance; used only to serve the self-hosted fonts",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    for source, name, label in GALLERY:
        path = MEDIA / source
        if not path.exists():
            print(f"skip (missing) {source}")
            continue
        crop_for_gallery(path).save(OUT / name, optimize=True)
        print(f"gallery  {name:26} {label}")

    for source, name in (
        ("mobile-today.png", "09-mobile.png"),
        ("mobile-chat.png", "10-mobile-chat.png"),
    ):
        path = MEDIA / source
        if path.exists():
            with Image.open(path) as image:
                image.convert("RGB").save(OUT / name, optimize=True)
            print(f"gallery  {name:26} phone layout")

    shot = base64.b64encode((MEDIA / "today.png").read_bytes()).decode()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        page = await browser.new_page(
            viewport={"width": 1440, "height": 960}, device_scale_factor=1
        )
        await page.goto(args.base + "/", wait_until="domcontentloaded")

        await page.set_content(THUMB_HTML.replace("__SHOT__", f"data:image/png;base64,{shot}"))
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(OUT / "devpost-thumbnail.png"))
        print("thumb    devpost-thumbnail.png        1440x960 (3:2)")

        await page.set_viewport_size({"width": 1280, "height": 720})
        await page.set_content(YT_HTML)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(ROOT / "submission" / "video" / "thumbnail-youtube.png"))
        print("thumb    thumbnail-youtube.png         1280x720")

        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))
