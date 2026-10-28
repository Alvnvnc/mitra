"""Capture every view of the running dashboard for visual review."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".design" / "shots"
BASE = "http://127.0.0.1:8099"
CHROME = str(Path.home() / ".local" / "bin" / "google-chrome")
VIEWS = ["today", "chat", "commitments", "memory", "skills", "audit", "stats"]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    views = args or VIEWS
    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--force-color-profile=srgb"])
        page = browser.new_page(viewport={"width": 1440, "height": 950}, device_scale_factor=1)
        page.on(
            "console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None
        )
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        boot = page.request.get(BASE + "/api/bootstrap").json()
        first = boot["commitments"][0]["id"]

        for view in views:
            page.goto(f"{BASE}/#/{view}", wait_until="networkidle")
            page.wait_for_timeout(450)
            page.screenshot(path=str(OUT / f"{view}.png"), full_page=False)
            print("shot", view)

        if args or "--detail" in sys.argv:
            page.goto(f"{BASE}/#/commitments/{first}", wait_until="networkidle")
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "commitment.png"), full_page=False)
            page.click("tbody tr.clickable")
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "drawer.png"), full_page=False)
            print("shot commitment + drawer")

        # mobile pass
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        for view in ("today", "chat", "commitments", "memory", "stats"):
            mobile.goto(f"{BASE}/#/{view}", wait_until="networkidle")
            mobile.wait_for_timeout(350)
            mobile.screenshot(path=str(OUT / f"m-{view}.png"))
            print("shot mobile", view)
        browser.close()
    print("console errors:", errors or "none")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
