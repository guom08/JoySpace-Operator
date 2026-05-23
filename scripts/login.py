#!/usr/bin/env python3
"""
scripts/login.py
────────────────
One-time login helper.  Run this script once to authenticate with JoySpace
and persist the session in the Chrome profile directory.

Usage:
    python scripts/login.py

After scanning the QR code and seeing the JoySpace home page, press Enter
to confirm and close the browser.  Subsequent automation runs will reuse
the saved session automatically.
"""
import asyncio

from joyspace_operator.browser import get_page, launch_persistent_context
from joyspace_operator.utils import get_logger
from playwright.async_api import async_playwright

log = get_logger("login")
JOYSPACE_URL = "https://joyspace.jd.com"


async def main() -> None:
    async with async_playwright() as pw:
        log.info("Launching Chrome with persistent profile …")
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx, JOYSPACE_URL)

        log.info("Browser opened.  If not yet logged in, scan the QR code now.")
        input("Press Enter once you are logged in and see the JoySpace home page … ")

        await ctx.close()
        log.info("Session saved.  You can now run automation scripts without scanning again.")


if __name__ == "__main__":
    asyncio.run(main())
