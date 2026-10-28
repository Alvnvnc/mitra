"""Capture interactive surfaces: new-commitment dialog, palette, memory editor."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".design" / "shots"
BASE = "http://127.0.0.1:8099"
CHROME = str(Path.home() / ".local" / "bin" / "google-chrome")


def main() -> int:
    errors: list[str] = []
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(BASE + "/#/commitments", wait_until="networkidle")
        page.click("#newCommitmentTop")
        page.wait_for_timeout(350)
        page.screenshot(path=str(OUT / "dialog.png"))

        page.keyboard.press("Escape")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.keyboard.type("mem")
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / "palette.png"))
        page.keyboard.press("Escape")

        page.goto(BASE + "/#/memory", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.click('[data-act="edit-memory"]')
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "memory-edit.png"))
        browser.close()
    print("errors:", errors or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
