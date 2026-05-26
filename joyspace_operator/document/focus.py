"""
focus.py — 主编辑区焦点管理。

核心问题：JoySpace 使用 Slate use-virtual-caret 模式，编辑器渲染自己的
虚拟光标，不依赖浏览器原生 Selection API。因此 window.getSelection() 不
可靠，改为用 document.activeElement 是否在主编辑区内来判断焦点。
"""
from __future__ import annotations

from playwright.async_api import Page

from joyspace_operator.utils import get_logger

log = get_logger(__name__)

EDITOR_SEL = ".page-main-content .slate-editor.use-virtual-caret"

# 返回 true 表示 activeElement 在主编辑区内
_JS_CHECK = """() => {
    const editor = document.querySelector(
        '.page-main-content .slate-editor.use-virtual-caret'
    );
    if (!editor) return false;
    const active = document.activeElement;
    if (!active) return false;
    return editor === active || editor.contains(active);
}"""

# 返回编辑区正文 block 的中心坐标（跳过标题 block）
_JS_BODY_CENTER = """() => {
    const editor = document.querySelector(
        '.page-main-content .slate-editor.use-virtual-caret'
    );
    if (!editor) return null;
    // 优先找第二个 block（正文起始），没有就用整个编辑区中部
    const blocks = editor.querySelectorAll('[data-slate-node="element"]');
    const target = blocks[1] || blocks[0] || editor;
    const r = target.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) {
        const er = editor.getBoundingClientRect();
        return {x: er.x + er.width / 2, y: er.y + 200};
    }
    return {x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 40)};
}"""


async def focus_main_editor(page: Page, retries: int = 3) -> None:
    """将焦点定位到主编辑区，失败时最多重试 retries 次。"""
    for attempt in range(1, retries + 1):
        # page.click() 比 dispatchEvent 更可靠（走完整的 pointer 事件链）
        coords = await page.evaluate(_JS_BODY_CENTER)
        if coords:
            await page.mouse.click(coords["x"], coords["y"])
        else:
            # fallback：直接 click CSS selector
            try:
                await page.click(EDITOR_SEL, timeout=2000)
            except Exception:
                pass

        await page.wait_for_timeout(400)

        if await page.evaluate(_JS_CHECK):
            log.debug("焦点定位成功（attempt %d）", attempt)
            return

        log.warning("焦点定位失败（attempt %d/%d）", attempt, retries)

    # 最后强制 focus：直接调用 JS .focus()
    await page.evaluate("""() => {
        const ed = document.querySelector(
            '.page-main-content .slate-editor.use-virtual-caret'
        );
        if (ed) ed.focus();
    }""")
    await page.wait_for_timeout(300)
    log.warning("已强制调用 editor.focus()，继续写入")


async def verify_focus(page: Page) -> bool:
    """检查当前焦点是否在主编辑区。"""
    return bool(await page.evaluate(_JS_CHECK))
