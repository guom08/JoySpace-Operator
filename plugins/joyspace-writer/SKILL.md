---
name: joyspace-writer
description: "Write structured content (headings, paragraphs, highlight blocks, tables, dividers, colored/bold inline text) into a JoySpace document using Playwright automation. Use this skill whenever the user asks to write, replicate, or populate a JoySpace doc — triggered by phrases like: 'write to JoySpace', 'push this to JoySpace', 'replicate to JoySpace', '写到JoySpace', '写入JoySpace文档', '发到JoySpace', or any request that involves producing formatted content in a JoySpace page."
argument-hint: "<target-doc-url> [content-description]"
allowed-tools: [Bash, Read, Write, Edit]
---

# JoySpace Writer Skill

Automates writing formatted content into a JoySpace document via Playwright. The automation library lives at `/Users/guomu/JoySpace-Operator/`.

## Invocation

User provides:
- **Target doc URL** (required): e.g. `https://joyspace.jd.com/h/personal/pages/xxxxxxxx`
- **Content** (required): either structured data in the conversation, or a reference doc to replicate from

## Core Workflow

1. **Write a Python script** under `/Users/guomu/JoySpace-Operator/scripts/` (e.g. `write_<topic>.py`)
2. **Run it** and monitor output/screenshots
3. **Iterate** if any component fails

### Script Template

```python
#!/usr/bin/env python3
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
log = get_logger("write_<topic>")
SS = Path("/tmp/write_<topic>")
SS.mkdir(exist_ok=True)
_step = 0

TARGET_URL = "https://joyspace.jd.com/h/personal/pages/xxxxxxxx"

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

        # ── 重要：每次写新文档，必须先清空标题栏和正文，顺序不能颠倒 ──
        await w.set_title("")      # 1. 清空标题栏（传空字符串 = 恢复"无标题"占位）
        await w.clear()            # 2. 清空正文（Cmd+A × 2 → Backspace，循环直到字数为0）
        await w.focus()            # 3. 将焦点定位到正文编辑区第一行

        # 如果需要写标题，在 clear()/focus() 之后再调用 set_title()：
        # await w.set_title("我的文档标题")

        # --- write body content here ---

        await shot(page, "final")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### Running

```bash
cd /Users/guomu/JoySpace-Operator
python3 scripts/write_<topic>.py 2>&1
```

## DocumentWriter API

All methods are `async`. Call them in sequence on the `w = DocumentWriter(page)` instance.

### Block-level

| Method | Description |
|--------|-------------|
| `await w.set_title(title)` | 设置标题栏；传 `""` 清空为"无标题" |
| `await w.clear()` | 清空**正文**（循环 Cmd+A × 2 → Backspace，直到字数为 0） |
| `await w.focus()` | 将焦点定位到正文编辑区第一行 |
| `await w.heading(level, text)` | H1–H6；斜杠命令失败时自动回退到工具栏设置 |
| `await w.paragraph(text)` | Plain paragraph (auto Enter at end) |
| `await w.bullet_list(items, indent=0)` | 无序列表；items 可为 str 列表或 `{"text":…,"indent":N}` 列表 |
| `await w.divider()` | Horizontal rule via `/fgx` |
| `await w.quote(text)` | Block quote via `/yy` |
| `await w.highlight(content)` | Orange highlight block；主路径 `/ga`，失败自动回退 fiber；写完自动跳出 |
| `await w.table(rows, bold_header_row, bold_header_col, full_width, col_weights)` | Insert and fill a table |

> **清空文档的正确顺序**：`set_title("") → clear() → focus()`
> `clear()` 只清正文，不碰标题栏；`set_title()` 只改标题，不碰正文。两者必须分开调用。

### bullet_list 示例

```python
# 简单列表（全部一级）
await w.bullet_list(["要点一", "要点二", "要点三"])

# 带层级的列表
await w.bullet_list([
    {"text": "一级要点", "indent": 0},
    {"text": "二级子项", "indent": 1},
    {"text": "二级子项", "indent": 1},
    {"text": "一级要点", "indent": 0},
])
```

### Inline (no line break — use before `paragraph()` or `Enter`)

| Method | Description |
|--------|-------------|
| `await w.bold_inline(text)` | Bold text at current cursor |
| `await w.colored_inline(text, color)` | Colored text; supported colors below |

Supported colors for `colored_inline`:
```
"#232930"  (black)   "#999999"  (grey)    "#F5222D"  (red)
"#CF6F00"  (brown)   "#E5A001"  (yellow)  "#2EA121"  (green)
"#4C7CFF"  (blue)    "#7437DD"  (purple)  "#fff"     (white)
```

### table() signature

```python
await w.table(
    rows=[["Header A", "Header B"], ["row1a", "row1b"]],
    bold_header_row=True,    # grey bold first row
    bold_header_col=False,   # grey bold first col
    full_width=True,         # expand table to page width
    col_weights=[1, 3],      # relative column widths (None = auto-estimate)
)
```

## Key Constraints & Gotchas

### 清空文档：标题栏和正文必须分开处理
- `clear()` 仅清空正文（Slate 编辑区），不触碰标题栏
- `set_title("")` 仅清空标题栏，不触碰正文
- **每次写新文档的固定开头**：`set_title("") → clear() → focus()`，顺序不能颠倒
- 如果跳过 `set_title("")`，旧标题会残留，文档看起来像没有被清空

### Title bar colors
**NEVER apply colored_inline or bold_inline in the page title bar.** Color and bold only apply within the body editor area. The title bar is outside Slate and these operations have no effect / may cause errors.

### highlight() content
- Pass the full text content as a single string (multi-line with `\n` is fine)
- The slash alias is `/ga` (not `/glk` — that was wrong)
- After fiber insert, the code checks DOM; if the orange box isn't rendered it falls back to `/ga` automatically
- The block cursor exits automatically via Slate fiber

### table() ordering
- `_set_col_widths` runs **before** `_apply_table_toolbar` (full_width). This is intentional: set proportions first on the narrow table, then expand to full width.

### Hover trigger for table toolbar
- Table must be scrolled so its top edge is ≥ 350px from viewport top — the floating toolbar needs ~41px above the table to fully appear
- Mouse approach: move to `(tbl_x - 80, tbl_y - 10)` first (neutral, avoids font dropdown), then move to `(tbl_cx, tbl_y + 5)` to enter table top
- Button icon classes: `adaptivewidth` = full page width; `widthadaptive` = fit content

### Virtual caret textarea
- JoySpace routes keyboard events through `.ant-input.virtual-caret-input`
- After `bold_inline` or `colored_inline`, the code already restores focus to this textarea — no extra action needed

### Login
- The persistent browser context should already be logged in
  - macOS: `~/Library/Application Support/Google/Chrome/JoySpaceProfile/`
  - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data\JoySpaceProfile\`
  - 可通过环境变量 `CHROME_USER_DATA_DIR` 自定义路径
- If login is needed, `wait_for_login(page)` will pause and the user must scan the QR code

### Cross-platform support
- 键盘快捷键使用 Playwright 的 `ControlOrMeta` 修饰符，macOS 自动映射为 Cmd，Windows/Linux 映射为 Ctrl
- 浏览器数据目录根据 `sys.platform` 自动选择默认路径
- 迁移脚本：macOS/Linux 用 `migrate_joyspace_writer.sh`，Windows 用 `migrate_joyspace_writer.ps1`

## Screenshot Verification

After running, inspect screenshots in `/tmp/write_<topic>/`. Key things to verify:
1. `01_cleared.png` — editor is empty
2. `*_highlight.png` — orange border box visible (not plain text)
3. `*_table.png` — table spans full editor width; header row has grey background
4. `*_final.png` — full document visible, structure matches intent

## Common Failure Modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Highlight content written as plain text | fiber insert succeeded but DOM didn't re-render | Already handled: auto-fallback to `/ga` slash menu |
| Table not full width | `minTop=350` scroll not enough for very tall tables | Increase `minTop` in `_apply_table_toolbar` |
| Font dropdown opens during table hover | Neutral start position drifted into toolbar area (y ≈ 65) | Keep neutral at `(tbl_x - 80, tbl_y - 10)` |
| 0 toolbar buttons after col resize | Mouse left inside table from drag, then moved through font bar | Already fixed: neutral position avoids font bar |
| Content after highlight lands in wrong place | `_exit_highlight_block` fiber strategy returned False | Check if editor has `__reactInternalInstance` key; may need to clear doc and retry |
