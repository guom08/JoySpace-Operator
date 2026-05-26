"""
writer.py — 向 JoySpace 文档写入各类内容块。

使用前提：页面已通过 navigator.open_doc() 打开，编辑器已就绪。

主要 API：
    writer = DocumentWriter(page)
    await writer.clear()             # 清空文档内容
    await writer.focus()             # 将焦点定位到编辑区
    await writer.heading(2, "标题")
    await writer.paragraph("正文")
    await writer.table([["A","B"],["1","2"]])
    await writer.divider()
    await writer.quote("引用内容")
"""
from __future__ import annotations

from playwright.async_api import Page

from joyspace_operator.utils import get_logger

log = get_logger(__name__)

# 斜杠命令 alias（已验证可用）
_SLASH_ALIAS = {
    "table":   "table",
    "divider": "fgx",
    "quote":   "yy",
    "highlight": "glk",
    "code":    "dmk",
}

# 斜杠菜单图标行索引：T=0, H1=1, H2=2, H3=3, H4=4, H5=5, H6=6
_HEADING_ICON_INDEX = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}


class DocumentWriter:
    """向已打开的 JoySpace 文档写入格式化内容。"""

    def __init__(self, page: Page, type_delay: int = 12):
        self.page = page
        self.type_delay = type_delay  # ms per character

    # ------------------------------------------------------------------ #
    #  公开 API
    # ------------------------------------------------------------------ #

    async def clear(self) -> None:
        """清空文档正文（循环 Cmd+A + Backspace 直到字数为 0）。

        关键：每次循环都先把焦点移到编辑区标题栏或非表格文本区，
        再连续发两次 Cmd+A，才能把表格和文本都选中。
        """
        for _ in range(8):
            wc = await self._word_count()
            has_tbl = await self._has_table()
            if wc == 0 and not has_tbl:
                break
            log.debug("clear 循环: word_count=%d, has_table=%s", wc, has_tbl)
            # 每轮都重新建立焦点：优先点标题栏，其次点非表格文本区
            await self._focus_title_or_body()
            # 连续两次 Cmd+A：第一次选当前块/表格内容，第二次选整个文档
            await self.page.keyboard.press("Meta+a")
            await self.page.wait_for_timeout(200)
            await self.page.keyboard.press("Meta+a")
            await self.page.wait_for_timeout(200)
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(600)
        final_wc = await self._word_count()
        log.debug("文档已清空，字数: %d", final_wc)
        if final_wc != 0:
            log.warning("clear() 未能完全清空，剩余字数: %d", final_wc)

    async def focus(self) -> None:
        """将焦点定位到编辑区。每次开始写入前调用一次。"""
        await self._focus_editor()

    async def heading(self, level: int, text: str) -> None:
        """写入标题（level: 1–6）。斜杠命令 /h1~/h6，必须在空行行首触发。"""
        assert 1 <= level <= 6, "level 支持 1–6"
        await self._ensure_empty_line()
        await self._slash_insert(f"h{level}")
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(400)
        log.debug("H%d: %s", level, text[:50])

    async def paragraph(self, text: str) -> None:
        """写入普通段落（末尾自动 Enter）。"""
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(200)
        log.debug("paragraph: %s", text[:50])

    async def divider(self) -> None:
        """插入分割线。"""
        await self._ensure_empty_line()
        await self._slash_insert("fgx")
        await self.page.wait_for_timeout(300)
        log.debug("divider inserted")

    async def quote(self, text: str) -> None:
        """插入引用块并写入内容。"""
        await self._ensure_empty_line()
        await self._slash_insert("yy")
        await self.page.wait_for_timeout(400)
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        # 跳出引用块
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(200)
        log.debug("quote: %s", text[:50])

    async def table(
        self,
        rows: list[list[str]],
        bold_header_row: bool = True,
        bold_header_col: bool = False,
        full_width: bool = True,
        col_weights: list[float] | None = None,
    ) -> None:
        """插入表格并填充内容，支持全宽、列宽比例、首行/首列加粗。

        Args:
            rows: 二维列表，rows[0] 通常为表头。
            bold_header_row: 首行加粗底色（True）。
            bold_header_col: 首列加粗底色（False）。
            full_width: 表格宽度填满页面宽度（True）。
            col_weights: 各列宽度权重，如 [1, 3, 2] 表示列宽比例 1:3:2。
                         为 None 时按内容自动估算。
        """
        if not rows or not rows[0]:
            return

        n_rows = len(rows)
        n_cols = len(rows[0])

        # ── 1. 确保在空行
        await self._ensure_empty_line()

        # ── 2. 插入表格
        await self._slash_insert("table")
        try:
            await self.page.wait_for_selector(
                "[data-slate-type='table'], table", timeout=5000)
        except Exception:
            log.warning("表格未出现，跳过")
            return

        # ── 3. 检测实际列数（默认 /table 可能是 3 列）
        actual_cols = await self.page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content [data-slate-type="table"]')
                || document.querySelector('.page-main-content table');
            if (!tbl) return 2;
            const firstRow = tbl.querySelector('tr');
            return firstRow ? firstRow.querySelectorAll('td, th').length : 2;
        }""") or n_cols
        log.debug("实际表格列数: %d, 数据列数: %d", actual_cols, n_cols)

        # ── 4. 填充单元格（Tab 移动，适配实际列数）
        for r, row in enumerate(rows):
            # 补齐/截断到实际列数
            padded = (list(row) + [""] * actual_cols)[:actual_cols]
            for c, cell in enumerate(padded):
                await self.page.keyboard.type(cell, delay=self.type_delay)
                if not (r == n_rows - 1 and c == actual_cols - 1):
                    await self.page.keyboard.press("Tab")
                    await self.page.wait_for_timeout(100)

        # ── 4.5 删除多余列（/table 默认3列，数据列数可能更少）
        for _ in range(actual_cols - n_cols):
            deleted = await self._delete_last_col()
            log.debug("删除多余列: %s", "✓" if deleted else "✗")

        # ── 5. 跳出表格
        await self._exit_table()

        # ── 6. 悬停表格 → 触发工具栏 → 操作
        await self._apply_table_toolbar(
            bold_header_row=bold_header_row,
            bold_header_col=bold_header_col,
            full_width=full_width,
        )

        # ── 7. 调整列宽（使用数据列数的权重，忽略多余列）
        weights = col_weights or self._estimate_col_weights(rows)
        await self._set_col_widths(weights)

        # ── 8. 确保光标在表格后的空行（为后续插入做准备）
        await self._focus_doc_end()
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(200)

        log.debug("table %dx%d 完成", n_rows, n_cols)

    # ------------------------------------------------------------------ #
    #  内部工具
    # ------------------------------------------------------------------ #

    async def _word_count(self) -> int:
        return await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            return ed ? (ed.innerText || '').replace(/\\s/g, '').length : -1;
        }""")

    async def _focus_editor(self) -> None:
        """坐标点击编辑区，避免被遮挡层拦截。"""
        coords = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const blocks = ed.querySelectorAll('[data-slate-node="element"]');
            const target = blocks[1] || blocks[0] || ed;
            const r = target.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)

    async def _focus_doc_end(self) -> None:
        """将光标定位到文档最后一个顶层块，并移到行尾。
        只取编辑区直接子节点（不含嵌套的表格行/单元格）。
        """
        coords = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            // 只取顶层直接子块，跳过表格类
            const top = Array.from(ed.children).filter(b =>
                b.dataset && b.dataset.slateNode === 'element' &&
                !b.classList.contains('sl-table-wrap') &&
                !b.querySelector('[data-slate-type="table"]')
            );
            const last = top[top.length - 1];
            if (last) {
                const r = last.getBoundingClientRect();
                if (r.width > 0 && r.height > 0)
                    return {x: Math.round(r.x + r.width/2),
                            y: Math.round(r.y + r.height/2)};
            }
            // 回退：点编辑区表格下方
            const tbl = ed.querySelector('[data-slate-type="table"]')
                       || ed.querySelector('table');
            if (tbl) {
                const tr = tbl.getBoundingClientRect();
                const er = ed.getBoundingClientRect();
                return {x: Math.round(tr.x + tr.width/2),
                        y: Math.round(Math.min(tr.bottom + 30, er.bottom - 10))};
            }
            const er = ed.getBoundingClientRect();
            return {x: Math.round(er.x + er.width/2),
                    y: Math.round(er.bottom - 40)};
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(300)
        await self.page.keyboard.press("End")
        await self.page.wait_for_timeout(100)

    async def _focus_title_or_body(self) -> None:
        """将焦点移到标题栏或正文首个非表格块（clear 专用）。

        策略：
          1. 优先点击标题输入框（.page-title-below input / [data-slate-node] 首块）
          2. 找不到标题就点正文编辑区第一个非表格块的可视区域
          3. 兜底：点编辑区顶部空白处
        焦点落在标题或正文（非表格）区后，Cmd+A×2 才能选中整个文档。
        """
        coords = await self.page.evaluate("""() => {
            // 1. 尝试点标题栏（page-title-below 内的可编辑元素）
            const titleEl = document.querySelector(
                '.page-title-below [data-slate-node="element"], ' +
                '.page-title-below .slate-editor');
            if (titleEl) {
                const r = titleEl.getBoundingClientRect();
                if (r.width > 0 && r.height > 0)
                    return {x: Math.round(r.x + r.width * 0.15),
                            y: Math.round(r.y + r.height / 2),
                            via: 'title'};
            }
            // 2. 正文编辑区第一个非表格顶层直接子块
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (ed) {
                const nonTable = Array.from(ed.children).filter(b =>
                    b.dataset && b.dataset.slateNode === 'element' &&
                    !b.classList.contains('sl-table-wrap') &&
                    !b.querySelector('[data-slate-type="table"]') &&
                    !b.querySelector('table')
                );
                const target = nonTable[0];
                if (target) {
                    const r = target.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: Math.round(r.x + r.width * 0.15),
                                y: Math.round(r.y + r.height / 2),
                                via: 'body'};
                }
                // 3. 兜底：点编辑区顶部
                const er = ed.getBoundingClientRect();
                return {x: Math.round(er.x + er.width * 0.15),
                        y: Math.round(er.y + 30),
                        via: 'editor-top'};
            }
            return null;
        }""")
        if coords:
            log.debug("_focus_title_or_body via=%s (%d,%d)",
                      coords.get("via"), coords["x"], coords["y"])
            await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)

    async def _focus_outside_table(self) -> None:
        """将焦点定位到编辑区中非表格的文本块上（兼容旧调用）。"""
        await self._focus_title_or_body()

    async def _has_table(self) -> bool:
        """检查编辑区是否还有表格。"""
        return await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            return ed ? (
                ed.querySelector('table') !== null ||
                ed.querySelector('[data-slate-type="table"]') !== null
            ) : false;
        }""")

    async def _ensure_empty_line(self) -> None:
        """确保光标在空行行首（块级插入前调用）。
        只检查顶层直接子块，避免误判表格内部单元格为最后一个块。
        """
        is_empty = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return true;
            // 只取顶层直接子块，排除表格包裹
            const top = Array.from(ed.children).filter(b =>
                b.dataset && b.dataset.slateNode === 'element' &&
                !b.classList.contains('sl-table-wrap') &&
                !b.querySelector('[data-slate-type="table"]')
            );
            if (!top.length) return true;
            const last = top[top.length - 1];
            return (last.innerText || '').replace(/[​​ ]/g, '').trim() === '';
        }""")
        if not is_empty:
            await self.page.keyboard.press("End")
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(200)

    async def _slash_insert(self, alias: str) -> None:
        """执行斜杠命令并点击菜单项（对有 alias 的命令）。"""
        await self.page.keyboard.type(f"/{alias}", delay=50)
        await self.page.wait_for_timeout(2000)
        try:
            await self.page.wait_for_selector(".insert-menu-button-item", timeout=4000)
            selected = self.page.locator(".insert-menu-button-item.selected")
            if await selected.count() > 0:
                await selected.first().click(force=True)
            else:
                await self.page.keyboard.press("Enter")
        except Exception:
            await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(1000)

    async def _delete_last_col(self) -> bool:
        """右键点击表格最后一列的第一行单元格，选择「删除列」。"""
        coords = await self.page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content [data-slate-type="table"]')
                || document.querySelector('.page-main-content table');
            if (!tbl) return null;
            const firstRow = tbl.querySelector('tr');
            if (!firstRow) return null;
            const cells = firstRow.querySelectorAll('td, th');
            const last = cells[cells.length - 1];
            if (!last) return null;
            const r = last.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if not coords:
            return False

        await self.page.mouse.click(coords["x"], coords["y"], button="right")
        await self.page.wait_for_timeout(800)

        del_coords = await self.page.evaluate("""() => {
            const all = document.querySelectorAll(
                '[role="menuitem"], .ant-dropdown-menu-item, li');
            for (const el of all) {
                const txt = (el.textContent || '').trim();
                if (txt === '删除列' || txt.includes('Delete column')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: Math.round(r.x + r.width/2),
                                y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")

        if del_coords:
            await self.page.mouse.click(del_coords["x"], del_coords["y"])
            await self.page.wait_for_timeout(600)
            return True
        else:
            log.warning("右键菜单未找到「删除列」，Escape")
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
            return False

    async def _exit_table(self) -> None:
        """跳出表格：先 Escape，再点击表格正下方的位置。"""
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(400)
        # 优先点击表格 wrap 的 nextElementSibling
        moved = await self.page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content [data-slate-type="table"]')
                || document.querySelector('.page-main-content table');
            if (!tbl) return false;
            const wrap = tbl.closest('[data-slate-node="element"]');
            const sib = wrap && wrap.nextElementSibling;
            if (sib) { sib.click(); return true; }
            return false;
        }""")
        if not moved:
            # 点击表格下方 30px（确保在表格外，而不是 ed.bottom 可能落在表格内）
            coords = await self.page.evaluate("""() => {
                const tbl = document.querySelector(
                    '.page-main-content [data-slate-type="table"]')
                    || document.querySelector('.page-main-content table');
                const ed = document.querySelector(
                    '.page-main-content .slate-editor.use-virtual-caret');
                if (!tbl || !ed) return null;
                const tr = tbl.getBoundingClientRect();
                const er = ed.getBoundingClientRect();
                const targetY = Math.min(tr.bottom + 30, er.bottom - 10);
                return {x: Math.round(tr.x + tr.width/2), y: Math.round(targetY)};
            }""")
            if coords:
                await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)

    async def _apply_table_toolbar(
        self,
        bold_header_row: bool,
        bold_header_col: bool,
        full_width: bool,
    ) -> None:
        """Hover 表格触发工具栏，然后点击对应按钮。

        工具栏按钮顺序（`.pop-menu-item.h`）：
          0 → 粗体首行
          1 → 粗体首列
          2 → 自适应列宽（按内容）
          3 → 适应页面宽度
        """
        # 获取表格位置
        tbl_rect = await self.page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content [data-slate-type="table"]')
                || document.querySelector('.page-main-content table');
            if (!tbl) return null;
            const r = tbl.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                cx: Math.round(r.x + r.width/2),
                cy: Math.round(r.y + r.height/2),
            };
        }""")
        if not tbl_rect:
            log.warning("未找到表格，跳过工具栏操作")
            return

        # 从表格上方 60px 处平滑移入，触发工具栏
        await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] - 60)
        await self.page.wait_for_timeout(200)
        await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] + 5)
        await self.page.wait_for_timeout(800)  # 等工具栏出现

        async def click_toolbar_btn(index: int) -> bool:
            coords = await self.page.evaluate(f"""() => {{
                const btns = document.querySelectorAll('.pop-menu-item.h');
                const btn = btns[{index}];
                if (!btn) return null;
                const r = btn.getBoundingClientRect();
                return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
            }}""")
            if coords:
                await self.page.mouse.click(coords["x"], coords["y"])
                await self.page.wait_for_timeout(400)
                return True
            return False

        if bold_header_row:
            ok = await click_toolbar_btn(0)
            log.debug("首行加粗: %s", "✓" if ok else "✗ 按钮未找到")
            # 点击后工具栏可能消失，重新 hover
            await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] - 60)
            await self.page.wait_for_timeout(200)
            await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] + 5)
            await self.page.wait_for_timeout(600)

        if bold_header_col:
            ok = await click_toolbar_btn(1)
            log.debug("首列加粗: %s", "✓" if ok else "✗ 按钮未找到")
            await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] - 60)
            await self.page.wait_for_timeout(200)
            await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] + 5)
            await self.page.wait_for_timeout(600)

        if full_width:
            # 按钮3（index=3）= 适应页面宽度（icon-adaptivewidth）
            ok = await click_toolbar_btn(3)
            log.debug("全宽: %s", "✓" if ok else "✗ 按钮未找到")

        # 点击表格外退出 hover 状态
        await self._exit_table()

    def _estimate_col_weights(self, rows: list[list[str]]) -> list[float]:
        """根据每列最长字符数估算列宽权重（中文算 2，英文算 1）。"""
        if not rows:
            return []
        n_cols = len(rows[0])
        weights: list[float] = []
        for c in range(n_cols):
            max_len = 0
            for row in rows:
                if c < len(row):
                    cell = row[c]
                    # 中文字符算2宽，其余算1
                    w = sum(2 if '一' <= ch <= '鿿' else 1 for ch in cell)
                    max_len = max(max_len, w)
            weights.append(max(max_len, 4))  # 最低 4 宽
        return weights

    async def _set_col_widths(self, weights: list[float]) -> None:
        """按比例设置列宽（hover 表格后拖拽列分隔线）。"""
        if not weights:
            return

        # 获取当前表格位置和总宽度
        tbl_info = await self.page.evaluate("""() => {
            const tbl = document.querySelector(
                '.page-main-content [data-slate-type="table"]')
                || document.querySelector('.page-main-content table');
            if (!tbl) return null;
            const r = tbl.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                cx: Math.round(r.x + r.width/2),
                w: Math.round(r.width),
            };
        }""")
        if not tbl_info or not tbl_info.get("w"):
            return

        total_w = tbl_info["w"]
        total_weight = sum(weights)
        col_pxs = [max(60, round(w * total_w / total_weight)) for w in weights]
        diff = total_w - sum(col_pxs)
        col_pxs[-1] += diff

        log.debug("列宽设置: total=%dpx, cols=%s", total_w, col_pxs)

        # 悬停表格顶部，让 resize dots 出现
        await self.page.mouse.move(tbl_info["cx"], tbl_info["y"] - 40)
        await self.page.wait_for_timeout(200)
        await self.page.mouse.move(tbl_info["cx"], tbl_info["y"] + 5)
        await self.page.wait_for_timeout(600)

        # 拖拽列分隔线
        await self._drag_col_resize(col_pxs, tbl_info["x"])

    async def _drag_col_resize(self, col_pxs: list[int], tbl_left: int = 0) -> None:
        """通过拖拽 sl-table-dot-col 分隔点来触发真实的列宽调整。
        需要在 hover 表格状态下调用（dots 才可见）。
        """
        dots = await self.page.evaluate("""() => {
            const dots = document.querySelectorAll(
                '.page-main-content .sl-table-dot.sl-table-dot-col');
            return Array.from(dots).map(d => {
                const r = d.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            });
        }""")

        if not dots:
            log.debug("未找到列分隔点（需在 hover 状态），跳过拖拽调整")
            return

        cum_x = tbl_left
        for i, px in enumerate(col_pxs[:-1]):  # 最后一列不需要拖
            cum_x += px
            if i < len(dots):
                src_x = dots[i]["x"]
                src_y = dots[i]["y"]
                target_x = cum_x
                if abs(src_x - target_x) > 3:
                    await self.page.mouse.move(src_x, src_y)
                    await self.page.wait_for_timeout(200)
                    await self.page.mouse.down()
                    await self.page.wait_for_timeout(100)
                    await self.page.mouse.move(target_x, src_y, steps=5)
                    await self.page.wait_for_timeout(100)
                    await self.page.mouse.up()
                    await self.page.wait_for_timeout(300)
                    log.debug("拖拽第%d列分隔线: %d → %d px", i, src_x, target_x)
