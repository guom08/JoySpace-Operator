#!/usr/bin/env python3
"""逐项演练：有序列表、代办、缩进、引用"""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from joyspace_operator.browser import launch_persistent_context, get_page, wait_for_login
from joyspace_operator.document import open_doc, DocumentWriter
from joyspace_operator.utils import get_logger

load_dotenv()
log = get_logger("test_new_features")
SS = Path("/tmp/test_new_features")
SS.mkdir(exist_ok=True)
_step = 0

TARGET_URL = "https://joyspace.jd.com/pages/EVI3T3deZsBPaiqjBCSF"

async def shot(page, label):
    global _step
    _step += 1
    path = str(SS / f"{_step:02d}_{label}.png")
    await page.screenshot(path=path, full_page=True)
    log.info("截图 → %s", path)

async def main():
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx)
        await open_doc(page, TARGET_URL)
        await wait_for_login(page)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        w = DocumentWriter(page)
        await w.set_title("")
        await w.clear()
        await w.focus()
        await shot(page, "cleared")

        # ── 测试1: 有序列表（第一个，从1开始）
        log.info("=== 测试 有序列表（首个）===")
        await w.ordered_list(["第一项", "第二项", "第三项"])
        await shot(page, "ordered_list_1")

        # ── 写一些普通段落，制造"中间断开"
        await w.paragraph("---中间段落---")

        # ── 测试2: 有序列表（第二个，restart=True 自动从1开始）
        log.info("=== 测试 有序列表（重新开始）===")
        await w.ordered_list(["新列表第一项", "新列表第二项"], restart=True)
        await shot(page, "ordered_list_2_restart")

        # ── 测试3: 代办列表
        log.info("=== 测试 代办列表 ===")
        await w.todo_list(["待完成事项 A", "待完成事项 B", "待完成事项 C"])
        await shot(page, "todo_list")

        # ── 测试4&5: 缩进（Tab / Shift+Tab）
        log.info("=== 测试 缩进 ===")
        await w.paragraph("无缩进文字")
        await page.keyboard.press("Tab")
        await w.paragraph("一级缩进")
        await page.keyboard.press("Tab")
        await w.paragraph("二级缩进")
        await page.keyboard.press("Shift+Tab")
        await w.paragraph("退回一级缩进")
        await page.keyboard.press("Shift+Tab")
        await shot(page, "indent")

        # ── 测试6: 引用块
        log.info("=== 测试 引用块 ===")
        await w.quote_block("这是一段引用文字，来源于某个重要文献")
        await shot(page, "quote_block")

        await shot(page, "final")
        log.info("全部演练完成")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
