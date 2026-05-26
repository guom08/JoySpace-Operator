"""
navigator.py — 打开 JoySpace 文档，等待编辑器就绪。
"""
from __future__ import annotations

import asyncio
from playwright.async_api import Page, TimeoutError as PWTimeout

from joyspace_operator.utils import get_logger

log = get_logger(__name__)

EDITOR_SEL = ".page-main-content .slate-editor.use-virtual-caret"
TITLE_SEL   = "[placeholder*='标题'], [class*='title-input']"


async def open_doc(page: Page, url: str, timeout: int = 30_000) -> None:
    """导航到文档 URL 并等待 Slate 编辑器加载完毕。"""
    log.info("打开文档: %s", url)
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    # 等待登录态（如果跳转到登录页则提示用户扫码）
    await _wait_for_login(page)

    # 关闭弹窗
    await _dismiss_popups(page)

    # 等待编辑器出现
    try:
        await page.wait_for_selector(EDITOR_SEL, timeout=timeout)
        log.info("编辑器就绪")
    except PWTimeout:
        raise RuntimeError(f"编辑器未在 {timeout}ms 内出现，请检查文档 URL 是否正确")


async def _wait_for_login(page: Page, poll_interval: float = 3.0, max_wait: float = 180.0) -> None:
    elapsed = 0.0
    while elapsed < max_wait:
        text = await page.evaluate("() => document.body.innerText")
        if "扫描二维码" in text or "登录" in text:
            if elapsed == 0:
                log.warning("检测到登录页，请扫码登录（最多等待 %.0f 秒）…", max_wait)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        else:
            return
    raise RuntimeError("等待扫码登录超时")


async def _dismiss_popups(page: Page) -> None:
    """关闭「不再提醒」「稍后」等弹窗。"""
    try:
        await page.evaluate("""() => {
            document.querySelectorAll('button').forEach(btn => {
                const t = btn.innerText.trim();
                if (t.includes('不再提醒') || t.includes('稍后') || t.includes('知道了')) btn.click();
            });
        }""")
    except Exception:
        pass
