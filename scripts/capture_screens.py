#!/usr/bin/env python3
"""Capture dashboard screenshots for verification and the submission gallery."""

from __future__ import annotations

import argparse
import asyncio
import pathlib
from pathlib import Path

from playwright.async_api import async_playwright

VIEWS = {
    "today": "#/today",
    "chat": "#/chat",
    "commitments": "#/commitments",
    "memory": "#/memory",
    "skills": "#/skills",
    "audit": "#/audit",
    "stats": "#/stats",
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8099")
    parser.add_argument("--out", default="docs/media")
    parser.add_argument("--only", default="")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    selected = [v for v in VIEWS if not args.only or v in args.only.split(",")]
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=str(pathlib.Path.home() / ".local/bin/google-chrome")
        )
        page = await browser.new_page(
            viewport={"width": args.width, "height": args.height}, device_scale_factor=2
        )
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        for name in selected:
            await page.goto(args.base + "/" + VIEWS[name], wait_until="networkidle")
            await page.wait_for_timeout(1200)
            await page.screenshot(path=str(out / f"{name}.png"), full_page=(name != "chat"))
            print("captured", name)

        # commitment detail (first row)
        await page.goto(args.base + "/#/commitments", wait_until="networkidle")
        await page.wait_for_timeout(500)
        row = page.locator("tr.clickable").first
        if await row.count():
            await row.click()
            await page.wait_for_timeout(1200)
            await page.screenshot(path=str(out / "commitment-detail.png"), full_page=True)
            print("captured commitment-detail")

        # chat interaction
        await page.goto(args.base + "/#/chat", wait_until="networkidle")
        await page.wait_for_timeout(800)
        await page.fill("#chatInput", "What needs a decision today?")
        await page.click("#sendBtn")
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(out / "chat-reply.png"), full_page=False)
        print("captured chat-reply")

        print("console errors:", errors or "none")
        await browser.close()

    # mobile pass
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=str(pathlib.Path.home() / ".local/bin/google-chrome")
        )
        page = await browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        for name in ("today", "chat", "memory"):
            await page.goto(args.base + "/" + VIEWS[name], wait_until="networkidle")
            await page.wait_for_timeout(900)
            await page.screenshot(path=str(out / f"mobile-{name}.png"), full_page=True)
            print("captured mobile", name)
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
