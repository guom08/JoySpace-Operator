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


async def create_doc(page: Page, timeout: int = 30_000) -> tuple[str, Page]:
    """在 JoySpace 首页新建一个空白文档，返回 (url, new_page)。

    步骤：首页 → 点击"新建" → 菜单选"文档" → 模板弹窗点"新建空白文档"
          → 新标签页打开 → 等待编辑器就绪 → 返回 (url, page)。
    """
    log.info("新建空白文档…")
    await page.goto("https://joyspace.jd.com/", wait_until="domcontentloaded", timeout=timeout)
    await _wait_for_login(page)
    await _dismiss_popups(page)

    # 点击左上角"新建"按钮
    await page.wait_for_selector("text=新建", timeout=timeout)
    await page.click("text=新建")
    await page.wait_for_timeout(800)

    # 下拉菜单里点"文档"——用 JS 直接触发点击，防止 survey 弹窗抢走焦点关闭菜单
    clicked = await page.evaluate("""() => {
        const items = Array.from(document.querySelectorAll('.create-button-menu__item'));
        const doc = items.find(el => el.innerText.trim() === '文档');
        if (doc) { doc.click(); return true; }
        return false;
    }""")
    if not clicked:
        raise RuntimeError("未找到'文档'菜单项")
    await page.wait_for_timeout(800)

    # 模板弹窗里点"新建空白文档"——会在新标签页打开文档
    await page.wait_for_selector("text=新建空白文档", timeout=timeout)
    async with page.context.expect_page(timeout=timeout) as page_info:
        await page.click("text=新建空白文档")
    new_page = await page_info.value

    # 等待新标签页编辑器就绪
    await new_page.wait_for_load_state("domcontentloaded", timeout=timeout)
    await new_page.wait_for_selector(EDITOR_SEL, timeout=timeout)

    doc_url = new_page.url
    log.info("新文档已创建: %s", doc_url)
    return doc_url, new_page


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
