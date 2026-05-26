#!/usr/bin/env python3
"""
clear_doc.py — 清空 JoySpace 文档正文（保留文档本身，只删内容）。
用法：python scripts/clear_doc.py
"""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page
from joyspace_operator.browser import launch_persistent_context, get_page
from joyspace_operator.document import open_doc
from joyspace_operator.utils import get_logger

load_dotenv()
log = get_logger("clear_doc")

DOC_URL = "https://joyspace.jd.com/pages/ypqSBeVkLZCuAicDPt4u"
SS = Path("/tmp/joyspace_screenshots")
SS.mkdir(exist_ok=True)


async def clear_doc(page: Page) -> None:
    """选中编辑器内全部内容并删除。

    关键：焦点必须在标题栏或正文文本区（不能在表格内），
    然后连续两次 Cmd+A 才能选中整个文档（含表格），再 Backspace 删除。
    """
    for attempt in range(6):
        # 检查是否已清空
        wc = await page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            return ed ? (ed.innerText || '').replace(/\\s/g, '').length : -1;
        }""")
        has_tbl = await page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            return ed ? (ed.querySelector('table') !== null ||
                         ed.querySelector('[data-slate-type="table"]') !== null) : false;
        }""")
        if wc == 0 and not has_tbl:
            break
        log.info("第%d轮: word_count=%d, has_table=%s", attempt + 1, wc, has_tbl)

        # 1. 点标题栏（最可靠的非表格焦点位置）
        coords = await page.evaluate("""() => {
            // 优先：标题栏 slate-editor
            const titleEl = document.querySelector(
                '.page-title-below [data-slate-node="element"], ' +
                '.page-title-below .slate-editor');
            if (titleEl) {
                const r = titleEl.getBoundingClientRect();
                if (r.width > 0 && r.height > 0)
                    return {x: Math.round(r.x + r.width * 0.15),
                            y: Math.round(r.y + r.height / 2), via: 'title'};
            }
            // 次选：正文编辑区第一个非表格顶层块
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (ed) {
                const nonTable = Array.from(ed.children).filter(b =>
                    b.dataset && b.dataset.slateNode === 'element' &&
                    !b.classList.contains('sl-table-wrap') &&
                    !b.querySelector('table') &&
                    !b.querySelector('[data-slate-type="table"]')
                );
                const t = nonTable[0];
                if (t) {
                    const r = t.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: Math.round(r.x + r.width * 0.15),
                                y: Math.round(r.y + r.height / 2), via: 'body'};
                }
                const er = ed.getBoundingClientRect();
                return {x: Math.round(er.x + er.width * 0.15),
                        y: Math.round(er.y + 30), via: 'editor-top'};
            }
            return null;
        }""")
        if coords and isinstance(coords, dict):
            log.info("点击焦点 via=%s (%d, %d)", coords.get("via"), coords["x"], coords["y"])
            await page.mouse.click(coords["x"], coords["y"])
        await page.wait_for_timeout(400)

        # 2. 连续两次 Cmd+A（第一次选当前块，第二次选整个文档）
        await page.keyboard.press("Meta+a")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Meta+a")
        await page.wait_for_timeout(200)

        # 截图确认选中状态（仅第一轮）
        if attempt == 0:
            await page.evaluate("window.scrollTo(0, 0)")
            await page.screenshot(path=str(SS / "clear_01_selected.png"), full_page=True)
            log.info("截图：选中状态")

        # 3. Backspace 删除
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(600)

    # 最终截图
    await page.evaluate("window.scrollTo(0, 0)")
    await page.screenshot(path=str(SS / "clear_02_done.png"), full_page=True)
    log.info("截图：清空后")


async def main() -> None:
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx)
        await open_doc(page, DOC_URL)
        await page.wait_for_timeout(500)

        log.info("开始清空文档…")
        await clear_doc(page)
        log.info("清空完成，截图在 %s", SS)

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
