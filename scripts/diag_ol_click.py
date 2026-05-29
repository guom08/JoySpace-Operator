#!/usr/bin/env python3
"""诊断：点击有序列表编号时为何触发全局搜索框"""
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
log = get_logger("diag_ol_click")
SS = Path("/tmp/diag_ol_click")
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

        # 写一个简单的有序列表（3项）
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
        await page.keyboard.press("Enter")  # 退出列表
        await page.wait_for_timeout(500)

        # 写中间段落
        await page.keyboard.type("中间段落")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(200)

        # 写第二个有序列表的第一项
        await page.keyboard.press("1")
        await page.keyboard.press(".")
        await page.keyboard.press("Space")
        await page.wait_for_timeout(500)
        await page.keyboard.type("新第一项")
        await page.wait_for_timeout(300)

        await shot(page, "before_escape")

        # 按 Escape（不移动光标）
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        await shot(page, "after_escape")

        # 查看所有编号 span 的详细信息
        info = await page.evaluate("""() => {
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return {err: 'no editor'};
            const edRect = ed.getBoundingClientRect();

            // 找所有数字 span
            const all_spans = [...ed.querySelectorAll('span')].map(el => {
                const t = (el.textContent || '').trim();
                if (!/^\d+\.?$/.test(t)) return null;
                const r = el.getBoundingClientRect();
                if (r.width === 0) return null;
                return {
                    text: t,
                    tag: el.tagName,
                    cls: el.className.slice(0, 60),
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    relX: Math.round(r.x - edRect.x),
                    parent: el.parentElement?.tagName + '.' + (el.parentElement?.className || '').slice(0, 40),
                };
            }).filter(Boolean);

            // 编辑区位置
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const scroll = document.querySelector('.page-main-content');
            return {
                spans: all_spans,
                edRect: {x: Math.round(edRect.x), y: Math.round(edRect.y), w: Math.round(edRect.width), h: Math.round(edRect.height)},
                viewport: {w: vw, h: vh},
                scrollTop: scroll ? scroll.scrollTop : 0,
            };
        }""")
        log.info("编辑区: %s", info.get("edRect"))
        log.info("viewport: %s", info.get("viewport"))
        log.info("scrollTop: %s", info.get("scrollTop"))
        for s in info.get("spans", []):
            log.info("SPAN: %s", s)

        # 尝试 scrollIntoView 然后查看坐标
        coords = await page.evaluate("""() => {
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const edRect = ed.getBoundingClientRect();
            const candidates = [...ed.querySelectorAll('span')].filter(el => {
                const t = (el.textContent || '').trim();
                if (!/^\d+\.?$/.test(t)) return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && (r.x - edRect.x) >= -60 && (r.x - edRect.x) < 80;
            });
            if (!candidates.length) return {err: 'no candidates'};
            const last = candidates[candidates.length - 1];
            log_info = {before: {x: last.getBoundingClientRect().x, y: last.getBoundingClientRect().y}};
            last.scrollIntoView({block: 'center'});
            const r = last.getBoundingClientRect();
            log_info.after = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            log_info.cls = last.className.slice(0, 80);
            log_info.parent_cls = (last.parentElement?.className || '').slice(0, 80);
            // 还有什么元素在这个坐标上面？
            const cx = Math.round(r.x + r.width / 2);
            const cy = Math.round(r.y + r.height / 2);
            const top_el = document.elementFromPoint(cx, cy);
            log_info.click_coord = {x: cx, y: cy};
            log_info.element_at_coord = top_el ? (top_el.tagName + '.' + (top_el.className || '').slice(0, 60)) : 'null';
            return log_info;
        }""")
        log.info("ScrollIntoView 结果: %s", coords)

        await shot(page, "after_scroll_into_view")

        # 现在检查 elementFromPoint 确认点击目标
        if coords and "click_coord" in coords:
            cx = coords["click_coord"]["x"]
            cy = coords["click_coord"]["y"]
            log.info("准备点击: (%d, %d), 该坐标元素: %s", cx, cy, coords.get("element_at_coord"))

            # 先 hover 看看
            await page.mouse.move(cx, cy)
            await page.wait_for_timeout(800)
            await shot(page, "after_hover")

            # 检查 hover 后出现了什么
            hover_info = await page.evaluate("""() => {
                // 检查是否有弹出框
                const popups = [...document.querySelectorAll('[class*="popup"], [class*="tooltip"], [class*="bubble"], [class*="dropdown"]')]
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0 && r.y > 0;
                    }).map(el => ({
                        tag: el.tagName,
                        cls: el.className.slice(0, 60),
                        x: Math.round(el.getBoundingClientRect().x),
                        y: Math.round(el.getBoundingClientRect().y),
                        text: (el.textContent || '').slice(0, 100),
                    }));
                return {popups};
            }""")
            log.info("Hover 后弹出层: %s", hover_info)

            # 现在点击
            await page.mouse.click(cx, cy)
            await page.wait_for_timeout(800)
            await shot(page, "after_click")

            # 检查点击后的状态
            click_info = await page.evaluate("""() => {
                const inputs = [...document.querySelectorAll('input')].filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 100 && r.height > 0;
                }).map(el => ({tag: el.tagName, cls: el.className.slice(0, 60), w: Math.round(el.getBoundingClientRect().width), type: el.type}));

                const popups = [...document.querySelectorAll('[class*="popup"], [class*="tooltip"], [class*="bubble"], [class*="list-start"], [class*="number"]')]
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    }).map(el => ({
                        cls: el.className.slice(0, 60),
                        text: (el.textContent || '').slice(0, 100),
                        y: Math.round(el.getBoundingClientRect().y),
                    }));

                return {inputs, popups};
            }""")
            log.info("点击后 inputs: %s", click_info.get("inputs"))
            log.info("点击后 popups: %s", click_info.get("popups"))

            if click_info.get("inputs"):
                await page.keyboard.press("Escape")
                log.warning("触发了搜索框，已 Escape")

        await shot(page, "final")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
