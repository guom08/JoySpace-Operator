"""Browser management: launch Chrome with persistent profile."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

load_dotenv()

_USER_DATA_DIR = os.getenv(
    "CHROME_USER_DATA_DIR",
    str(Path.home() / "Library/Application Support/Google/Chrome/JoySpaceProfile"),
)


async def launch_persistent_context(playwright: Playwright) -> BrowserContext:
    """Launch Chromium with a persistent profile so login survives restarts.

    On first run the user must scan the JoySpace QR code; subsequent runs
    reuse the stored session automatically.
    """
    context = await playwright.chromium.launch_persistent_context(
        _USER_DATA_DIR,
        headless=False,          # must be visible for QR-code scan
        channel="chrome",        # use the installed Google Chrome binary
        args=["--start-maximized"],
        no_viewport=True,
    )
    return context


async def get_page(context: BrowserContext, url: str | None = None):
    """Return the first page (or open a new one at *url*)."""
    pages = context.pages
    page = pages[0] if pages else await context.new_page()
    if url:
        await page.goto(url, wait_until="domcontentloaded")
    return page
