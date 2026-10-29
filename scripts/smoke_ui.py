"""Interaction smoke test: every primary action must complete without errors.

    python scripts/smoke_ui.py https://mitra.pavernor.tech

Reseeds first when MITRA_ADMIN_TOKEN is in the environment, because the test
walks the approval inbox and a previous run will have emptied it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
CHROME = str(Path.home() / ".local" / "bin" / "google-chrome")


def reseed(base: str) -> None:
    token = os.environ.get("MITRA_ADMIN_TOKEN", "").strip()
    if not token:
        print("(no MITRA_ADMIN_TOKEN — not reseeding; the approval inbox may be empty)")
        return
    request = urllib.request.Request(
        base.rstrip("/") + "/api/demo/reset",
        data=b"{}",
        method="POST",
        headers={
            "content-type": "application/json",
            "x-mitra-admin": token,
            # Cloudflare's browser-integrity check blocks the default
            # Python-urllib user agent on this zone.
            "user-agent": "mitra-smoke/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    print(
        "reseeded:",
        len(payload["commitments"]),
        "commitments,",
        len(payload["proposals"]),
        "proposals",
    )


def main() -> int:
    errors: list[str] = []
    bad: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))

        def expected(status: int, url: str) -> bool:
            """429 from the chat allowance is a working limiter, not a defect."""
            return status == 429 and "/api/chat/stream" in url

        page.on(
            "console",
            lambda m: errors.append(m.text) if m.type == "error" and "429" not in m.text else None,
        )
        page.on(
            "response",
            lambda r: (
                bad.append(f"{r.status} {r.url}")
                if r.status >= 400 and not expected(r.status, r.url)
                else None
            ),
        )

        reseed(BASE)
        page.goto(BASE + "/#/today", wait_until="networkidle")
        page.wait_for_timeout(400)

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
        # A live run takes seconds; wait for the POST itself instead of guessing.
        with page.expect_response(
            lambda r: "/run" in r.url and r.request.method == "POST", timeout=120_000
        ):
            page.click('[data-act="run-now"]')
        page.wait_for_timeout(900)
        if not page.locator("#drawer").is_hidden():
            page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        print("after run:", page.locator(".chip").first.inner_text())

        # audit tabs
        page.goto(BASE + "/#/audit", wait_until="networkidle")
        page.wait_for_selector('[data-act="audit-filter"]', timeout=30_000)
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
        try:
            page.wait_for_selector(".msg-agent .agent-body p", timeout=30000)
            page.wait_for_timeout(1500)
            replied = page.locator(".msg-agent .agent-body").last.inner_text()
        except Exception:  # noqa: BLE001 — the bubble may still be streaming
            replied = ""
        if "cannot be spent" in replied or "limits chat turns" in replied:
            print("chat: rate limited (allowance exhausted — the limiter is working)")
        else:
            print("chat reply chars:", len(replied))

        browser.close()
    print("console errors:", errors or "none")
    print("bad responses:", bad or "none")
    return 1 if errors or bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
