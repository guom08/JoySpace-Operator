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

    async def set_page_font(self, font_name: str = "京东朗正体", force: bool = False) -> bool:
        """检查并设置文档字体，若已是目标字体则跳过。

        force=True 跳过检测，直接打开字体面板设置（用于 create_doc 后首次设置）。
        Returns True if font was set or already correct, False if button not found.
        """
        await self.page.wait_for_timeout(500)  # 等页面头部完全渲染

        if not force:
            # 检查是否已设置（按钮显示完整名或缩写，如「京东朗正体」→「朗正」）
            font_fragments = [font_name] + [font_name[i:i+2] for i in range(0, len(font_name)-1)]
            already_js = "(" + " || ".join(
                f"txt.includes('{f}')" for f in font_fragments
            ) + ")"
            already = await self.page.evaluate(f"""() => {{
                for (const el of document.querySelectorAll('*')) {{
                    const txt = (el.textContent || '').trim();
                    if (!({already_js})) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.y >= 0 && r.y < 200) return true;
                }}
                return false;
            }}""")
            if already:
                log.info("字体已是「%s」，跳过", font_name)
                return True

        # 找字体按钮：文字为「字体」或当前任意字体名（y < 200px）
        btn = await self.page.evaluate("""() => {
            for (const el of document.querySelectorAll('button,[role="button"],span,div')) {
                const txt = (el.textContent || '').trim();
                if (txt !== '字体' && !['宋体','微软雅黑','黑体','楷体','仿宋',
                    '方正', 'PingFang', 'Arial', 'Helvetica', 'Times'].some(f => txt.includes(f)))
                    continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < 200)
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
            // 兜底：找所有 y<200 可点击元素里文字最短的那个（字体按钮通常标签很短）
            const candidates = [];
            for (const el of document.querySelectorAll('button,[role="button"]')) {
                const txt = (el.textContent || '').trim();
                if (!txt || txt.length > 15) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < 200)
                    candidates.push({txt, x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
            }
            return candidates.length ? candidates[0] : null;
        }""")
        if not btn:
            log.warning("未找到字体按钮，跳过字体设置")
            return False

        log.info("点击字体按钮 (%d,%d)", btn["x"], btn["y"])
        await self.page.mouse.click(btn["x"], btn["y"])
        await self.page.wait_for_timeout(1000)  # 等下拉列表渲染

        # 在弹出列表中找目标字体（用 includes 而非 === 防止子元素干扰）
        result = await self.page.evaluate(f"""() => {{
            const target = '{font_name}';
            const found = [];
            for (const el of document.querySelectorAll('[role="option"],[role="menuitem"],li')) {{
                const txt = (el.textContent || '').trim();
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < window.innerHeight)
                    found.push(txt);
                if (txt.includes(target) && r.width > 0 && r.y >= 0 && r.y < window.innerHeight)
                    return {{ok: true, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), txt}};
            }}
            // 也搜 div（有些下拉用 div 渲染）
            for (const el of document.querySelectorAll('div')) {{
                const txt = (el.textContent || '').trim();
                if (!txt.includes(target) || txt.length > target.length + 5) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.y >= 0 && r.y < window.innerHeight)
                    return {{ok: true, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), txt}};
            }}
            return {{ok: false, candidates: found.slice(0, 20)}};
        }}""")
        if not result.get("ok"):
            log.warning("字体列表中未找到「%s」，候选: %s", font_name, result.get("candidates", []))
            await self.page.keyboard.press("Escape")
            return False
        opt = result

        await self.page.mouse.click(opt["x"], opt["y"])
        await self.page.wait_for_timeout(500)
        log.info("字体已设置为「%s」", font_name)
        return True

    async def clear(self) -> None:
        """清空文档正文（循环：建立焦点 → Cmd+A × 2 → Backspace，直到字数为 0）。

        注意：_word_count 已排除 sl-list-prefix（列表编号），所以文字全删完后
        循环会正常退出。退出后再检查是否还有空列表项（只剩编号前缀），
        若有则直接 Backspace 逐一消掉。
        """
        await self._scroll_container_to_top()
        await self.page.wait_for_timeout(400)
        for _ in range(10):
            wc = await self._word_count()
            has_tbl = await self._has_table()
            if wc == 0 and not has_tbl:
                break
            log.debug("clear 循环: word_count=%d, has_table=%s", wc, has_tbl)
            await self._focus_title_or_body()
            await self.page.keyboard.press("ControlOrMeta+a")
            await self.page.wait_for_timeout(150)
            await self.page.keyboard.press("ControlOrMeta+a")
            await self.page.wait_for_timeout(300)
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(600)

        # 处理残留的空列表项（有序/无序列表的空行，只剩编号前缀，无文字内容）。
        # Cmd+A+Backspace 无法删掉这类行，直接 Backspace 逐一消除。
        for _ in range(20):
            has_empty_list = await self.page.evaluate("""() => {
                const ed = document.querySelector(
                    '.page-main-content .slate-editor.use-virtual-caret');
                if (!ed) return false;
                return ed.querySelectorAll('.sl-list-prefix').length > 0;
            }""")
            if not has_empty_list:
                break
            await self._focus_title_or_body()
            await self.page.keyboard.press("ControlOrMeta+End")
            await self.page.wait_for_timeout(150)
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(300)

        await self._scroll_container_to_top()
        await self.page.wait_for_timeout(200)
        final_wc = await self._word_count()
        log.debug("文档已清空，字数: %d", final_wc)
        if final_wc != 0:
            log.warning("clear() 未能完全清空，剩余字数: %d", final_wc)

    async def set_title(self, title: str = "") -> None:
        """设置文档标题栏。

        传空字符串时清空标题。每次写新文档前应先调用此方法，避免残留旧标题。

        JoySpace 有两种标题结构：
        1. 独立 contenteditable input（已有内容的旧文档）
        2. Slate 内嵌首行标题（show-title 模式，新建空文档）
        两种都能处理。
        """
        # 路径 A：找独立的 contenteditable 标题输入框
        coords = await self.page.evaluate("""() => {
            const selectors = [
                '.page-title-content [contenteditable]',
                '.sl-title [contenteditable]',
                '[data-testid="page-title"] [contenteditable]',
                '.page-title [contenteditable]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {x: Math.round(r.x + 20), y: Math.round(r.y + r.height / 2), via: 'selector'};
                }
            }
            // 兜底：找页面顶部区域内 contenteditable 且不在 .slate-editor 内的元素
            for (const el of document.querySelectorAll('[contenteditable]')) {
                if (el.closest('.slate-editor')) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < 300)
                    return {x: Math.round(r.x + 20), y: Math.round(r.y + r.height / 2), via: 'fallback'};
            }
            return null;
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(300)
            await self.page.keyboard.press("ControlOrMeta+a")
            await self.page.wait_for_timeout(100)
            if title:
                await self.page.keyboard.type(title, delay=self.type_delay)
            else:
                await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(300)
            log.debug("set_title (independent input): %r", title[:50] if title else "(cleared)")
            return

        # 路径 B：show-title 模式 — Slate 第一个块就是标题行
        # 点击 Slate 编辑区第一个段落块，全选后替换
        title_coords = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const container = ed.closest('.sl-editor-container');
            if (!container || !container.classList.contains('show-title')) return null;
            // 第一个子块就是标题行
            const first = ed.children[0];
            if (!first) return null;
            const r = first.getBoundingClientRect();
            if (r.width > 0)
                return {x: Math.round(r.x + 40), y: Math.round(r.y + Math.max(r.height / 2, 10))};
            return null;
        }""")
        if title_coords:
            await self.page.mouse.click(title_coords["x"], title_coords["y"])
            await self.page.wait_for_timeout(300)
            await self.page.keyboard.press("ControlOrMeta+a")
            await self.page.wait_for_timeout(100)
            if title:
                await self.page.keyboard.type(title, delay=self.type_delay)
            else:
                await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(300)
            log.debug("set_title (show-title slate): %r", title[:50] if title else "(cleared)")
            return

        log.warning("set_title: 未找到标题栏，跳过")

    async def focus(self) -> None:
        """将焦点定位到编辑区。每次开始写入前调用一次。"""
        await self._focus_editor()
        # JS focus 确保 virtual-caret-input 激活，坐标点击有时落在非交互区
        await self._refocus_virtual_caret()

    async def heading(self, level: int, text: str) -> None:
        """写入标题（level: 1–6）via 斜杠命令 /h1~/h6。"""
        assert 1 <= level <= 6, "level 支持 1–6"
        await self._ensure_empty_line()
        await self._slash_insert(f"h{level}")
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(400)
        log.debug("H%d: %s", level, text[:50])

    async def paragraph(self, text: str) -> None:
        """写入普通段落（末尾自动 Enter）。"""
        if await self._is_cursor_in_list():
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(200)
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(200)
        log.debug("paragraph: %s", text[:50])

    async def divider(self) -> None:
        """插入分割线。"""
        await self._ensure_empty_line()
        await self._slash_insert("fgx")
        await self.page.wait_for_timeout(600)  # 等分割线和后续空行完全渲染
        # 分割线插入后光标处于虚悬状态，点击分割线之后的最后一个空行（非 _focus_editor，
        # 后者会滚到顶部找错误位置）
        await self._focus_after_divider()
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

    async def bullet_list(self, items: list, indent: int = 0) -> None:
        """写入无序列表。

        items 支持两种格式：
          - str：单条 bullet，用 indent 指定层级（0=一级，1=二级，…）
          - dict：{"text": "...", "indent": N} 逐条指定层级

        原理：在空行行首输入 "* " + 空格触发无序列表，
        然后用 Tab 推进层级，Enter 换行继续，最后 Enter+Backspace 退出列表。

        注意：连续两次 Enter 会退出列表，所以每条 item 只按一次 Enter。
        """
        await self._ensure_empty_line()

        for i, item in enumerate(items):
            if isinstance(item, dict):
                text = item.get("text", "")
                lvl = item.get("indent", 0)
            else:
                text = str(item)
                lvl = indent

            if i == 0:
                # "* " 触发无序列表（逐键确保 markdown 转换可靠）
                await self.page.keyboard.press("Home")
                await self.page.wait_for_timeout(100)
                await self.page.keyboard.press("*")
                await self.page.wait_for_timeout(60)
                await self.page.keyboard.press("Space")
                await self.page.wait_for_timeout(500)  # 等 markdown 转换
                # 推进层级
                for _ in range(lvl):
                    await self.page.keyboard.press("Tab")
                    await self.page.wait_for_timeout(100)
                await self.page.keyboard.type(text, delay=self.type_delay)
            else:
                # 后续行：Enter 换行（JoySpace 自动延续 bullet）
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(200)

                # 检查并调整层级
                cur_lvl = await self._get_current_list_indent()
                target_lvl = lvl
                if target_lvl > cur_lvl:
                    for _ in range(target_lvl - cur_lvl):
                        await self.page.keyboard.press("Tab")
                        await self.page.wait_for_timeout(100)
                elif target_lvl < cur_lvl:
                    for _ in range(cur_lvl - target_lvl):
                        await self.page.keyboard.press("Shift+Tab")
                        await self.page.wait_for_timeout(100)

                await self.page.keyboard.type(text, delay=self.type_delay)

            await self.page.wait_for_timeout(150)

        # 退出列表：按 Enter 产生空 bullet，再按 Backspace 撤销 bullet 变成普通空行
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        # 检查是否还在列表中，若是则 Backspace 退出
        still_in_list = await self._is_cursor_in_list()
        if still_in_list:
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(200)
        log.debug("bullet_list: %d items", len(items))

    async def ordered_list(self, items: list, restart: bool = False) -> None:
        """写入有序列表。

        items: str 列表，每项一行。
        restart: 若当前编号不从 1 开始（接续上一个有序列表），自动点击编号弹出框
                 将起始编号改为 1 并确定。

        原理：
        - 输入 "1. " 触发有序列表
        - 每项 Enter 换行（JoySpace 自动递增编号）
        - 最后一项后 Enter，再 Enter（空行不输文字）自动撤销多余编号并退出列表
        - 若 restart=True 且检测到编号不从 1 起，点击编号弹出框改为 1 后确定
        """
        await self._ensure_empty_line()

        # "1." + 空格 触发有序列表（逐键确保 markdown 触发可靠）
        await self.page.keyboard.press("Home")
        await self.page.wait_for_timeout(100)
        await self.page.keyboard.press("1")
        await self.page.wait_for_timeout(60)
        await self.page.keyboard.press(".")
        await self.page.wait_for_timeout(60)
        await self.page.keyboard.press("Space")
        await self.page.wait_for_timeout(500)  # 等 markdown 转换

        # 若需要重置编号（接续上一个列表时会从上个列表末尾+1开始）
        if restart:
            await self._ensure_ordered_list_starts_at_one()
            # 点击弹出框后焦点会离开 Slate，需重新激活 virtual-caret-input
            await self._refocus_virtual_caret()
            await self.page.wait_for_timeout(200)

        for i, item in enumerate(items):
            if i > 0:
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(200)
            await self.page.keyboard.type(str(item), delay=self.type_delay)
            await self.page.wait_for_timeout(150)

        # 退出：Enter 一次（产生下一个编号行），再 Enter（空行自动撤销编号）
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        log.debug("ordered_list: %d items", len(items))

    async def todo_list(self, items: list) -> None:
        """写入代办列表（checkbox）。

        items: str 列表，每项一行。

        原理：输入 "[] " 触发代办块，Enter 换行自动延续，
        最后 Enter（空行）自动撤销并退出。
        """
        await self._ensure_empty_line()

        # "[]" + 空格 触发代办（逐键确保 markdown 转换可靠）
        await self.page.keyboard.press("Home")
        await self.page.wait_for_timeout(100)
        await self.page.keyboard.press("[")
        await self.page.wait_for_timeout(60)
        await self.page.keyboard.press("]")
        await self.page.wait_for_timeout(60)
        await self.page.keyboard.press("Space")
        await self.page.wait_for_timeout(500)  # 等 markdown 转换

        for i, item in enumerate(items):
            if i > 0:
                await self.page.keyboard.press("Enter")
                await self.page.wait_for_timeout(200)
            await self.page.keyboard.type(str(item), delay=self.type_delay)
            await self.page.wait_for_timeout(150)

        # 退出：空行 + Enter 撤销
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        log.debug("todo_list: %d items", len(items))

    async def quote_block(self, text: str) -> None:
        """插入引用块并写入内容。

        原理：输入 "> " 触发引用块，写完后 Enter + Enter 退出。
        （与 quote() 方法等价，提供更直观的名字；底层相同。）
        """
        await self._ensure_empty_line()
        await self.page.keyboard.press("Home")
        await self.page.wait_for_timeout(100)
        await self.page.keyboard.press(">")
        await self.page.wait_for_timeout(60)
        await self.page.keyboard.press("Space")
        await self.page.wait_for_timeout(500)  # 等 markdown 转换
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(200)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(300)
        log.debug("quote_block: %s", text[:50])

    async def bold_inline(self, text: str) -> None:
        """在当前光标位置输入加粗文字（行内，不换行）。

        原理：输入文字 → 鼠标拖拽选中 → 点击浮动工具条 Bold 按钮 → 重置 marks。
        """
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.wait_for_timeout(300)
        await self._select_last_typed(len(text))
        await self.page.wait_for_timeout(200)
        ok = await self._click_inline_toolbar_button("Bold")
        if not ok:
            log.warning("bold_inline: 未找到 Bold 按钮")
        await self._reset_slate_marks()
        # 浮动工具条点击后 DOM 焦点离开虚拟输入框，需恢复
        await self.page.evaluate("""() => {
            const ta = document.querySelector('.ant-input.virtual-caret-input');
            if (ta) ta.focus();
        }""")
        await self.page.wait_for_timeout(100)
        log.debug("bold_inline: %s", text[:40])

    async def colored_inline(self, text: str, color: str = "#F5222D") -> None:
        """在当前光标位置输入指定颜色的文字（行内，不换行）。

        color: 十六进制颜色值，支持:
            #232930 (默认黑)  #999999 (灰)   #F5222D (红)
            #CF6F00 (棕橙)    #E5A001 (黄)   #2EA121 (绿)
            #4C7CFF (蓝)      #7437DD (紫)   #fff (白)
        """
        await self.page.keyboard.type(text, delay=self.type_delay)
        await self.page.wait_for_timeout(300)
        await self._select_last_typed(len(text))
        await self.page.wait_for_timeout(200)
        ok = await self._apply_font_color(color)
        if not ok:
            log.warning("colored_inline: 未能应用颜色 %s", color)
        await self._reset_slate_marks()
        # 颜色面板点击后 DOM 焦点离开虚拟输入框，需恢复以保证后续键盘事件进入编辑器
        await self.page.evaluate("""() => {
            const ta = document.querySelector('.ant-input.virtual-caret-input');
            if (ta) ta.focus();
        }""")
        await self.page.wait_for_timeout(100)
        log.debug("colored_inline: %s color=%s", text[:40], color)

    async def highlight(self, content: str) -> None:
        """插入高亮块并写入内容。

        策略顺序：
        1. 斜杠命令 /ga（主路径，最稳定）
        2. 若斜杠命令后高亮块未出现，回退到 Slate fiber insert_node
        写入内容后，通过 fiber set_selection + DOM 点击退出高亮块。
        """
        await self._ensure_empty_line()

        # ── 1. 主路径：斜杠命令 /ga
        await self._slash_insert("ga")
        await self.page.wait_for_timeout(800)

        hl_coords = await self._get_highlight_block_coords()

        if not hl_coords:
            # ── 2. 回退：Slate fiber insert_node
            log.warning("highlight: /ga 未产生高亮块，改用 fiber 插入")
            await self.page.evaluate("""() => {
                var ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
                if (!ed) return {err: 'no ed'};
                var fiberKey = Object.keys(ed).find(function(k) {
                    return k.startsWith('__reactInternalInstance');
                });
                if (!fiberKey) return {err: 'no fiber'};
                function findOuterEditor(node, d) {
                    if (!node || d > 60) return null;
                    if (node.memoizedProps && node.memoizedProps.editor) {
                        var e = node.memoizedProps.editor;
                        if (e.children && e.marks !== undefined) return e;
                    }
                    return findOuterEditor(node.return, d + 1);
                }
                var editor = findOuterEditor(ed[fiberKey], 0);
                if (!editor) return {err: 'no editor'};
                var sel = editor.selection;
                var insertIdx = sel ? (sel.anchor.path[0] + 1) : editor.children.length;
                try {
                    var ts = Date.now();
                    var hlNode = {
                        type: 'highlight-block', id: 'hl_' + ts,
                        bgColor: '#FEF3F3', emoji: '👉', borderColor: '#F88E8B',
                        children: [{type: 'p', id: 'hlp_' + ts, children: [{text: ''}]}]
                    };
                    editor.apply({type: 'insert_node', path: [insertIdx], node: hlNode});
                    editor.apply({
                        type: 'set_selection',
                        properties: editor.selection,
                        newProperties: {
                            anchor: {path: [insertIdx, 0, 0], offset: 0},
                            focus:  {path: [insertIdx, 0, 0], offset: 0}
                        }
                    });
                    editor.marks = {};
                    return {ok: true};
                } catch(e) { return {err: e.message}; }
            }""")
            await self.page.wait_for_timeout(800)
            hl_coords = await self._get_highlight_block_coords()

        # ── 3. 点击高亮块内部，确保焦点在块内
        if hl_coords:
            await self.page.mouse.click(hl_coords["x"], hl_coords["y"])
            await self.page.wait_for_timeout(400)
            # 再次确认焦点在高亮块内（通过检查光标所在 DOM 节点）
            in_block = await self._is_cursor_in_highlight_block()
            if not in_block:
                log.warning("highlight: 点击后光标不在高亮块内，再试一次")
                await self.page.mouse.click(hl_coords["x"], hl_coords["y"])
                await self.page.wait_for_timeout(400)
        else:
            log.warning("highlight: 无法找到高亮块 DOM，内容写到当前光标处")

        # ── 4. 写内容
        await self.page.keyboard.type(content, delay=self.type_delay)
        await self.page.wait_for_timeout(400)

        # ── 5. 验证内容写入了高亮块（而不是落到块外）
        wrote_in_block = await self._is_cursor_in_highlight_block()
        if not wrote_in_block:
            log.warning("highlight: 内容可能未写入高亮块（光标已在块外）")

        # ── 6. 退出高亮块
        exited = await self._exit_highlight_block()
        if not exited:
            # 最终回退：点击高亮块下方区域
            log.warning("highlight: fiber exit 失败，尝试点击块外")
            await self._click_below_highlight_block()
        log.debug("highlight: %s", content[:50])

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

        # ── 2. 把光标所在行滚入视口，斜杠菜单才能出现在屏幕内
        await self.page.evaluate("""() => {
            const sel = window.getSelection();
            if (sel && sel.anchorNode) {
                const node = sel.anchorNode.nodeType === 1
                    ? sel.anchorNode : sel.anchorNode.parentElement;
                if (node) node.scrollIntoView({block: 'center'});
            }
        }""")
        await self.page.wait_for_timeout(300)

        # ── 3. 插入表格（失败时重试一次）
        for attempt in range(2):
            await self._slash_insert("table")
            try:
                await self.page.wait_for_selector(
                    "[data-slate-type='table'], table", timeout=5000)
                break
            except Exception:
                if attempt == 0:
                    log.warning("表格未出现，重试一次")
                    await self._scroll_cursor_into_view()
                    await self.page.wait_for_timeout(500)
                else:
                    log.warning("表格未出现，跳过")
                    return

        # ── 3. 调整表格到目标行列数（默认 3×3，用右键菜单增删行/列）
        await self._adjust_table_dimensions(n_rows, n_cols)

        # ── 4. 移到第一格（左上角），从头开始填
        await self._goto_first_cell()

        # ── 5. 填充单元格（Tab 移动）
        for r, row in enumerate(rows):
            padded = (list(row) + [""] * n_cols)[:n_cols]
            for c, cell in enumerate(padded):
                await self.page.keyboard.type(cell, delay=self.type_delay)
                if not (r == n_rows - 1 and c == n_cols - 1):
                    await self.page.keyboard.press("Tab")
                    await self.page.wait_for_timeout(100)

        # ── 6. 先调整列宽比例（在固定宽表格上拖分隔线），再 full_width 展开
        weights = col_weights or self._estimate_col_weights(rows)
        await self._set_col_widths(weights)

        # ── 7. 悬停表格 → 触发工具栏 → full_width / 首行加粗
        await self._apply_table_toolbar(
            bold_header_row=bold_header_row,
            bold_header_col=bold_header_col,
            full_width=full_width,
        )

        # ── 8. 焦点移到表格后，并验证确实跳出（最多重试3次）
        await self._focus_after_table()
        # 注意：不再多按 Enter，_focus_after_table 已落到后续空行，
        # 额外 Enter 会产生一个多余空行。

        for attempt in range(3):
            if not await self._is_cursor_in_table():
                break
            log.warning("table(): 光标仍在表格内，第%d次强制跳出", attempt + 1)
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
            await self._force_focus_below_table()
            await self.page.wait_for_timeout(300)
        else:
            log.error("table(): 3次重试后光标仍在表格内，后续写入可能错位")

        log.debug("table %dx%d 完成", n_rows, n_cols)

    # ------------------------------------------------------------------ #
    #  内部工具
    # ------------------------------------------------------------------ #

    async def _word_count(self) -> int:
        return await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return -1;
            // 克隆节点，移除 sl-list-prefix（有序/无序列表前缀），再取 innerText
            const clone = ed.cloneNode(true);
            for (const el of clone.querySelectorAll('.sl-list-prefix')) el.remove();
            return (clone.innerText || '').replace(/\\s/g, '').length;
        }""")

    async def _exit_highlight_block(self) -> bool:
        """将光标移出高亮块：通过 Slate fiber 直接跳到后续段落，失败则点击块外。

        高亮块对 Enter×2 / Tab / Escape / ArrowDown 均无反应，
        唯一可靠出口是操作 Slate 内部选区或点击块外的 DOM 元素。
        """
        # 策略1：通过 Slate editor.apply 直接将光标移到高亮块之后的位置
        moved = await self.page.evaluate("""() => {
            var ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            var fiberKey = Object.keys(ed).find(function(k) {
                return k.startsWith('__reactInternalInstance');
            });
            if (!fiberKey) return false;
            // 向上找包含 highlight-block 的外层 editor
            function findOuterEditor(node, d) {
                if (!node || d > 60) return null;
                if (node.memoizedProps && node.memoizedProps.editor) {
                    var e = node.memoizedProps.editor;
                    if (e.children && e.marks !== undefined &&
                        e.children.some(function(c) { return c.type === 'highlight-block'; }))
                        return e;
                }
                return findOuterEditor(node.return, d + 1);
            }
            var editor = findOuterEditor(ed[fiberKey], 0);
            if (!editor || !editor.children) return false;
            // 找高亮块（type='highlight-block'）在顶层 children 中最后一个的索引
            var hlIdx = -1;
            for (var i = editor.children.length - 1; i >= 0; i--) {
                var node = editor.children[i];
                if (node.type === 'highlight-block') {
                    hlIdx = i;
                    break;
                }
            }
            if (hlIdx === -1) return false;
            // 目标：高亮块之后的第一个节点的开头
            var targetIdx = hlIdx + 1;
            if (targetIdx >= editor.children.length) return false;
            try {
                editor.apply({
                    type: 'set_selection',
                    properties: editor.selection,
                    newProperties: {
                        anchor: {path: [targetIdx, 0], offset: 0},
                        focus:  {path: [targetIdx, 0], offset: 0}
                    }
                });
                editor.marks = {};
                return {ok: true, targetIdx: targetIdx};
            } catch(e) { return false; }
        }""")

        if moved and isinstance(moved, dict) and moved.get("ok"):
            await self.page.wait_for_timeout(300)
            # 点击目标段落激活 DOM focus
            await self._click_slate_path_node(moved.get("targetIdx", 0))
            log.debug("_exit_highlight_block: via Slate fiber targetIdx=%s",
                      moved.get("targetIdx"))
            return True

        # 策略1b：高亮块是最后节点，在其后插入新空段落
        inserted = await self.page.evaluate("""() => {
            var ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            var fiberKey = Object.keys(ed).find(function(k) {
                return k.startsWith('__reactInternalInstance');
            });
            if (!fiberKey) return false;
            // 向上找包含 highlight-block 的外层 editor
            function findOuterEditor(node, d) {
                if (!node || d > 60) return null;
                if (node.memoizedProps && node.memoizedProps.editor) {
                    var e = node.memoizedProps.editor;
                    if (e.children && e.marks !== undefined &&
                        e.children.some(function(c) { return c.type === 'highlight-block'; }))
                        return e;
                }
                return findOuterEditor(node.return, d + 1);
            }
            var editor = findOuterEditor(ed[fiberKey], 0);
            if (!editor || !editor.children) return false;
            var hlIdx = -1;
            for (var i = editor.children.length - 1; i >= 0; i--) {
                if (editor.children[i].type === 'highlight-block') {
                    hlIdx = i;
                    break;
                }
            }
            if (hlIdx === -1) return false;
            var targetIdx = hlIdx + 1;
            try {
                var newNode = {type: 'p', children: [{text: ''}]};
                editor.apply({type: 'insert_node', path: [targetIdx], node: newNode});
                editor.apply({
                    type: 'set_selection',
                    properties: editor.selection,
                    newProperties: {
                        anchor: {path: [targetIdx, 0], offset: 0},
                        focus:  {path: [targetIdx, 0], offset: 0}
                    }
                });
                editor.marks = {};
                return {ok: true, targetIdx: targetIdx};
            } catch(e) { return {error: e.message}; }
        }""")

        if inserted and isinstance(inserted, dict) and inserted.get("ok"):
            await self.page.wait_for_timeout(400)
            await self._click_slate_path_node(inserted["targetIdx"])
            log.debug("_exit_highlight_block: inserted new paragraph targetIdx=%s",
                      inserted.get("targetIdx"))
            return True

        log.warning("_exit_highlight_block fiber insert failed: %s", inserted)

        # 策略2：找高亮块在 editor 顶层 children 中的位置，点击其后的第一个兄弟
        coords = await self.page.evaluate("""() => {
            var ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            var children = Array.from(ed.children);
            var hlIdx = -1;
            for (var i = children.length - 1; i >= 0; i--) {
                if (children[i].classList.contains('sl-highlight-block')) {
                    hlIdx = i;
                    break;
                }
            }
            if (hlIdx === -1) return null;

            for (var j = hlIdx + 1; j < children.length; j++) {
                var b = children[j];
                var r = b.getBoundingClientRect();
                if (r.width > 0 && r.height > 4) {
                    if (r.y < 0 || r.y + r.height > window.innerHeight) {
                        b.scrollIntoView({block: 'nearest'});
                        r = b.getBoundingClientRect();
                    }
                    return {x: Math.round(r.x + r.width * 0.3),
                            y: Math.round(r.y + Math.max(r.height / 2, 8)),
                            via: 'next-sibling'};
                }
            }

            // 没有后继兄弟：点击高亮块视口底部正下方
            var hl = children[hlIdx];
            hl.scrollIntoView({block: 'start'});
            var hlR = hl.getBoundingClientRect();
            var edR = ed.getBoundingClientRect();
            if (hlR.bottom + 40 > window.innerHeight) {
                var scEl = ed.parentElement;
                while (scEl && scEl !== document.documentElement) {
                    var ss = window.getComputedStyle(scEl);
                    if (['scroll','auto'].includes(ss.overflow) ||
                        ['scroll','auto'].includes(ss.overflowY)) {
                        scEl.scrollTop += (hlR.bottom + 40 - window.innerHeight);
                        break;
                    }
                    scEl = scEl.parentElement;
                }
                hlR = hl.getBoundingClientRect();
            }
            if (hlR.bottom + 10 < window.innerHeight) {
                return {x: Math.round(edR.x + edR.width * 0.3),
                        y: Math.round(hlR.bottom + 10),
                        via: 'below-last-hl'};
            }
            return null;
        }""")

        if not coords:
            log.warning("_exit_highlight_block: 找不到可点击位置")
            return False

        log.debug("_exit_highlight_block via=%s at (%d,%d)",
                  coords.get("via"), coords["x"], coords["y"])
        await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)
        return True

    async def _click_slate_path_node(self, top_idx: int) -> None:
        """点击 Slate 顶层 children[top_idx] 对应的 DOM 元素，同步 DOM focus。"""
        coords = await self.page.evaluate(f"""() => {{
            var ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            var children = Array.from(ed.children);
            var b = children[{top_idx}];
            if (!b) return null;
            var r = b.getBoundingClientRect();
            if (r.width > 0) {{
                if (r.y < 0 || r.y > window.innerHeight) {{
                    b.scrollIntoView({{block: 'nearest'}});
                    r = b.getBoundingClientRect();
                }}
                return {{x: Math.round(r.x + r.width * 0.3),
                         y: Math.round(r.y + Math.max(r.height / 2, 8))}};
            }}
            return null;
        }}""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(300)

    async def _focus_after_divider(self) -> None:
        """分割线插入后，将光标定位到分割线之后的第一个段落。

        策略：
        1. 如果 divider 后已有段落，通过 fiber set_selection 移过去。
        2. 如果 divider 是最后节点，通过 fiber insertNodes 在后面插入空段落，再移过去。
           （不依赖键盘 ArrowDown，因为 selection 停在 divider 时键盘无效。）
        3. 最终兜底：点击 divider DOM 元素下方。
        """
        moved = await self.page.evaluate("""() => {
            var ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return {error: 'no editor'};
            var fiberKey = Object.keys(ed).find(function(k) {
                return k.startsWith('__reactInternalInstance');
            });
            if (!fiberKey) return {error: 'no fiber key'};
            function findEditor(node, d) {
                if (!node || d > 30) return null;
                if (node.memoizedProps && node.memoizedProps.editor &&
                    node.memoizedProps.editor.marks !== undefined)
                    return node.memoizedProps.editor;
                return findEditor(node.child, d + 1);
            }
            var editor = findEditor(ed[fiberKey], 0);
            if (!editor || !editor.children) return {error: 'no editor in fiber'};

            // 找最后一个 type='divider' 节点
            var divIdx = -1;
            for (var i = editor.children.length - 1; i >= 0; i--) {
                if (editor.children[i].type === 'divider') { divIdx = i; break; }
            }
            if (divIdx === -1) return {error: 'no divider found'};

            var targetIdx = divIdx + 1;

            // 情况 A：divider 后已有段落，直接 set_selection
            if (targetIdx < editor.children.length) {
                try {
                    editor.apply({
                        type: 'set_selection',
                        properties: editor.selection,
                        newProperties: {
                            anchor: {path: [targetIdx, 0], offset: 0},
                            focus:  {path: [targetIdx, 0], offset: 0}
                        }
                    });
                    editor.marks = {};
                    return {ok: true, targetIdx: targetIdx, existed: true};
                } catch(e) { return {error: 'set_selection A: ' + e.message}; }
            }

            // 情况 B：divider 是最后节点，用 insertNodes 在后面插入空段落
            // 先把 selection 移到 divider，然后 insertNodes
            try {
                editor.apply({
                    type: 'set_selection',
                    properties: editor.selection,
                    newProperties: {
                        anchor: {path: [divIdx, 0], offset: 0},
                        focus:  {path: [divIdx, 0], offset: 0}
                    }
                });
            } catch(e) { return {error: 'set_selection B pre: ' + e.message}; }

            // insertNodes 在 divider 之后
            // 生成 JoySpace 格式的 6 字符 base62 id（避免 tmp_ 前缀被 JoySpace 斜杠菜单拒绝）
            var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-';
            var newId = Array.from({length: 6}, () => chars[Math.floor(Math.random() * chars.length)]).join('');
            var newParagraph = {type: 'p', id: newId, children: [{text: ''}]};

            // 优先用高层 API editor.insertNode（会触发 JoySpace 内部节点注册）
            var inserted = false;
            if (editor.insertNode) {
                try {
                    editor.insertNode(newParagraph);
                    inserted = true;
                } catch(e) {}
            }
            if (!inserted) {
                try {
                    editor.apply({type: 'insert_node', path: [divIdx + 1], node: newParagraph});
                    inserted = true;
                } catch(e) {
                    return {error: 'insert_node failed: ' + e.message};
                }
            }

            // Now move selection to the new paragraph
            var newIdx = divIdx + 1;
            try {
                editor.apply({
                    type: 'set_selection',
                    properties: editor.selection,
                    newProperties: {
                        anchor: {path: [newIdx, 0], offset: 0},
                        focus:  {path: [newIdx, 0], offset: 0}
                    }
                });
                editor.marks = {};
                return {ok: true, targetIdx: newIdx, existed: false, inserted: true};
            } catch(e) { return {error: 'set_selection B post: ' + e.message}; }
        }""")

        log.debug("_focus_after_divider fiber result: %s", moved)

        if moved and moved.get("ok"):
            await self.page.wait_for_timeout(300)
            await self._click_slate_path_node(moved["targetIdx"])
            await self._scroll_cursor_into_view()
            # 激活段落的 slash 菜单上下文：输入一个占位符字符再删除
            # 不做这一步，slash 菜单出现但无选项（JoySpace 内部状态未初始化）
            await self._refocus_virtual_caret()
            await self.page.keyboard.type("a", delay=50)
            await self.page.wait_for_timeout(100)
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(200)
            log.debug("_focus_after_divider: via fiber targetIdx=%s inserted=%s",
                      moved["targetIdx"], moved.get("inserted"))
            return

        # 兜底：点击 divider DOM 下方空白处
        log.warning("_focus_after_divider: fiber failed (%s), falling back to DOM click", moved)
        clicked = await self.page.evaluate("""() => {
            var ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            var children = Array.from(ed.children);
            // 找最后一个 sl-line（不是 sl-paragraph）= divider DOM
            for (var i = children.length - 1; i >= 0; i--) {
                var cls = children[i].className || '';
                if (cls.includes('sl-line') && !cls.includes('sl-paragraph')) {
                    // 点击 divider 下方：取 divider 的 bottom + 10px
                    var r = children[i].getBoundingClientRect();
                    children[i].scrollIntoView({block: 'center'});
                    r = children[i].getBoundingClientRect();
                    return {x: Math.round(r.x + r.width * 0.3),
                            y: Math.round(r.bottom + 10)};
                }
            }
            // fallback: last child bottom
            var last = children[children.length - 1];
            if (last) {
                last.scrollIntoView({block: 'center'});
                var lr = last.getBoundingClientRect();
                return {x: Math.round(lr.x + lr.width * 0.3), y: Math.round(lr.bottom + 10)};
            }
            return null;
        }""")
        if clicked and isinstance(clicked, dict):
            await self.page.mouse.click(clicked["x"], clicked["y"])
            await self.page.wait_for_timeout(400)
        await self._scroll_cursor_into_view()

    async def _focus_editor(self) -> None:
        """坐标点击编辑区，避免被遮挡层拦截。优先点击最后一个普通段落块。

        show-title 模式：Slate 第一个块是标题行，必须跳过，否则光标会落在标题区。
        """
        # 先把内部 scroll 容器滚到顶部，确保第一个块可见
        await self._scroll_container_to_top()
        await self.page.wait_for_timeout(300)
        coords = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const container = ed.closest('.sl-editor-container');
            const isShowTitle = container && container.classList.contains('show-title');

            const children = Array.from(ed.children);
            // show-title 模式跳过第一个块（标题行）
            const startIdx = isShowTitle ? 1 : 0;

            // 优先：最后一个普通段落（非表格/分割线/高亮块）
            for (let i = children.length - 1; i >= startIdx; i--) {
                const b = children[i];
                if (b.classList.contains('sl-table-wrap')) continue;
                if (b.querySelector('[data-slate-type="table"]')) continue;
                if (b.classList.contains('sl-divider')) continue;
                if (b.querySelector('.sl-divider')) continue;
                if (b.classList.contains('sl-highlight-block')) continue;
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < window.innerHeight)
                    return {x: Math.round(r.x + r.width * 0.3), y: Math.round(r.y + r.height / 2)};
            }
            // 兜底：点任意可见子块（仍跳过标题行）
            for (let i = children.length - 1; i >= startIdx; i--) {
                const b = children[i];
                if (b.classList.contains('sl-table-wrap')) continue;
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < window.innerHeight)
                    return {x: Math.round(r.x + r.width * 0.3), y: Math.round(r.y + r.height / 2)};
            }
            // 最终兜底：编辑区中部（y + 80 跳过标题行高度）
            const er = ed.getBoundingClientRect();
            return {x: Math.round(er.x + er.width * 0.3), y: Math.round(er.y + (isShowTitle ? 80 : 40))};
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)

    async def _focus_after_table(self) -> None:
        """将光标定位到最后一个表格之后。

        关键步骤：先把内部 scroll 容器调整到「表格底部在视口 40% 处」，
        这样表格下方始终有足够的可见空间，再点击后续块或表格正下方。
        """
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(300)

        # 调整 scroll 容器：让最后一个表格的底部出现在视口 40% 处
        await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return;
            let scrollEl = tbl.parentElement;
            while (scrollEl && scrollEl !== document.documentElement) {
                const s = window.getComputedStyle(scrollEl);
                if (['scroll','auto'].includes(s.overflow) ||
                    ['scroll','auto'].includes(s.overflowY)) break;
                scrollEl = scrollEl.parentElement;
            }
            if (!scrollEl || scrollEl === document.documentElement) {
                tbl.scrollIntoView({block: 'start'});
                return;
            }
            const tblRect = tbl.getBoundingClientRect();
            const containerRect = scrollEl.getBoundingClientRect();
            // tbl bottom 相对 scroll 容器的绝对 offset
            const tblBottomAbs = tblRect.bottom - containerRect.top + scrollEl.scrollTop;
            // 目标：tbl bottom 在视口 40% 处 → 下方有 60% 视口空间
            const desired = tblBottomAbs - window.innerHeight * 0.4;
            scrollEl.scrollTop = Math.max(0, desired);
        }""")
        await self.page.wait_for_timeout(400)

        result = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return {via: 'no-editor'};
            const children = Array.from(ed.children);
            let lastTblIdx = -1;
            for (let i = 0; i < children.length; i++) {
                const b = children[i];
                if (b.classList.contains('sl-table-wrap') ||
                    b.querySelector('[data-slate-type="table"]') ||
                    b.querySelector('table')) {
                    lastTblIdx = i;
                }
            }
            if (lastTblIdx === -1) return {via: 'no-table'};

            // 找表格后第一个在视口内的块（允许空行高度很小）
            for (let i = lastTblIdx + 1; i < children.length; i++) {
                const b = children[i];
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < window.innerHeight)
                    return {via: 'after-block',
                            x: Math.round(r.x + r.width * 0.15),
                            y: Math.round(r.y + Math.max(r.height / 2, 8))};
            }

            // 表格是最后一块：点击其下方（scroll 已调好，tr.bottom 在视口 40% 处）
            const tbl = children[lastTblIdx];
            const er = ed.getBoundingClientRect();
            const tr = tbl.getBoundingClientRect();
            const targetY = tr.bottom + 30;
            if (targetY < window.innerHeight - 10)
                return {via: 'below-last-table',
                        x: Math.round(er.x + er.width * 0.3),
                        y: Math.round(targetY)};
            // 极端兜底（表格撑满整个视口）
            return {via: 'editor-bottom',
                    x: Math.round(er.x + er.width * 0.3),
                    y: Math.round(Math.min(er.bottom - 10, window.innerHeight - 15))};
        }""")

        via = result.get("via", "")
        log.debug("_focus_after_table via=%s", via)

        if via in ("no-editor", "no-table"):
            log.warning("_focus_after_table: %s", via)
            return

        await self.page.mouse.click(result["x"], result["y"])
        await self.page.wait_for_timeout(400)
        if via == "after-block":
            await self.page.keyboard.press("End")
        await self.page.wait_for_timeout(100)

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

    async def _refocus_virtual_caret(self) -> None:
        """让 Slate 重新接收键盘事件（弹出框关闭后焦点会离开 Slate）。

        virtual-caret-input 被编辑区覆盖，不能用 Playwright click()，
        改用 JS focus() 直接激活。
        """
        await self.page.evaluate("""() => {
            const vci = document.querySelector('.ant-input.virtual-caret-input');
            if (vci) vci.focus();
        }""")
        await self.page.wait_for_timeout(150)

    async def _focus_title_or_body(self) -> None:
        """将焦点移到 Slate 编辑区的虚拟光标 textarea（clear 专用）。

        JoySpace 通过 .ant-input.virtual-caret-input 路由所有键盘事件到 Slate，
        点击它是让 Cmd+A / Backspace 等快捷键生效最可靠的方式。
        若找不到 virtual-caret-input，再兜底点击编辑区内可见块。
        """
        coords = await self.page.evaluate("""() => {
            // 首选：virtual-caret-input（Slate 键盘事件入口）
            const vci = document.querySelector('.ant-input.virtual-caret-input');
            if (vci) {
                const r = vci.getBoundingClientRect();
                if (r.width >= 0 && r.height >= 0)
                    return {x: Math.round(r.x + 2), y: Math.round(r.y + 2), via: 'virtual-caret'};
            }

            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;

            const blocks = Array.from(ed.querySelectorAll('[data-slate-node="element"]'));

            // 优先：高度 > 0 的非表格顶层块
            for (const b of blocks) {
                if (b.closest('[data-slate-type="table"]')) continue;
                if (b.closest('.sl-table-wrap')) continue;
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.top >= 0 && r.top < window.innerHeight)
                    return {x: Math.round(r.x + r.width * 0.15),
                            y: Math.round(r.y + Math.min(12, r.height / 2)),
                            via: 'non-table-block'};
            }

            // 兜底：点编辑区顶部
            const er = ed.getBoundingClientRect();
            return {x: Math.round(er.x + er.width * 0.15),
                    y: Math.round(er.y + 20),
                    via: 'editor-top'};
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
        """确保光标在空行行首（块级插入前调用）。"""
        # 防御性检查：若光标在表格内，先强制跳出
        if await self._is_cursor_in_table():
            log.warning("_ensure_empty_line: 检测到光标在表格内，强制跳出")
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
            await self._force_focus_below_table()
            await self.page.wait_for_timeout(200)

        # 若光标在列表上下文中，按 Backspace 退出列表格式
        if await self._is_cursor_in_list():
            await self.page.keyboard.press("Backspace")
            await self.page.wait_for_timeout(200)

        # 用 [data-slate-string] 节点的 textContent 判断空行，过滤零宽字符。
        # innerText 不可靠：Slate 在空段落里插入零宽占位符导致 innerText 非空。
        is_empty = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return true;

            const blockIsEmpty = (node) => {
                const strings = node.querySelectorAll('[data-slate-string]');
                const text = Array.from(strings)
                    .map(s => s.textContent)
                    .join('')
                    .replace(/[\u200B\u200C\u200D\uFEFF\u00A0]/g, '')
                    .trim();
                return text === '';
            };

            // 方法1：Selection API → 光标所在的 ed 直接子块
            const sel = window.getSelection();
            if (sel && sel.anchorNode) {
                let node = sel.anchorNode.nodeType === 3
                    ? sel.anchorNode.parentElement
                    : sel.anchorNode;
                while (node && node !== ed) {
                    if (node.parentElement === ed)
                        return blockIsEmpty(node);
                    node = node.parentElement;
                }
            }

            // 方法2：回退到 ed.children 最后一个非表格块
            const top = Array.from(ed.children).filter(b =>
                !b.classList.contains('sl-table-wrap') &&
                !b.querySelector('[data-slate-type="table"]')
            );
            if (!top.length) return true;
            return blockIsEmpty(top[top.length - 1]);
        }""")
        if not is_empty:
            await self.page.keyboard.press("End")
            await self.page.keyboard.press("Enter")
            await self.page.wait_for_timeout(200)
            await self._scroll_cursor_into_view()

    async def _slash_insert(self, alias: str) -> None:
        """执行斜杠命令：先单独打 /，等菜单弹出，再逐字输入 alias 过滤，最后 Enter 确认。"""
        await self._scroll_cursor_into_view()
        await self.page.keyboard.type("/", delay=80)
        await self.page.wait_for_timeout(600)   # 等斜杠菜单弹出
        await self.page.keyboard.type(alias, delay=80)
        await self.page.wait_for_timeout(800)   # 等过滤结果稳定
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(800)

    async def _delete_last_col(self) -> bool:
        """右键点击表格最后一列的第一行单元格，选择「删除列」。
        右键前先把目标单元格滚入视口，避免坐标为负数打到右上角。
        """
        # 先把目标单元格滚入视口
        await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return;
            const firstRow = tbl.querySelector('tr');
            if (!firstRow) return;
            const cells = firstRow.querySelectorAll('td, th');
            const last = cells[cells.length - 1];
            if (last) last.scrollIntoView({block: 'center'});
        }""")
        await self.page.wait_for_timeout(300)

        coords = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return null;
            const firstRow = tbl.querySelector('tr');
            if (!firstRow) return null;
            const cells = firstRow.querySelectorAll('td, th');
            const last = cells[cells.length - 1];
            if (!last) return null;
            const r = last.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
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

    async def _get_table_dims(self) -> tuple[int, int]:
        """返回当前表格（最后一个）的 (行数, 列数)，找不到返回 (0, 0)。"""
        result = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return [0, 0];
            const rows = tbl.querySelectorAll('tr');
            const cols = rows[0] ? rows[0].querySelectorAll('td, th').length : 0;
            return [rows.length, cols];
        }""")
        return tuple(result)

    async def _right_click_cell(self, row_idx: int, col_idx: int) -> None:
        """滚入视口（确保 ≥ 140px 顶部边距）后右键点击最后一个表格中指定行列的单元格（0-based）。"""
        # 先关闭任何可能存在的浮层（搜索框、标签输入、快速访问弹层等）
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(200)
        await self.page.evaluate(f"""() => {{
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return;
            const rows = tbl.querySelectorAll('tr');
            const row = rows[{row_idx}];
            if (!row) return;
            const cells = row.querySelectorAll('td, th');
            const cell = cells[{col_idx}];
            if (cell) {{
                cell.scrollIntoView({{block: 'center'}});
                const minTop = 200;
                const r = cell.getBoundingClientRect();
                if (r.top < minTop) {{
                    let el = cell.parentElement;
                    while (el && el !== document.documentElement) {{
                        const s = window.getComputedStyle(el);
                        if (['scroll','auto'].includes(s.overflow) ||
                            ['scroll','auto'].includes(s.overflowY)) {{
                            el.scrollTop -= (minTop - r.top);
                            break;
                        }}
                        el = el.parentElement;
                    }}
                    if (!el || el === document.documentElement)
                        window.scrollBy(0, -(minTop - r.top));
                }}
            }}
        }}""")
        await self.page.wait_for_timeout(300)
        coords = await self.page.evaluate(f"""() => {{
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return null;
            const rows = tbl.querySelectorAll('tr');
            const row = rows[{row_idx}];
            if (!row) return null;
            const cells = row.querySelectorAll('td, th');
            const cell = cells[{col_idx}];
            if (!cell) return null;
            const r = cell.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
        }}""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"], button="right")
            await self.page.wait_for_timeout(800)

    async def _click_context_menu(self, text: str, count: int = 1) -> bool:
        """在当前右键菜单中找到包含 text 的菜单项并点击。

        count: 若菜单项有数量输入框（如"向右插入N列"），填入此数量。
        """
        info = await self.page.evaluate(f"""() => {{
            const candidates = document.querySelectorAll(
                '[role="menuitem"], .ant-dropdown-menu-item, .sl-context-menu-item, li[class*="menu"]');
            for (const item of candidates) {{
                const allText = (item.textContent || '').trim();
                if (!allText.includes('{text}')) continue;
                const r = item.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                const inp = item.querySelector('input.ant-input');
                if (inp) {{
                    const ir = inp.getBoundingClientRect();
                    return {{
                        has_input: true,
                        inp_x: Math.round(ir.x + ir.width / 2),
                        inp_y: Math.round(ir.y + ir.height / 2),
                        insert_x: Math.round(ir.x - 15),
                        insert_y: Math.round(ir.y + ir.height / 2),
                    }};
                }}
                return {{
                    has_input: false,
                    x: Math.round(r.x + r.width / 2),
                    y: Math.round(r.y + r.height / 2),
                }};
            }}
            const all = document.querySelectorAll(
                '[role="menuitem"], .ant-dropdown-menu-item, .sl-context-menu-item, li[class*="menu"]');
            const texts = Array.from(all)
                .filter(el => el.getBoundingClientRect().width > 0)
                .map(el => (el.textContent || '').trim().substring(0, 30));
            return {{ not_found: true, available: texts }};
        }}""")

        if not info or info.get("not_found"):
            available = info.get("available", []) if info else []
            if available:
                log.info("右键菜单未找到「%s」，可用项: %s", text, available)
            else:
                log.warning("右键菜单未找到「%s」且菜单为空（右键可能未触发）", text)
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
            return False

        if info.get("has_input"):
            await self.page.mouse.click(info["inp_x"], info["inp_y"])
            await self.page.wait_for_timeout(150)
            await self.page.keyboard.press("ControlOrMeta+a")
            await self.page.keyboard.type(str(count))
            await self.page.wait_for_timeout(150)
            await self.page.mouse.click(info["insert_x"], info["insert_y"])
        else:
            await self.page.mouse.click(info["x"], info["y"])

        await self.page.wait_for_timeout(600)
        log.debug("点击菜单项「%s」成功", text)
        return True

    async def _adjust_table_dimensions(self, target_rows: int, target_cols: int) -> None:
        """将表格调整到目标行列数（默认 3×3），通过右键菜单增删行/列。

        增加时一次性输入 delta 数量，避免逐个操作。
        删除仍需逐步进行（菜单无批量删除输入）。
        """
        cur_rows, cur_cols = await self._get_table_dims()
        log.debug("调整表格: 当前 %dx%d → 目标 %dx%d",
                  cur_rows, cur_cols, target_rows, target_cols)

        MAX_TRIES = 30

        # ── 先调整列数
        cur_rows, cur_cols = await self._get_table_dims()
        if cur_cols < target_cols:
            delta = target_cols - cur_cols
            await self._right_click_cell(0, cur_cols - 1)
            await self._click_context_menu("向右插入", count=delta)
            await self.page.wait_for_timeout(300)
        elif cur_cols > target_cols:
            for _ in range(MAX_TRIES):
                _, cur_cols = await self._get_table_dims()
                if cur_cols <= target_cols:
                    break
                await self._right_click_cell(0, cur_cols - 1)
                await self._click_context_menu("删除所选列")
            else:
                log.warning("列数删除超过 %d 次仍未达目标", MAX_TRIES)

        # ── 再调整行数
        cur_rows, cur_cols = await self._get_table_dims()
        if cur_rows < target_rows:
            delta = target_rows - cur_rows
            await self._right_click_cell(cur_rows - 1, 0)
            await self._click_context_menu("向下插入", count=delta)
            await self.page.wait_for_timeout(300)
        elif cur_rows > target_rows:
            for _ in range(MAX_TRIES):
                cur_rows, _ = await self._get_table_dims()
                if cur_rows <= target_rows:
                    break
                await self._right_click_cell(cur_rows - 1, 0)
                await self._click_context_menu("删除所选行")
            else:
                log.warning("行数删除超过 %d 次仍未达目标", MAX_TRIES)

        log.debug("表格尺寸调整完成")

    async def _goto_first_cell(self) -> None:
        """滚入视口并点击最后一个表格左上角第一个单元格，获取输入焦点。"""
        await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return;
            const firstCell = tbl.querySelector('td, th');
            if (firstCell) firstCell.scrollIntoView({block: 'center'});
        }""")
        await self.page.wait_for_timeout(300)
        coords = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return null;
            const cell = tbl.querySelector('td, th');
            if (!cell) return null;
            const r = cell.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(300)

    async def _exit_table(self) -> None:
        """跳出表格：先 Escape，再点击表格正下方的位置。"""
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(400)
        # 优先点击最后一个表格 wrap 的 nextElementSibling
        moved = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return false;
            const wrap = tbl.closest('[data-slate-node="element"]');
            const sib = wrap && wrap.nextElementSibling;
            if (sib) { sib.click(); return true; }
            return false;
        }""")
        if not moved:
            # 点击表格下方 30px（确保在表格外，而不是 ed.bottom 可能落在表格内）
            coords = await self.page.evaluate("""() => {
                const tbls = document.querySelectorAll(
                    '.page-main-content [data-slate-type="table"], .page-main-content table');
                const tbl = tbls[tbls.length - 1];
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
        """Hover 最后一个表格触发工具栏，然后点击对应按钮。

        工具栏按钮顺序（`.pop-menu-item.h`）：
          0 → 粗体首行
          1 → 粗体首列
          2 → 自适应列宽（按内容）
          3 → 适应页面宽度
        """
        # 获取最后一个表格位置，确保顶部距视口上边缘 ≥ 350px（给工具栏足够空间完整露出）
        # 必须滚动表格真正的 scroll 容器，不能用 window.scrollBy
        tbl_rect = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return null;
            tbl.scrollIntoView({block: 'center'});
            const minTop = 350;
            const r = tbl.getBoundingClientRect();
            if (r.top < minTop) {
                // 找到真正的 overflow scroll 容器并调整其 scrollTop
                let el = tbl.parentElement;
                while (el && el !== document.documentElement) {
                    const s = window.getComputedStyle(el);
                    if (['scroll','auto'].includes(s.overflow) ||
                        ['scroll','auto'].includes(s.overflowY)) {
                        el.scrollTop -= (minTop - r.top);
                        break;
                    }
                    el = el.parentElement;
                }
                if (!el || el === document.documentElement)
                    window.scrollBy(0, -(minTop - r.top));
            }
            const r2 = tbl.getBoundingClientRect();
            return {
                x: Math.round(r2.x), y: Math.round(r2.y),
                cx: Math.round(r2.x + r2.width/2),
                cy: Math.round(r2.y + r2.height/2),
            };
        }""")
        if not tbl_rect:
            log.warning("未找到表格，跳过工具栏操作")
            return
        await self.page.wait_for_timeout(400)

        # 先将鼠标移到编辑区外（中立位置）：停在表格左侧且与表格同高，
        # 避免穿过顶部格式栏触发字体下拉（格式栏在 y≈65，这里保持在 y≥表格顶部-10）
        neutral_start = (tbl_rect["x"] - 80, tbl_rect["y"] - 10)
        await self.page.mouse.move(neutral_start[0], neutral_start[1])
        await self.page.wait_for_timeout(300)

        # 从表格左上角斜向移入并到达顶部 +5px 处，与 test_table_fullwidth.py 验证过的方式相同
        # 鼠标在表格顶部边缘 5px 内，移动到上方工具栏按钮只需穿越 ~5px
        await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] + 5)
        await self.page.wait_for_timeout(1000)  # 等工具栏出现


        async def click_toolbar_by_icon(icon_class: str) -> bool:
            """通过图标 class 精确查找工具栏按钮，不依赖顺序 index。"""
            coords = await self.page.evaluate(f"""() => {{
                const btns = document.querySelectorAll('.pop-menu-item.h');
                for (const btn of btns) {{
                    const icon = btn.querySelector('i, span');
                    if (icon && (icon.className || '').includes('{icon_class}')) {{
                        const r = btn.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
                    }}
                }}
                return null;
            }}""")
            if coords:
                await self.page.mouse.move(coords["x"], coords["y"])
                await self.page.wait_for_timeout(300)
                await self.page.mouse.click(coords["x"], coords["y"])
                await self.page.wait_for_timeout(400)
                log.debug("btn click %s coords=%s", icon_class, coords)
                return True
            return False

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

        async def rehover() -> None:
            """点击某个工具栏按钮后重新触发工具栏。"""
            await self.page.mouse.move(tbl_rect["x"] - 80, tbl_rect["y"] - 10)
            await self.page.wait_for_timeout(200)
            await self.page.mouse.move(tbl_rect["cx"], tbl_rect["y"] + 5)
            await self.page.wait_for_timeout(700)

        # full_width 先执行：设置完宽度后 rehover，再做其他操作
        if full_width:
            ok = await click_toolbar_by_icon("adaptivewidth")
            if not ok:
                ok = await click_toolbar_btn(3)
            log.debug("full_width: ok=%s", ok)
            if ok:
                await self.page.wait_for_timeout(600)
                await rehover()

        if bold_header_row:
            ok = await click_toolbar_btn(0)
            log.debug("首行加粗: %s", "✓" if ok else "✗ 按钮未找到")
            if bold_header_col:
                await rehover()

        if bold_header_col:
            ok = await click_toolbar_btn(1)
            log.debug("首列加粗: %s", "✓" if ok else "✗ 按钮未找到")

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

        # 获取最后一个表格位置和总宽度，确保顶部距视口上边缘 ≥ 200px
        tbl_info = await self.page.evaluate("""() => {
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!tbl) return null;
            tbl.scrollIntoView({block: 'center'});
            const minTop = 200;
            const r0 = tbl.getBoundingClientRect();
            if (r0.top < minTop) {
                let el = tbl.parentElement;
                while (el && el !== document.documentElement) {
                    const s = window.getComputedStyle(el);
                    if (['scroll','auto'].includes(s.overflow) ||
                        ['scroll','auto'].includes(s.overflowY)) {
                        el.scrollTop -= (minTop - r0.top);
                        break;
                    }
                    el = el.parentElement;
                }
                if (!el || el === document.documentElement)
                    window.scrollBy(0, -(minTop - r0.top));
            }
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

    async def _scroll_cursor_into_view(self) -> None:
        """把当前光标所在行滚动到视口 40% 处，确保光标下方有足够的交互空间。

        JoySpace 使用内部 overflow-scroll 容器而非 window.scroll，所以不能用
        scrollIntoView 然后依赖 window.scrollY — 必须直接操作内部容器的 scrollTop。
        """
        await self.page.evaluate("""() => {
            // 找 overflow-scroll 容器
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return;
            let scEl = ed.parentElement;
            while (scEl && scEl !== document.documentElement) {
                const s = window.getComputedStyle(scEl);
                if (['scroll','auto'].includes(s.overflow) ||
                    ['scroll','auto'].includes(s.overflowY)) break;
                scEl = scEl.parentElement;
            }
            if (!scEl || scEl === document.documentElement) return;

            // 优先：通过 Slate fiber selection 定位目标块（DOM selection 永远在 caret-position-wrap，不可靠）
            let targetEl = null;
            const fiberKey = Object.keys(ed).find(k => k.startsWith('__reactInternalInstance'));
            if (fiberKey) {
                function findEditor(node, d) {
                    if (!node || d > 30) return null;
                    if (node.memoizedProps && node.memoizedProps.editor &&
                        node.memoizedProps.editor.marks !== undefined)
                        return node.memoizedProps.editor;
                    return findEditor(node.child, d + 1);
                }
                const editor = findEditor(ed[fiberKey], 0);
                if (editor && editor.selection) {
                    const pathIdx = editor.selection.anchor.path[0];
                    if (typeof pathIdx === 'number') {
                        const children = Array.from(ed.children);
                        targetEl = children[pathIdx] || null;
                    }
                }
            }

            // 回退：DOM selection（虽然不准确，至少不会崩）
            if (!targetEl) {
                const sel = window.getSelection();
                if (sel && sel.anchorNode) {
                    const node = sel.anchorNode.nodeType === 3
                        ? sel.anchorNode.parentElement : sel.anchorNode;
                    let cur = node;
                    while (cur && cur.parentElement && cur.parentElement !== ed)
                        cur = cur.parentElement;
                    if (cur && cur !== ed) targetEl = cur;
                }
            }
            if (!targetEl) {
                const children = Array.from(ed.children);
                targetEl = children[children.length - 1] || ed;
            }

            // 把目标块滚到视口 40% 处
            const scRect = scEl.getBoundingClientRect();
            const tRect  = targetEl.getBoundingClientRect();
            const tAbsTop = tRect.top - scRect.top + scEl.scrollTop;
            const desired = tAbsTop - scEl.clientHeight * 0.4;
            scEl.scrollTop = Math.max(0, desired);
        }""")
        await self.page.wait_for_timeout(200)

    async def _scroll_container_to_top(self) -> None:
        """把编辑区的内部 scroll 容器滚回顶部（JoySpace 不用 window scroll）。"""
        await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) { window.scrollTo(0, 0); return; }
            let el = ed.parentElement;
            while (el && el !== document.documentElement) {
                const s = window.getComputedStyle(el);
                if (['scroll','auto'].includes(s.overflow) ||
                    ['scroll','auto'].includes(s.overflowY)) {
                    el.scrollTop = 0;
                    return;
                }
                el = el.parentElement;
            }
            window.scrollTo(0, 0);
        }""")

    async def _is_cursor_in_table(self) -> bool:
        """检测当前光标是否在表格单元格内。"""
        return await self.page.evaluate("""() => {
            const sel = window.getSelection();
            if (!sel || !sel.anchorNode) return false;
            const node = sel.anchorNode.nodeType === 3
                ? sel.anchorNode.parentElement
                : sel.anchorNode;
            return !!(node && (
                node.closest('[data-slate-type="table"]') ||
                node.closest('td') ||
                node.closest('th')
            ));
        }""")

    async def _force_focus_below_table(self) -> None:
        """强制将焦点定位到表格后方：先滚动到底，再点击表格下方空白处。"""
        # 滚动编辑区容器到底部
        await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return;
            let el = ed.parentElement;
            while (el && el !== document.documentElement) {
                const s = window.getComputedStyle(el);
                if (['scroll','auto'].includes(s.overflow) ||
                    ['scroll','auto'].includes(s.overflowY)) {
                    el.scrollTop = el.scrollHeight;
                    return;
                }
                el = el.parentElement;
            }
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        await self.page.wait_for_timeout(400)

        coords = await self.page.evaluate("""() => {
            const ed = document.querySelector(
                '.page-main-content .slate-editor.use-virtual-caret');
            const tbls = document.querySelectorAll(
                '.page-main-content [data-slate-type="table"], .page-main-content table');
            const tbl = tbls[tbls.length - 1];
            if (!ed) return null;
            const er = ed.getBoundingClientRect();
            if (!tbl)
                return {x: Math.round(er.x + er.width * 0.3), y: Math.round(er.bottom - 20)};
            const tr = tbl.getBoundingClientRect();
            const targetY = Math.min(tr.bottom + 60, er.bottom - 8, window.innerHeight - 10);
            if (targetY > tr.bottom + 5)
                return {x: Math.round(er.x + er.width * 0.3), y: Math.round(targetY)};
            return {x: Math.round(er.x + er.width * 0.3), y: Math.round(er.bottom - 5)};
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(300)
            log.debug("_force_focus_below_table 点击 (%d,%d)", coords["x"], coords["y"])

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

    # ------------------------------------------------------------------ #
    #  行内格式辅助：选中、工具条、颜色
    # ------------------------------------------------------------------ #

    async def _get_last_text_leaf_rect(self) -> dict | None:
        """获取编辑区最后一个文字叶节点的 bounding rect。"""
        return await self.page.evaluate("""() => {
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const walker = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT);
            let last = null;
            while (walker.nextNode()) {
                if (walker.currentNode.nodeValue.replace(/​|﻿| /g, '').trim())
                    last = walker.currentNode;
            }
            if (!last) return null;
            const range = document.createRange();
            range.selectNode(last);
            const r = range.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return {x: Math.round(r.x + 1), y: Math.round(r.y + r.height/2),
                    right: Math.round(r.right - 1), height: Math.round(r.height)};
        }""")

    async def _select_last_typed(self, char_count: int) -> None:
        """用鼠标拖拽选中刚刚输入的最后 char_count 个字符。

        用 DOM Range API 计算目标字符的精确坐标，再拖拽触发浮动工具条。
        """
        rect = await self.page.evaluate(f"""() => {{
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            // 找最后一个有内容的文字节点
            const walker = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT);
            let lastNode = null;
            while (walker.nextNode()) {{
                const val = walker.currentNode.nodeValue
                    .replace(/[\\u200B\\uFEFF\\u00A0]/g, '');
                if (val.trim()) lastNode = walker.currentNode;
            }}
            if (!lastNode) return null;
            const textLen = lastNode.nodeValue.length;
            const startIdx = Math.max(0, textLen - {char_count});
            try {{
                const range = document.createRange();
                range.setStart(lastNode, startIdx);
                range.setEnd(lastNode, textLen);
                const r = range.getBoundingClientRect();
                if (r.width > 0 && r.height > 0)
                    return {{x: Math.round(r.x), y: Math.round(r.y + r.height/2),
                             right: Math.round(r.right)}};
            }} catch(e) {{}}
            return null;
        }}""")

        if not rect or rect["right"] <= rect["x"]:
            log.warning("_select_last_typed: DOM Range 失败，回退 Shift+ArrowLeft")
            for _ in range(char_count):
                await self.page.keyboard.press("Shift+ArrowLeft")
                await self.page.wait_for_timeout(20)
            await self.page.wait_for_timeout(500)
            return

        x_start = rect["x"]
        x_end = rect["right"]
        y = rect["y"]

        # 从左向右拖拽（左→右与人类操作相同，可靠触发浮动工具条）
        await self.page.mouse.move(x_start, y)
        await self.page.wait_for_timeout(80)
        await self.page.mouse.down()
        await self.page.wait_for_timeout(80)
        steps = max(8, (x_end - x_start) // 5)
        for i in range(1, steps + 1):
            ix = x_start + (x_end - x_start) * i // steps
            await self.page.mouse.move(ix, y)
            await self.page.wait_for_timeout(15)
        await self.page.mouse.up()
        await self.page.wait_for_timeout(700)  # 等浮动工具条出现

    async def _click_inline_toolbar_button(self, button_key: str) -> bool:
        """在浮动工具条中点击指定 data-button-key 的按钮。"""
        coords = await self.page.evaluate(f"""() => {{
            const toolbar = document.querySelector('.inline-toolbar-inner');
            if (!toolbar) return null;
            const btn = toolbar.querySelector('[data-button-key="{button_key}"]');
            if (!btn) return null;
            const r = btn.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
        }}""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(500)
            return True
        return False

    async def _apply_font_color(self, color: str) -> bool:
        """在浮动工具条中点击颜色按钮(A)，然后在弹出面板中选择指定颜色。

        color: 十六进制颜色，如 "#F5222D"，大小写不敏感。
        """
        # 1. 找颜色按钮（含 sl-editor-toolbar-font-icon 的按钮）并点击
        color_btn = await self.page.evaluate("""() => {
            const toolbar = document.querySelector('.inline-toolbar-inner');
            if (!toolbar) return null;
            const btn = toolbar.querySelector('.sl-editor-toolbar-font-icon')
                              ?.closest('button, .sl-editor-toolbar-dropdown');
            if (!btn) return null;
            const r = btn.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")
        if not color_btn:
            log.warning("_apply_font_color: 找不到颜色按钮")
            return False

        await self.page.mouse.click(color_btn["x"], color_btn["y"])
        await self.page.wait_for_timeout(800)

        # 2. 在颜色面板中找到目标颜色并点击
        color_upper = color.upper().lstrip("#")
        full_color = f"#{color_upper}"

        color_item = await self.page.evaluate(f"""() => {{
            // 颜色面板容器
            const container = document.querySelector('.sl-editor-toolbar-fontcolor-container');
            if (!container) return null;
            const items = container.querySelectorAll('[data-font-color]');
            for (const item of items) {{
                const c = (item.getAttribute('data-font-color') || '').toUpperCase();
                if (c === '{full_color}'.toUpperCase()) {{
                    const r = item.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0)
                        return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
                }}
            }}
            // 列出可用颜色
            return {{not_found: true,
                     available: Array.from(items).map(i => i.getAttribute('data-font-color'))}};
        }}""")

        if not color_item or color_item.get("not_found"):
            available = color_item.get("available", []) if color_item else []
            log.warning("_apply_font_color: 颜色 %s 不在面板中，可用: %s", full_color, available)
            await self.page.keyboard.press("Escape")
            return False

        await self.page.mouse.click(color_item["x"], color_item["y"])
        await self.page.wait_for_timeout(500)
        return True

    async def _reset_slate_marks(self) -> bool:
        """通过 React fiber 访问 Slate editor，将选区折叠到末尾并清除 marks。

        解决行内格式后 marks 继承问题：
        - 折叠 Slate 内部 selection（颜色/加粗后 selection 可能仍指向原选区）
        - 将 editor.marks 设为 {} 而非 null，防止从相邻字符继承格式
        """
        return await self.page.evaluate("""() => {
            var ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            var fiberKey = Object.keys(ed).find(function(k) {
                return k.startsWith('__reactInternalInstance');
            });
            if (!fiberKey) return false;
            var fiber = ed[fiberKey];
            function findEditor(node, d) {
                if (!node || d > 30) return null;
                if (node.memoizedProps && node.memoizedProps.editor &&
                    node.memoizedProps.editor.marks !== undefined)
                    return node.memoizedProps.editor;
                return findEditor(node.child, d + 1);
            }
            var editor = findEditor(fiber, 0);
            if (!editor) return false;
            if (editor.selection && !editor.selection.anchor.equals) {
                var focus = editor.selection.focus;
                try {
                    editor.apply({
                        type: 'set_selection',
                        properties: editor.selection,
                        newProperties: {anchor: focus, focus: focus}
                    });
                } catch(e) {}
            }
            editor.marks = {};
            return true;
        }""")

    async def _deselect_and_move_end(self) -> None:
        """取消选区，将光标移到当前行末尾。"""
        await self.page.keyboard.press("ArrowRight")
        await self.page.wait_for_timeout(100)

    # ------------------------------------------------------------------ #
    #  Heading / List / Highlight 辅助
    # ------------------------------------------------------------------ #

    async def _current_block_type_is_heading(self, level: int) -> bool:
        """检查光标所在块是否为指定级别的标题。

        先用 DOM selection 判断（不依赖 fiber.selection 是否为 null），
        找到光标所在的顶层 [data-slate-node="element"] 块，检查其 data-slate-type。
        """
        expected = f"h{level}"
        result = await self.page.evaluate(f"""() => {{
            // 用浏览器原生 selection 定位光标所在 DOM 节点
            const sel = window.getSelection();
            if (!sel || !sel.anchorNode) return false;
            let node = sel.anchorNode;
            // 向上找到 [data-slate-node="element"] 顶层块
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            while (node && node !== ed) {{
                if (node.nodeType === 1 && node.dataset &&
                    node.dataset.slateNode === 'element' &&
                    node.parentElement === ed) {{
                    return node.dataset.slateType === '{expected}';
                }}
                node = node.parentElement;
            }}
            return false;
        }}""")
        return bool(result)

    async def _set_heading_via_toolbar(self, level: int) -> bool:
        """通过顶部工具栏的段落类型选择器设置标题级别。

        流程：找工具栏中显示当前块类型的按钮（通常显示"正文"或已有标题名）→
        点击弹出选择框 → 找到 H{level} 选项并点击。
        """
        # 找工具栏中的段落类型按钮（y < 120px，包含"正文"、"标题"等文字）
        btn = await self.page.evaluate("""() => {
            const keywords = ['正文', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
                              '标题1', '标题2', '标题3', 'Heading', 'Normal', 'Text'];
            for (const el of document.querySelectorAll('button, [role="button"], span, div')) {
                const txt = (el.textContent || '').trim();
                if (!keywords.some(k => txt === k || txt.includes(k))) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.y >= 0 && r.y < 120)
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), txt};
            }
            return null;
        }""")
        if not btn:
            log.warning("_set_heading_via_toolbar: 未找到段落类型按钮")
            return False

        log.debug("_set_heading_via_toolbar: 点击按钮 %r", btn.get("txt"))
        await self.page.mouse.click(btn["x"], btn["y"])
        await self.page.wait_for_timeout(700)

        # 在弹出的选择框中找 H{level}
        level_labels = {
            1: ["H1", "标题1", "标题 1", "Heading 1"],
            2: ["H2", "标题2", "标题 2", "Heading 2"],
            3: ["H3", "标题3", "标题 3", "Heading 3"],
            4: ["H4", "标题4", "标题 4", "Heading 4"],
            5: ["H5", "标题5", "标题 5", "Heading 5"],
            6: ["H6", "标题6", "标题 6", "Heading 6"],
        }
        labels = level_labels.get(level, [f"H{level}"])
        labels_js = str(labels)

        opt = await self.page.evaluate(f"""() => {{
            const labels = {labels_js};
            const candidates = document.querySelectorAll(
                '[role="option"], [role="menuitem"], li, .sl-dropdown-item, .ant-select-item');
            for (const el of candidates) {{
                const txt = (el.textContent || '').trim();
                if (labels.some(l => txt === l || txt.includes(l))) {{
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.y >= 0 && r.y < window.innerHeight)
                        return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
                }}
            }}
            return null;
        }}""")

        if not opt:
            log.warning("_set_heading_via_toolbar: 下拉框未找到 H%d 选项", level)
            await self.page.keyboard.press("Escape")
            return False

        await self.page.mouse.click(opt["x"], opt["y"])
        await self.page.wait_for_timeout(400)
        return True

    async def _get_highlight_block_coords(self) -> dict | None:
        """获取最新高亮块的点击坐标（块内文字区中部）。"""
        return await self.page.evaluate("""() => {
            const hls = document.querySelectorAll('.page-main-content .sl-highlight-block');
            const hl = hls[hls.length - 1];
            if (!hl) return null;
            const r = hl.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return null;
            // 点击块内左侧文字区（避开 emoji 图标区）
            return {x: Math.round(r.x + 60), y: Math.round(r.y + Math.max(r.height / 2, 16))};
        }""")

    async def _is_cursor_in_highlight_block(self) -> bool:
        """检测光标是否在高亮块内部。"""
        return await self.page.evaluate("""() => {
            const sel = window.getSelection();
            if (!sel || !sel.anchorNode) return false;
            const node = sel.anchorNode.nodeType === 3
                ? sel.anchorNode.parentElement : sel.anchorNode;
            return !!(node && node.closest('.sl-highlight-block'));
        }""")

    async def _click_below_highlight_block(self) -> None:
        """点击最后一个高亮块下方，作为 exit 的最终回退。"""
        coords = await self.page.evaluate("""() => {
            const hls = document.querySelectorAll('.page-main-content .sl-highlight-block');
            const hl = hls[hls.length - 1];
            if (!hl) return null;
            const r = hl.getBoundingClientRect();
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            const er = ed ? ed.getBoundingClientRect() : r;
            const targetY = r.bottom + 20;
            if (targetY < window.innerHeight - 10)
                return {x: Math.round(er.x + er.width * 0.3), y: Math.round(targetY)};
            return null;
        }""")
        if coords:
            await self.page.mouse.click(coords["x"], coords["y"])
            await self.page.wait_for_timeout(400)

    async def _get_current_list_indent(self) -> int:
        """获取当前光标所在列表项的层级（0-based）。"""
        return await self.page.evaluate("""() => {
            const sel = window.getSelection();
            if (!sel || !sel.anchorNode) return 0;
            let node = sel.anchorNode.nodeType === 3
                ? sel.anchorNode.parentElement : sel.anchorNode;
            let depth = 0;
            while (node) {
                if (node.matches && (
                    node.matches('[data-slate-type="ul-item"]') ||
                    node.matches('[data-slate-type="list-item"]') ||
                    node.matches('li')
                )) depth++;
                const parent = node.parentElement;
                if (!parent || parent.classList.contains('slate-editor')) break;
                node = parent;
            }
            // 更可靠：读取 data-indent 或 padding-left 推算
            const sel2 = window.getSelection();
            if (sel2 && sel2.anchorNode) {
                let n = sel2.anchorNode.nodeType === 3
                    ? sel2.anchorNode.parentElement : sel2.anchorNode;
                while (n) {
                    const indent = n.getAttribute && n.getAttribute('data-indent');
                    if (indent !== null && indent !== undefined) return parseInt(indent) || 0;
                    if (n.classList && n.classList.contains('slate-editor')) break;
                    n = n.parentElement;
                }
            }
            return 0;
        }""")

    async def _is_cursor_in_list(self) -> bool:
        """检测光标是否在列表项内（无序、有序、待办均检测）。"""
        return await self.page.evaluate("""() => {
            const LIST_SELECTORS = [
                '[data-slate-type="ul-item"]', '[data-slate-type="ul"]',
                '[data-slate-type="ol-item"]', '[data-slate-type="ol"]',
                '[data-slate-type="todo-item"]', '[data-slate-type="todo"]',
                '[data-slate-type="list-item"]',
                'li', 'ul', 'ol',
            ];
            const LIST_TYPES = new Set([
                'ul-item', 'ul', 'ol-item', 'ol',
                'todo-item', 'todo', 'list-item', 'li',
            ]);

            const sel = window.getSelection();
            if (sel && sel.anchorNode) {
                let node = sel.anchorNode.nodeType === 3
                    ? sel.anchorNode.parentElement : sel.anchorNode;
                while (node) {
                    if (node.matches && LIST_SELECTORS.some(s => node.matches(s)))
                        return true;
                    if (node.classList && node.classList.contains('slate-editor')) break;
                    node = node.parentElement;
                }
            }
            // 也检查 Slate fiber type
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return false;
            const fiberKey = Object.keys(ed).find(k => k.startsWith('__reactInternalInstance'));
            if (!fiberKey) return false;
            function findEditor(node, d) {
                if (!node || d > 30) return null;
                if (node.memoizedProps && node.memoizedProps.editor &&
                    node.memoizedProps.editor.marks !== undefined)
                    return node.memoizedProps.editor;
                return findEditor(node.child, d + 1);
            }
            const editor = findEditor(ed[fiberKey], 0);
            if (!editor || !editor.selection) return false;
            const idx = editor.selection.anchor.path[0];
            const block = editor.children[idx];
            return block && LIST_TYPES.has(block.type);
        }""")

    async def _ensure_ordered_list_starts_at_one(self) -> None:
        """若当前有序列表编号不从 1 开始，点击编号气泡 → 选择"开始新列表"。

        不做 fiber 预判（fiber 计数跨段落不准确）：
        直接 scrollIntoView + hover + 点击编号 span，
        若弹出框含"开始新列表"则点击，否则 Escape 放弃（说明已是 1 或不需要处理）。
        """
        await self.page.wait_for_timeout(300)
        await self.page.keyboard.press("Escape")  # 关掉任何悬浮层
        await self.page.wait_for_timeout(200)

        # 找编辑区左侧的编号 span，scrollIntoView 后 hover
        coords = await self.page.evaluate("""() => {
            const ed = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
            if (!ed) return null;
            const edRect = ed.getBoundingClientRect();
            const candidates = [...ed.querySelectorAll('span')].filter(el => {
                const t = (el.textContent || '').trim();
                if (!/^\d+\.?$/.test(t)) return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && (r.x - edRect.x) >= -60 && (r.x - edRect.x) < 80;
            });
            if (!candidates.length) return null;
            const last = candidates[candidates.length - 1];
            last.scrollIntoView({block: 'center'});
            const r = last.getBoundingClientRect();
            if (r.y < 0 || r.y > window.innerHeight) return null;
            return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
        }""")

        if not coords:
            log.debug("_ensure_ordered_list_starts_at_one: 未找到编号 span，跳过")
            return

        # hover 让气泡激活，再点击
        await self.page.mouse.move(coords["x"], coords["y"])
        await self.page.wait_for_timeout(400)
        await self.page.mouse.click(coords["x"], coords["y"])
        await self.page.wait_for_timeout(600)

        # 检查是否出现了编号设置弹窗（renumberContentContainer）
        # 注意：弹窗内部本身有 ant-input（"修改编号值"输入框），不要误判为全局搜索框
        popup_state = await self.page.evaluate("""() => {
            // 优先检查编号弹窗
            const popup = document.querySelector('.renumberContentContainer');
            if (popup) {
                const r = popup.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    // 找"开始新列表"按钮
                    for (const el of popup.querySelectorAll('*')) {
                        const t = (el.textContent || '').trim();
                        if (t === '开始新列表') {
                            const br = el.getBoundingClientRect();
                            if (br.width > 0 && br.height > 0)
                                return {kind: 'popup', x: Math.round(br.x + br.width/2), y: Math.round(br.y + br.height/2)};
                        }
                    }
                    return {kind: 'popup_no_btn'};
                }
            }
            // 没有弹窗，检查是否误触全局搜索框（排除 virtual-caret-input 和 ant-input 在 renumber 容器内）
            for (const el of document.querySelectorAll('input')) {
                if (el.closest('.renumberContentContainer')) continue;
                if (el.classList.contains('virtual-caret-input')) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 200 && r.height > 0) return {kind: 'search'};
            }
            return {kind: 'none'};
        }""")

        kind = popup_state.get("kind")
        if kind == "popup":
            # 点击"开始新列表"
            await self.page.mouse.click(popup_state["x"], popup_state["y"])
            await self.page.wait_for_timeout(400)
            log.info("_ensure_ordered_list_starts_at_one: 已点击'开始新列表'")
        elif kind == "popup_no_btn":
            # 弹窗出现但没有"开始新列表"（说明已经是第1项），Escape
            log.debug("_ensure_ordered_list_starts_at_one: 弹窗无'开始新列表'，已是第1项")
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(200)
        elif kind == "search":
            log.warning("_ensure_ordered_list_starts_at_one: 误触搜索框，Escape")
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
        else:
            # 没有任何弹出，说明编号不需要重置
            log.debug("_ensure_ordered_list_starts_at_one: 未出现弹窗，无需重置")
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(200)
