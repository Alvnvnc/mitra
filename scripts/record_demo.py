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
        await self.page.mouse.move(900, 520)

    async def scroll(self, amount: int) -> None:
        await self.page.mouse.move(900, 520)
        await self.page.mouse.wheel(0, amount)


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

        try:
            await record(page, shot, args.base)
        finally:
            await context.close()  # always finalise the video file
            await browser.close()

    video = sorted((out.parent / "_video").glob("*.webm"))[-1]
    video.replace(out)
    leftover = [p for p in (out.parent / "_video").iterdir() if p.is_file()]
    for path in leftover:
        path.unlink()
    (out.parent / "_video").rmdir()
    print(f"recorded {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


async def record(page, shot, base: str) -> None:
    # 0:00 — Today: the decision surface first
    await shot.goto(base + "/#/today")
    await shot.wait_until(13)
    await shot.scroll(250)  # needs-you rows + commitments
    await shot.wait_until(20)
    await page.locator('[data-act="notice"]').first.click()
    await shot.wait_until(28)
    await page.keyboard.press("Escape")
    await shot.wait_until(31)

    # 0:31 — Commitments → detail → runs
    await shot.goto(base + "/#/commitments")
    await shot.wait_until(37)
    await page.locator("tr.clickable").first.click()
    await shot.wait_until(46)
    await shot.scroll(360)  # runs table
    await shot.wait_until(62)

    # 1:02 — instruction versions + evidence
    await shot.scroll(620)
    await shot.wait_until(78)
    await shot.scroll(320)
    await shot.wait_until(88)

    # 1:28 — memory approval inbox
    await shot.goto(base + "/#/memory")
    await shot.wait_until(95)
    await shot.scroll(170)
    await shot.wait_until(107)
    await page.locator('[data-act="reject-proposal"]').first.click()
    await shot.wait_until(114)
    await shot.scroll(-400)
    await shot.wait_until(117)

    # 1:57 — chat: a fresh turn with retrieval + trace
    await shot.goto(base + "/#/chat")
    await shot.wait_until(121)
    await page.locator('[data-act="new-chat"]').click()
    await shot.wait_until(124)
    await page.fill("#chatInput", "Did yesterday's brief actually deliver?")
    await shot.wait_until(128)
    await page.click("#sendBtn")
    # Live Nemotron takes a few seconds; wait for the answer rather than guess.
    try:
        await page.wait_for_selector(".msg-agent .agent-body p", timeout=45_000)
    except Exception:  # noqa: BLE001 — keep the recording going
        pass
    await shot.wait_until(145)
    if await page.locator(".trace summary").count():
        await page.locator(".trace summary").last.click()
    await shot.wait_until(150)

    # 2:30 — audit, denied filter
    await shot.goto(base + "/#/audit")
    await shot.wait_until(154)
    await page.locator('[data-act="audit-filter"][data-filter="denied"]').click()
    await shot.wait_until(166)

    # 2:46 — stats
    await shot.goto(base + "/#/stats")
    await shot.wait_until(173)
    await shot.scroll(300)
    await shot.wait_until(182)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
