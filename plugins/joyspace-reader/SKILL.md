---
name: joyspace-reader
description: "Read and extract content from a JoySpace document (headings, paragraphs, tables, highlight blocks, lists) into structured text or Markdown. Use this skill whenever the user asks to read, extract, or fetch content from a JoySpace doc — triggered by phrases like: 'read this JoySpace doc', 'extract content from JoySpace', 'fetch JoySpace page', '读取JoySpace', '读JoySpace文档', '提取JoySpace内容', '看看这个JoySpace', or any request that involves retrieving content from a JoySpace page URL."
argument-hint: "<joyspace-doc-url>"
allowed-tools: [Bash, Read, Write, Edit]
---

# JoySpace Reader Skill

Reads and extracts structured content from a JoySpace document via Playwright. The automation library lives at `/Users/guomu/JoySpace-Operator/`.

## Invocation

User provides:
- **JoySpace doc URL** (required): e.g. `https://joyspace.jd.com/pages/xxxxxxxx`

The skill returns the document content as structured Markdown (headings, paragraphs, tables, highlights, dividers) that can be used in the conversation.

## Core Workflow

1. **Write a Python script** under `/Users/guomu/JoySpace-Operator/scripts/` (e.g. `read_<topic>.py`)
2. **Run it** — script prints document content to stdout as Markdown
3. **Return the content** to the conversation

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
from joyspace_operator.document import open_doc, read_doc, blocks_to_markdown
from joyspace_operator.utils import get_logger

load_dotenv()
log = get_logger("read_joyspace")

TARGET_URL = "https://joyspace.jd.com/pages/xxxxxxxx"

async def main():
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx)
        await open_doc(page, TARGET_URL)
        await wait_for_login(page)
        await page.wait_for_timeout(2000)  # 等文档完全加载

        # 读取标题
        title = await page.evaluate("""() => {
            const el = document.querySelector('.page-title-content [contenteditable]') ||
                       document.querySelector('.sl-editor-container.show-title .sl-header-1');
            return el ? el.innerText.trim() : '';
        }""")

        # 读取正文内容
        blocks = await read_doc(page)
        md = blocks_to_markdown(blocks)

        print(f"# {title}")
        print()
        print(md)

        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Reader API

```python
from joyspace_operator.document import open_doc, read_doc, blocks_to_markdown, Block

# 打开文档
await open_doc(page, url)

# 读取结构化内容 → Block 列表
blocks = await read_doc(page)

# 转为 Markdown 字符串
md = blocks_to_markdown(blocks)
```

### Block types

| Type | Fields | Description |
|------|--------|-------------|
| `heading1` / `heading2` / `heading3` | `text`, `level` | H1-H3 标题 |
| `paragraph` | `text` | 普通段落（含列表文本） |
| `highlight` | `text` | 橙色高亮块 |
| `table` | `rows` (list of list) | 表格，rows[0] 通常是表头 |
| `divider` | — | 分割线 |
| `unknown` | `text` | 未识别的块 |

### blocks_to_markdown() output format

- Headings → `# / ## / ###`
- Highlights → `> 👉 text`
- Dividers → `---`
- Tables → pipe-separated Markdown table
- Paragraphs → plain text

## Key Constraints

### Login
- The persistent browser context should already be logged in
  - macOS: `~/Library/Application Support/Google/Chrome/JoySpaceProfile/`
  - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data\JoySpaceProfile\`
  - 可通过环境变量 `CHROME_USER_DATA_DIR` 自定义路径
- If login is needed, `wait_for_login(page)` will pause and the user must scan the QR code

### Loading wait
- 文档打开后需要等待 1-2 秒让 Slate 编辑器完全加载
- `read_doc()` 依赖 `.page-main-content .slate-editor.use-virtual-caret` 选择器
- 如果页面未完全加载，`read_doc()` 会返回空列表

### Content limitations
- 当前 reader 不解析列表层级（列表内容作为普通 paragraph 返回）
- 图片/附件/嵌入内容不被提取
- 代码块作为 paragraph 返回（暂不区分）

### Cross-platform
- 与 joyspace-writer 共享同一个代码库和浏览器持久化上下文
- 如果已部署 joyspace-writer，reader 无需额外安装依赖
