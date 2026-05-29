#!/usr/bin/env python3
"""诊断：有序列表重新开始的 DOM 结构和气泡触发方式"""
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
log = get_logger("diag_ol_restart")
SS = Path("/tmp/diag_ol_restart")
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

        # 写第一个列表（3项）
        await page.keyboard.press("1")
        await page.keyboard.press(".")
        await page.keyboard.press("Space")
        await page.wait_for_timeout(500)
        await page.keyboard.type("第一项")
        await page.keyboard.press("Enter")
        await page.keyboard.type("第二项")
        await page.keyboard.press("Enter")
        await page.keyboard.type("第三项")
        await page.keyboard.press("Enter")
        await page.keyboard.press("Enter")  # 退出
        await page.wait_for_timeout(300)

        # 写普通段落
        await page.keyboard.type("中间段落")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(200)

        # 开始第二个列表
        await page.keyboard.press("1")
        await page.keyboard.press(".")
        await page.keyboard.press("Space")
        await page.wait_for_timeout(800)
        await shot(page, "after_trigger")

        # 诊断：DOM 中有序列表相关结构
        info = await page.evaluate("""() => {
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return {err: 'no editor'};
            const edRect = ed.getBoundingClientRect();

            // 找所有可能的编号元素
            const results = [];
            for (const el of ed.querySelectorAll('*')) {
                const t = (el.textContent || '').trim();
                if (!/^\d+\.?$/.test(t) || t.length > 4) continue;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                results.push({
                    tag: el.tagName,
                    cls: el.className,
                    text: t,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    edX: Math.round(edRect.x),
                    relX: Math.round(r.x - edRect.x),
                });
            }

            // Slate fiber 中的 ol-item 信息
            const fiberKey = Object.keys(ed).find(k => k.startsWith('__reactInternalInstance'));
            let fiberInfo = [];
            if (fiberKey) {
                function findEditor(node, d) {
                    if (!node || d > 30) return null;
                    if (node.memoizedProps && node.memoizedProps.editor &&
                        node.memoizedProps.editor.marks !== undefined)
                        return node.memoizedProps.editor;
                    return findEditor(node.child, d + 1);
                }
                const editor = findEditor(ed[fiberKey], 0);
                if (editor) {
                    editor.children.forEach((b, i) => {
                        if (b.type && b.type.includes('ol')) {
                            fiberInfo.push({idx: i, type: b.type, start: b.start,
                                           keys: Object.keys(b)});
                        }
                    });
                }
            }

            return {domNumbers: results, fiberOlItems: fiberInfo, edX: Math.round(edRect.x)};
        }""")
        log.info("DOM 编号元素: %s", info.get("domNumbers"))
        log.info("Fiber ol-items: %s", info.get("fiberOlItems"))
        log.info("编辑区 edX: %s", info.get("edX"))

        await shot(page, "final")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
