"""Interaction smoke test: every primary action must complete without errors."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
CHROME = str(Path.home() / ".local" / "bin" / "google-chrome")


def main() -> int:
    errors: list[str] = []
    bad: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda m: errors.append(m.text) if m.type == "error" else None,
        )
        page.on(
            "response",
            lambda r: bad.append(f"{r.status} {r.url}") if r.status >= 400 else None,
        )

        page.goto(BASE + "/#/today", wait_until="networkidle")
        page.wait_for_timeout(300)

        # approve a memory proposal from Today
        page.click('[data-act="approve-proposal"]')
        page.wait_for_timeout(900)
        print("today after approve:", page.locator("#view .display").inner_text()[:40])

        # memory view: reject the next proposal
        page.goto(BASE + "/#/memory", wait_until="networkidle")
        page.wait_for_timeout(500)
        if page.locator('[data-act="reject-proposal"]').count():
            page.click('[data-act="reject-proposal"]')
            page.wait_for_timeout(900)
        print("memory proposals:", page.locator(".proposal").count())

        # commitment detail: run now
        page.goto(BASE + "/#/commitments", wait_until="networkidle")
        page.click("tbody tr.clickable")
        page.wait_for_timeout(700)
        page.click('[data-act="run-now"]')
        page.wait_for_timeout(2500)
        if not page.locator("#drawer").is_hidden():
            page.keyboard.press("Escape")
        print("after run:", page.locator(".chip").first.inner_text())

        # audit tabs
        page.goto(BASE + "/#/audit", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.click('[data-act="audit-filter"][data-filter="denied"]')
        page.wait_for_timeout(500)
        page.click('[data-act="audit-tab"][data-tab="calls"]')
        page.wait_for_timeout(500)
        print("audit rows:", page.locator("tbody tr").count())

        # stats range switch
        page.goto(BASE + "/#/stats", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.click('[data-act="stats-days"][data-days="30"]')
        page.wait_for_timeout(800)
        print("stats kpi:", page.locator(".kpi").first.inner_text().replace("\n", " | "))

        # chat: send a message and wait for the final answer
        page.goto(BASE + "/#/chat", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.fill("#chatInput", "Which commitment is most at risk right now?")
        page.click("#sendBtn")
        page.wait_for_selector(".msg-agent .agent-body p", timeout=30000)
        page.wait_for_timeout(2500)
        print("chat reply chars:", len(page.locator(".msg-agent .agent-body").last.inner_text()))

        browser.close()
    print("console errors:", errors or "none")
    print("bad responses:", bad or "none")
    return 1 if errors or bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
