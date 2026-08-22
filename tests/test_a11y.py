"""Automated accessibility scan of the main UI, using axe-core.

Requires Playwright plus an installed Chromium browser; skipped otherwise so the
regular `pytest tests/` run (which doesn't install a browser) is unaffected. A
dedicated CI job installs Playwright's browser and runs this file — see
.github/workflows/ci.yml.

Most of the UI lives behind client-side navigation (`.nav-btn[data-page]`) or
modals that don't exist in the DOM until opened, so a single scan of the landing
page would miss almost everything. This walks through every page and the two
modals reachable without seeded data, aggregating violations across all of them.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest
import uvicorn

AXE_SCRIPT = Path(__file__).parent / "vendor" / "axe.min.js"

try:
    from playwright.sync_api import Page, sync_playwright

    _PLAYWRIGHT_IMPORTABLE = True
except ImportError:  # pragma: no cover - exercised only when the extra isn't installed
    _PLAYWRIGHT_IMPORTABLE = False

# Violations at these impact levels fail the check. "minor"/"moderate" are left out
# for now to keep this gate actionable while the broader a11y pass (#99) continues.
FAILING_IMPACTS = {"serious", "critical"}

NAV_PAGES = [
    "generate",
    "batch",
    "refine",
    "history",
    "presets",
    "sd",
    "img2img",
    "inpaint",
    "xyplot",
    "compare",
    "gallery",
    "pnginfo",
    "wildcards",
    "stats",
    "backup",
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _running_app() -> Iterator[str]:
    from main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("Test server did not start in time")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _scan(page: Page, label: str, violations_by_label: dict) -> None:
    results = page.evaluate("async () => await axe.run()")
    found = [v for v in results["violations"] if v["impact"] in FAILING_IMPACTS]
    if found:
        violations_by_label[label] = found


@pytest.mark.skipif(not _PLAYWRIGHT_IMPORTABLE, reason="playwright is not installed")
def test_no_serious_or_critical_axe_violations_across_the_app():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium browser is not installed for Playwright: {e}")

        violations_by_label: dict = {}
        try:
            with _running_app() as base_url:
                page = browser.new_page()
                page.goto(base_url + "/", wait_until="networkidle")
                page.add_script_tag(path=str(AXE_SCRIPT))
                _scan(page, "generate (landing)", violations_by_label)

                for page_name in NAV_PAGES:
                    page.click(f'.nav-btn[data-page="{page_name}"]', timeout=3000)
                    page.wait_for_timeout(150)
                    _scan(page, f"page:{page_name}", violations_by_label)

                # Modals reachable without seeded data.
                page.click('.nav-btn[data-page="presets"]', timeout=3000)
                page.wait_for_timeout(150)
                page.click("#add-preset-btn", timeout=3000)
                page.wait_for_timeout(150)
                _scan(page, "modal:preset-modal", violations_by_label)
                page.keyboard.press("Escape")

                page.keyboard.press("?")
                page.wait_for_timeout(150)
                _scan(page, "modal:shortcuts-modal", violations_by_label)
                page.keyboard.press("Escape")
        finally:
            browser.close()

    if violations_by_label:
        lines = []
        for label, violations in violations_by_label.items():
            lines.append(f"== {label} ==")
            for v in violations:
                targets = ", ".join(str(n["target"]) for n in v["nodes"])
                lines.append(f"  [{v['impact']}] {v['id']}: {v['help']} ({v['helpUrl']}) — {targets}")
        pytest.fail("axe-core found serious/critical violations:\n" + "\n".join(lines))
