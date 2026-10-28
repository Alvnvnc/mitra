#!/usr/bin/env python3
"""Record the 3-minute demo walkthrough described in docs/SUBMISSION.md.

    python scripts/record_demo.py --base https://… --out docs/media/demo.webm

The recording is silent by design: it is the picture track for a voice-over, so
every action follows the script's timeline. Playwright captures the viewport
only, which keeps the frame clean (no browser chrome).
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import time
from pathlib import Path

from playwright.async_api import async_playwright

CHROME = pathlib.Path.home() / ".local/bin/google-chrome"


class Shot:
    def __init__(self, page) -> None:
        self.page = page
        self.started = time.monotonic()

    async def wait_until(self, seconds: float) -> None:
        """Sleep until `seconds` after recording started (keeps the script on time)."""
        remaining = seconds - (time.monotonic() - self.started)
        if remaining > 0:
            await self.page.wait_for_timeout(int(remaining * 1000))

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="networkidle")
        await self.page.wait_for_timeout(600)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8099")
    parser.add_argument("--out", default="docs/media/demo.webm")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=str(CHROME))
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(out.parent / "_video"),
            record_video_size={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        shot = Shot(page)

        # 0:00 — Today
        await shot.goto(args.base + "/#/today")
        await shot.wait_until(12)
        await page.mouse.wheel(0, 260)  # banner + KPIs
        await shot.wait_until(17)
        await page.locator('[data-act="notice"]').first.click()
        await shot.wait_until(26)
        await page.keyboard.press("Escape")
        await shot.wait_until(30)

        # 0:30 — Commitments → detail → runs
        await shot.goto(args.base + "/#/commitments")
        await shot.wait_until(36)
        await page.locator("tr.clickable").first.click()
        await shot.wait_until(46)
        await page.mouse.wheel(0, 430)  # runs table
        await shot.wait_until(62)

        # 1:02 — instruction versions
        await page.mouse.wheel(0, 700)
        await shot.wait_until(78)
        await page.mouse.wheel(0, 380)
        await shot.wait_until(88)

        # 1:28 — memory approval inbox
        await shot.goto(args.base + "/#/memory")
        await shot.wait_until(96)
        await page.mouse.wheel(0, 180)
        await shot.wait_until(108)
        await page.locator('[data-act="reject-proposal"]').first.click()
        await shot.wait_until(116)

        # 1:56 — chat turn
        await shot.goto(args.base + "/#/chat")
        await shot.wait_until(122)
        await page.fill("#chatInput", "What needs a decision today?")
        await shot.wait_until(126)
        await page.click("#sendBtn")
        await shot.wait_until(142)

        # 2:22 — audit, denied filter
        await shot.goto(args.base + "/#/audit")
        await shot.wait_until(148)
        await page.locator('[data-act="audit-filter"][data-filter="denied"]').click()
        await shot.wait_until(164)

        # 2:44 — stats
        await shot.goto(args.base + "/#/stats")
        await shot.wait_until(176)
        await page.mouse.wheel(0, 300)
        await shot.wait_until(180)

        await context.close()  # finalises the video file
        await browser.close()

    video = sorted((out.parent / "_video").glob("*.webm"))[-1]
    video.replace(out)
    leftover = [p for p in (out.parent / "_video").iterdir() if p.is_file()]
    for path in leftover:
        path.unlink()
    (out.parent / "_video").rmdir()
    print(f"recorded {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
