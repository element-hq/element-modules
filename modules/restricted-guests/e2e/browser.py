"""Headless Chromium for the browser checks, through Playwright.

Playwright's own Chromium, or the one at $GF_CHROMIUM. Element Web and the
stack are on localhost, so the proxy is kept out of the browser.
"""

import os

from playwright.sync_api import sync_playwright

CHROMIUM = os.environ.get("GF_CHROMIUM")
_PROXY_VARS = {"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"}


def launch(**context_options):
    """Start Playwright, Chromium and a context; returns all three."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        executable_path=CHROMIUM,
        headless=True,
        args=["--no-sandbox", "--no-proxy-server"],
        env={k: v for k, v in os.environ.items() if k not in _PROXY_VARS},
    )
    return pw, browser, browser.new_context(**context_options)


def close(pw, browser):
    browser.close()
    pw.stop()
