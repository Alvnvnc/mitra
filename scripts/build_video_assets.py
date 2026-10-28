"""Render the title card, end card and caption strips for the demo video.

The cards are HTML so they use the same self-hosted fonts as the dashboard.
Output: .design/video/*.png
"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".design" / "video"
BASE = "http://127.0.0.1:8099"
CHROME = str(pathlib.Path.home() / ".local" / "bin" / "google-chrome")

CAPTIONS = [
    (
        6,
        20,
        "The decision surface",
        "Today answers one question: what actually needs your decision?",
    ),
    (
        20,
        31,
        "Failure is a state",
        "A failed delivery is surfaced without being asked — it is not a silent gap.",
    ),
    (
        31,
        46,
        "Delegated work",
        "Every commitment carries its schedule and the instruction version in force.",
    ),
    (
        46,
        78,
        "Evidence gate",
        "Runs are gated by deterministic checks, not by the model's own opinion.",
    ),
    (
        78,
        88,
        "Version truth",
        "Versions are append-only, so a change dated tomorrow cannot apply today.",
    ),
    (
        88,
        117,
        "Human write path",
        "Memory waits for you: approve appends a bullet, reject leaves the page untouched.",
    ),
    (
        117,
        152,
        "Grounded chat",
        "Chat reads that memory, then shows its sources, its trace and its real cost.",
    ),
    (
        152,
        166,
        "Audit",
        "Denied tool calls stay in the log — that is the proof the allowlist does something.",
    ),
    (
        166,
        182,
        "Measured, not claimed",
        "Cost and reliability are counted per call from the ledger.",
    ),
]

SHARED = """
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; width: 1440px; height: 900px; }
  body { font-family: "Inter Tight", system-ui, sans-serif; color: #16150f; }
  .mono { font-family: "JetBrains Mono", monospace; }
"""

CAPTION_HTML = (
    """
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/fonts/fonts-local.css">
<style>
"""
    + SHARED
    + """
  body { background: transparent; }
  .band {
    position: absolute; left: 0; right: 0; bottom: 0; height: 96px;
    background: #16150f;
    display: flex; align-items: center; gap: 26px; padding: 0 52px;
    border-top: 2px solid #1c5a41;
  }
  .step {
    font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: 0.16em;
    text-transform: uppercase; color: #8fd3ae; white-space: nowrap;
    border-right: 1px solid rgba(255,255,255,0.18); padding-right: 26px;
  }
  .line { font-size: 25px; line-height: 1.3; color: #f7f5ee; letter-spacing: -0.012em; }
</style></head><body>
  <div class="band"><div class="step">__STEP__</div><div class="line">__LINE__</div></div>
</body></html>
"""
)

TITLE_HTML = (
    """
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/fonts/fonts-local.css">
<style>
"""
    + SHARED
    + """
  body {
    background: #faf9f5; display: grid; place-items: center;
    background-image: radial-gradient(circle at 18% 20%, #efece1 0, transparent 55%),
                      radial-gradient(circle at 82% 78%, #e9efe6 0, transparent 50%);
  }
  .card { width: 100%; padding: 0 118px; }
  .mark { color: #1c5a41; width: 58px; height: 58px; margin-bottom: 34px; }
  h1 { font-family: "Fraunces", Georgia, serif; font-size: 118px; line-height: 0.92;
       font-weight: 600; letter-spacing: -0.04em; margin: 0 0 18px; }
  h1 em { font-style: italic; color: #1c5a41; }
  .sub { font-size: 26px; color: #4a463b; max-width: 880px; line-height: 1.4; }
  .rule { width: 100%; height: 1px; background: #ddd8c9; margin: 44px 0 22px; }
  .meta { display: flex; gap: 12px; align-items: center; }
  .tag { font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: 0.08em;
         text-transform: uppercase; color: #6d685b; border: 1px solid #ddd8c9;
         border-radius: 999px; padding: 6px 12px; background: #fff; }
  .tag.solid { background: #16150f; border-color: #16150f; color: #faf9f5; }
</style></head><body>
  <div class="card">
    <svg class="mark" viewBox="0 0 32 32"><path d="M16 3.5 28.5 16 16 28.5 3.5 16z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="16" cy="16" r="4.2" fill="currentColor"/></svg>
    <h1>Mitra.<br><em>Delegated work, verified.</em></h1>
    <p class="sub">A personal agent with a persistent self-model, evidence-gated runs and governed tools. Built for the NVIDIA \u00d7 Nebius hackathon, Personal&nbsp;AI&nbsp;track.</p>
    <div class="rule"></div>
    <div class="meta">
      <span class="tag solid">3-minute walkthrough</span>
      <span class="tag">Nemotron · Nebius Token Factory</span>
      <span class="tag">Synthetic demo data</span>
    </div>
  </div>
</body></html>
"""
)

END_HTML = (
    """
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/fonts/fonts-local.css">
<style>
"""
    + SHARED
    + """
  body { background: #16150f; color: #f7f5ee; display: grid; place-items: center; }
  .card { width: 100%; padding: 0 118px; }
  .mark { color: #8fd3ae; width: 46px; height: 46px; margin-bottom: 26px; }
  h1 { font-family: "Fraunces", Georgia, serif; font-size: 92px; line-height: 0.98;
       font-weight: 600; letter-spacing: -0.035em; margin: 0 0 20px; }
  h1 em { font-style: italic; color: #8fd3ae; }
  .url { font-family: "JetBrains Mono", monospace; font-size: 19px; color: #d9d4c5; }
  .note { margin-top: 26px; font-size: 19px; color: #a9a396; max-width: 760px; line-height: 1.5; }
  .rule { width: 100%; height: 1px; background: rgba(255,255,255,0.16); margin: 40px 0 24px; }
</style></head><body>
  <div class="card">
    <svg class="mark" viewBox="0 0 32 32"><path d="M16 3.5 28.5 16 16 28.5 3.5 16z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="16" cy="16" r="4.2" fill="currentColor"/></svg>
    <h1>The ledger remembers.<br><em>You decide what it keeps.</em></h1>
    <div class="rule"></div>
    <p class="url">Live demo linked on the Devpost submission page</p>
    <p class="note">Synthetic demo data; the ledger, evidence gate and policy engine are the real ones.</p>
  </div>
</body></html>
"""
)


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(BASE + "/", wait_until="domcontentloaded")

        await page.set_content(TITLE_HTML)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT / "title.png"))

        await page.set_content(END_HTML)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT / "end.png"))

        manifest = []
        for index, (start, end, step, line) in enumerate(CAPTIONS):
            html = CAPTION_HTML.replace("__STEP__", step).replace("__LINE__", line)
            await page.set_content(html)
            await page.wait_for_timeout(220)
            path = OUT / f"cap{index:02d}.png"
            await page.screenshot(path=str(path), omit_background=True)
            manifest.append({"start": start, "end": end, "path": str(path), "line": line})

        (OUT / "captions.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        await browser.close()

    print(f"rendered {len(CAPTIONS)} captions + title + end card in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))
