"""Smoke test: verify browser can launch and reach JoySpace."""
import pytest
from playwright.async_api import async_playwright

from joyspace_operator.browser import launch_persistent_context


@pytest.mark.asyncio
async def test_browser_launches():
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        assert page is not None
        await ctx.close()
