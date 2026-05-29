#!/usr/bin/env python3
"""诊断：focus() 之后焦点到底在哪，/h2 之后块类型是什么"""
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
log = get_logger("diag_focus")
SS = Path("/tmp/diag_focus")
SS.mkdir(exist_ok=True)
_step = 0
TARGET_URL = "https://joyspace.jd.com/pages/ypqSBeVkLZCuAicDPt4u"

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
        await w.set_title("测试标题")
        await w.focus()
        await shot(page, "after_focus")

        # 检查焦点在哪
        focus_info = await page.evaluate("""() => {
            const active = document.activeElement;
            const sel = window.getSelection();
            return {
                activeTag: active ? active.tagName : 'none',
                activeCls: active ? active.className.slice(0, 80) : '',
                selAnchor: sel && sel.anchorNode ? (sel.anchorNode.nodeType === 3 ? '#text' : sel.anchorNode.nodeName + '.' + (sel.anchorNode.className || '').slice(0, 40)) : 'none',
                selRange: sel ? sel.rangeCount : 0,
            };
        }""")
        log.info("focus 后活动元素: %s", focus_info)

        # 手动输入 /h2 并等待
        await page.keyboard.press("/")
        await page.wait_for_timeout(300)
        await page.keyboard.type("h2")
        await page.wait_for_timeout(800)
        await shot(page, "after_slash_h2_typed")

        # 检查是否有斜杠菜单
        menu_info = await page.evaluate("""() => {
            const menus = [...document.querySelectorAll('[class*="slash"], [class*="menu"], [class*="dropdown"]')]
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 50 && r.height > 20 && r.y > 100;
                }).map(el => ({cls: el.className.slice(0, 60), text: (el.textContent||'').slice(0, 80), y: Math.round(el.getBoundingClientRect().y)}));
            return menus;
        }""")
        log.info("斜杠菜单: %s", menu_info)

        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        await shot(page, "after_enter")

        # 检查当前块类型
        block_info = await page.evaluate("""() => {
            const sel = window.getSelection();
            const active = document.activeElement;
            let slateType = 'unknown';
            if (sel && sel.anchorNode) {
                let node = sel.anchorNode;
                const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
                while (node && node !== ed) {
                    if (node.nodeType === 1 && node.dataset && node.dataset.slateNode === 'element' && node.parentElement === ed) {
                        slateType = node.dataset.slateType || 'no-type';
                        break;
                    }
                    node = node.parentElement;
                }
            }
            return {
                slateType,
                activeTag: active ? active.tagName : 'none',
                activeCls: active ? active.className.slice(0, 80) : '',
            };
        }""")
        log.info("Enter 后块类型: %s", block_info)

        # 写一些文字测试
        await page.keyboard.type("测试标题文字")
        await page.wait_for_timeout(300)
        await shot(page, "after_type")

        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
