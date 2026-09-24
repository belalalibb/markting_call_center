"""P4 UI smoke (Playwright, headless Chromium) against a running QEVION server with NO provider key.

Checks: first-run banner + dismiss; Normal hides telemetry cards, Advanced shows them; Admin vendor list has no dead
providers; composition labels mark simulated vs KEY MISSING; connecting a real-provider composition without a key
shows an actionable error with an Admin link; mobile (390 px) header does not overlap content; 0 console errors.

usage: .venv/bin/python scripts/ui_smoke_p4.py OUT.json [--base http://localhost:8000]
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

from playwright.sync_api import sync_playwright

BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost:8000"


def main() -> int:
    out = sys.argv[1]
    checks: dict[str, Any] = {}
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(BASE + "/#/console")
        pg.wait_for_selector("#firstrun", timeout=10000)
        checks["first_run_banner"] = "Admin" in (pg.text_content("#firstrun") or "")
        pg.wait_for_selector("text=Live session", timeout=10000)
        checks["normal_hides_telemetry"] = not pg.is_visible("text=Interruption metrics")
        pg.click("#uimode")
        checks["advanced_shows_telemetry"] = pg.is_visible("text=Interruption metrics")
        pg.click("#uimode")
        opts = pg.eval_on_selector_all("select >> nth=1 >> option", "els => els.map(e => e.textContent)")
        checks["label_simulated"] = any("simulated (no key needed)" in (o or "") for o in opts)
        checks["label_key_missing"] = any("KEY MISSING" in (o or "") for o in opts)
        pg.select_option("select >> nth=1", "comp_s2s_openai_v1")
        pg.click("button:has-text('Connect')")
        pg.wait_for_selector(".msg.sys.bad", timeout=15000)
        err = pg.text_content(".msg.sys.bad") or ""
        checks["no_key_error_actionable"] = "Admin" in err and pg.is_visible(".msg.sys.bad a[href='#/admin']")
        pg.click("#firstrun button:has-text('Dismiss')")
        checks["first_run_dismissed"] = not pg.is_visible("#firstrun")
        pg.goto(BASE + "/#/admin")
        pg.wait_for_selector("text=Ephemeral test key", timeout=10000)
        vendors = pg.eval_on_selector_all(
            "section:has-text('Ephemeral test key') select option", "els => els.map(e => e.value)"
        )
        checks["admin_vendors_real_only"] = set(vendors) == {"openai", "typesafe"}
        m = b.new_page(viewport={"width": 390, "height": 844})
        m.on("console", lambda x: errors.append(x.text) if x.type == "error" else None)
        m.goto(BASE + "/#/console")
        m.wait_for_selector("text=Live session", timeout=10000)
        top = m.eval_on_selector("#top", "e => e.getBoundingClientRect().bottom")
        app = m.eval_on_selector("#app", "e => e.getBoundingClientRect().top")
        wide = m.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        checks["mobile_header_not_overlapping"] = app >= top - 1
        checks["mobile_no_horizontal_overflow"] = bool(wide)
        m.screenshot(path=str(pathlib.Path(out).with_suffix(".mobile.png")))
        pg.goto(BASE + "/#/console")
        pg.wait_for_selector("text=Live session", timeout=10000)
        pg.screenshot(path=str(pathlib.Path(out).with_suffix(".desktop.png")))
        b.close()
    # the no-key connect produces one expected WS close; only JS errors count
    js_errors = [e for e in errors if "WebSocket" not in e and "Failed to load resource" not in e]
    checks["no_console_errors"] = not js_errors
    rep = {"checks": checks, "passed": all(checks.values()), "console_errors": js_errors[:10]}
    pathlib.Path(out).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
