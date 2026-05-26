#!/usr/bin/env python3
"""
diag_heading_table.py — 验证两件事：
1. /bt2 能否在正文区插入 H2 标题
2. 右键表格单元格能否找到"删除列"的菜单项
"""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page
from joyspace_operator.browser import launch_persistent_context, get_page
from joyspace_operator.document import open_doc, DocumentWriter
from joyspace_operator.utils import get_logger

load_dotenv()
log = get_logger("diag_ht")

DOC_URL = "https://joyspace.jd.com/pages/ypqSBeVkLZCuAicDPt4u"
SS = Path("/tmp/joyspace_screenshots")
SS.mkdir(exist_ok=True)
_step = 0


async def shot(page: Page, label: str) -> None:
    global _step
    _step += 1
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(300)
    p = SS / f"dht_{_step:02d}_{label}.png"
    await page.screenshot(path=str(p), full_page=True)
    log.info("截图 → %s", p.name)


async def main() -> None:
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx)
        await open_doc(page, DOC_URL)

        w = DocumentWriter(page)
        await w.clear()
        await shot(page, "cleared")

        # ── 测试1：标题栏写入（直接点击，不用斜杠）
        log.info("=== 测试1：标题栏写入 ===")
        title_el = await page.evaluate("""() => {
            const el = document.querySelector(
                '.page-title-below [data-slate-node="element"], ' +
                '.page-title-below .slate-editor');
            if (!el) return {found: false};
            const r = el.getBoundingClientRect();
            return {found: true, x: Math.round(r.x + r.width*0.15),
                    y: Math.round(r.y + r.height/2), w: r.width, h: r.height};
        }""")
        log.info("标题栏元素: %s", title_el)
        if title_el.get("found"):
            await page.mouse.click(title_el["x"], title_el["y"])
            await page.wait_for_timeout(300)
            await page.keyboard.type("诊断标题写入测试", delay=12)
            await page.wait_for_timeout(300)
        await shot(page, "title_typed")

        # ── 聚焦正文区
        await w.focus()
        await page.wait_for_timeout(300)

        # ── 测试2：/bt2 能否插入 H2
        log.info("=== 测试2：/bt2 → H2 ===")
        await page.keyboard.type("/bt2", delay=50)
        await page.wait_for_timeout(2000)
        await shot(page, "slash_bt2_menu")

        # 抓取菜单项
        menu_items = await page.evaluate("""() => {
            const items = document.querySelectorAll('.insert-menu-button-item');
            return Array.from(items).map(el => {
                const r = el.getBoundingClientRect();
                const cls = (typeof el.className === 'string') ? el.className : '';
                return {text: (el.textContent||'').trim().slice(0,40),
                        cls: cls.slice(0,60), selected: cls.includes('selected'),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)};
            });
        }""")
        log.info("/bt2 菜单项 (%d 个):", len(menu_items))
        for item in menu_items:
            log.info("  %s", item)

        if menu_items:
            # 点击选中项或第一项
            selected = [i for i in menu_items if i["selected"]]
            target = selected[0] if selected else menu_items[0]
            await page.mouse.click(target["x"] + target["w"]//2,
                                   target["y"] + target["h"]//2, force=True)
            await page.wait_for_timeout(600)
            await page.keyboard.type("这是 bt2 插入的 H2 标题", delay=12)
            await page.keyboard.press("Enter")
        else:
            log.warning("/bt2 菜单未出现，Escape 退出")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        await shot(page, "after_bt2")

        # ── 测试3：/bt3 能否插入 H3
        log.info("=== 测试3：/bt3 → H3 ===")
        await page.keyboard.type("/bt3", delay=50)
        await page.wait_for_timeout(2000)
        menu_items3 = await page.evaluate("""() => {
            const items = document.querySelectorAll('.insert-menu-button-item');
            return Array.from(items).map(el => ({
                text: (el.textContent||'').trim().slice(0,40),
                selected: (el.className||'').includes('selected')
            }));
        }""")
        log.info("/bt3 菜单项: %s", menu_items3)
        if menu_items3:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(600)
            await page.keyboard.type("这是 bt3 插入的 H3 标题", delay=12)
            await page.keyboard.press("Enter")
        else:
            await page.keyboard.press("Escape")
        await shot(page, "after_bt3")

        # ── 测试4：插入 3×3 表格，然后右键第一行第三列，看上下文菜单
        log.info("=== 测试4：表格右键菜单 ===")
        await page.keyboard.type("/table", delay=50)
        await page.wait_for_timeout(1800)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1000)

        try:
            await page.wait_for_selector("table, [data-slate-type='table']", timeout=5000)
        except Exception:
            log.error("表格未出现")
            await ctx.close()
            return

        # 填一行以便能识别
        await page.keyboard.type("列A")
        await page.keyboard.press("Tab")
        await page.keyboard.type("列B")
        await page.keyboard.press("Tab")
        await page.keyboard.type("列C")  # 第三列
        await page.wait_for_timeout(300)
        await shot(page, "table_filled_row1")

        # 找第一行第三列单元格，右键
        cell_coords = await page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content table, .page-main-content [data-slate-type="table"]');
            if (!tbl) return null;
            const firstRow = tbl.querySelector('tr');
            if (!firstRow) return null;
            const cells = firstRow.querySelectorAll('td, th');
            // 第三列
            const cell = cells[2];
            if (!cell) return null;
            const r = cell.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    count: cells.length};
        }""")
        log.info("第一行单元格数 / 第三列坐标: %s", cell_coords)

        if cell_coords:
            # 右键点击第三列第一行
            await page.mouse.click(cell_coords["x"], cell_coords["y"],
                                   button="right")
            await page.wait_for_timeout(1000)
            await shot(page, "table_right_click")

            # 抓取右键菜单
            ctx_menu = await page.evaluate("""() => {
                // 找各种可能的右键菜单
                const selectors = [
                    '.ant-dropdown-menu-item',
                    '.context-menu-item',
                    '[class*="dropdown"] li',
                    '[class*="context"] li',
                    '[role="menuitem"]',
                    '.ant-menu-item',
                ];
                for (const sel of selectors) {
                    const items = document.querySelectorAll(sel);
                    if (items.length > 0) {
                        return {sel, items: Array.from(items).map(el => ({
                            text: (el.textContent||'').trim().slice(0,40),
                            cls: (el.className||'').slice(0,60),
                            x: Math.round(el.getBoundingClientRect().x),
                            y: Math.round(el.getBoundingClientRect().y),
                            w: Math.round(el.getBoundingClientRect().width),
                            h: Math.round(el.getBoundingClientRect().height),
                        }))};
                    }
                }
                return null;
            }""")
            if ctx_menu:
                log.info("右键菜单 (selector=%s, %d项):",
                         ctx_menu["sel"], len(ctx_menu["items"]))
                for item in ctx_menu["items"]:
                    log.info("  %s", item)
            else:
                log.warning("未找到右键菜单")

            # 查找"删除列"选项并点击
            delete_col = await page.evaluate("""() => {
                const all = document.querySelectorAll('[role="menuitem"], li, .ant-dropdown-menu-item');
                for (const el of all) {
                    const txt = (el.textContent||'').trim();
                    if (txt.includes('删除列') || txt.includes('Delete column')) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {text: txt, x: Math.round(r.x + r.width/2),
                                    y: Math.round(r.y + r.height/2)};
                    }
                }
                return null;
            }""")
            log.info("找到'删除列': %s", delete_col)

            if delete_col:
                await page.mouse.click(delete_col["x"], delete_col["y"])
                await page.wait_for_timeout(800)
                await shot(page, "col_deleted")
                log.info("点击'删除列'完成")
            else:
                await page.keyboard.press("Escape")

        await shot(page, "final")
        log.info("诊断完成，截图在 %s", SS)
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
