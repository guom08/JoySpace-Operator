"""Browser management: launch Chrome with persistent profile."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

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
        args=["--start-maximized", "--remote-debugging-port=9222"],
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


async def wait_for_login(page: Page, timeout_s: int = 120) -> None:
    """等待 JoySpace 登录完成。

    检测是否存在登录二维码：若有，打印提示让用户扫码，然后轮询直到
    编辑器出现（登录成功）或超时。
    已登录时立即返回。
    """
    import asyncio
    from joyspace_operator.utils import get_logger
    log = get_logger(__name__)

    # 判断是否出现了登录二维码（img src 含 qr 或 login 相关选择器）
    qr_visible = await page.evaluate("""() => {
        // 常见登录页特征
        return !!(
            document.querySelector('canvas[id*="qr"]') ||
            document.querySelector('img[src*="qrcode"]') ||
            document.querySelector('img[src*="qr_code"]') ||
            document.querySelector('.login-qr') ||
            document.querySelector('[class*="qrCode"]') ||
            document.querySelector('[class*="QRCode"]') ||
            document.querySelector('[class*="login"]')
        ) && !document.querySelector('.page-main-content .slate-editor');
    }""")

    if not qr_visible:
        # 已登录，直接检查编辑器是否存在
        editor_ready = await page.evaluate("""() =>
            !!document.querySelector('.page-main-content .slate-editor')
        """)
        if editor_ready:
            return
        # 页面还在加载，稍等
        try:
            await page.wait_for_selector(
                '.page-main-content .slate-editor', timeout=10000)
        except Exception:
            pass
        return

    # 有二维码，需要用户扫码
    log.warning("⚠️  检测到登录二维码，请在浏览器中扫码登录 JoySpace...")
    print("\n" + "="*60)
    print("⚠️  请扫描浏览器中的 JoySpace 登录二维码")
    print("="*60 + "\n")

    # 轮询直到编辑器出现或超时
    deadline = timeout_s * 10  # 每次等 100ms
    for _ in range(deadline):
        await asyncio.sleep(0.1)
        logged_in = await page.evaluate("""() =>
            !!document.querySelector('.page-main-content .slate-editor')
        """)
        if logged_in:
            log.info("✓ 登录成功")
            print("✓ 登录成功，继续执行...\n")
            return

    raise TimeoutError(f"等待 JoySpace 登录超时（{timeout_s}s），请检查是否已扫码")

