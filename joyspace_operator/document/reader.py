"""
reader.py — 读取 JoySpace 文档内容。
返回结构化的 block 列表，便于后续处理。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from playwright.async_api import Page

from joyspace_operator.utils import get_logger

log = get_logger(__name__)

BlockType = Literal["heading1", "heading2", "heading3", "paragraph", "highlight", "divider", "table", "unknown"]


@dataclass
class Block:
    type: BlockType
    text: str = ""
    level: int = 0        # 仅 heading 有效
    rows: list[list[str]] = field(default_factory=list)  # 仅 table 有效


async def read_doc(page: Page) -> list[Block]:
    """从已打开的文档中读取所有内容块，返回 Block 列表。"""
    raw = await page.evaluate("""() => {
        const editor = document.querySelector('.page-main-content .slate-editor.use-virtual-caret');
        if (!editor) return [];
        const results = [];
        for (const el of editor.children) {
            const cls = el.className || '';

            // 标题
            for (const [level, mark] of [[1,'sl-header-1'],[2,'sl-header-2'],[3,'sl-header-3']]) {
                if (cls.includes(mark)) {
                    results.push({type: 'heading' + level, text: el.innerText.trim(), level});
                    break;
                }
            }
            if (results.length && results[results.length-1].type?.startsWith('heading')) continue;

            // 高亮块
            if (cls.includes('sl-highlight-block')) {
                const editable = el.querySelector('[contenteditable]');
                results.push({type: 'highlight', text: editable?.innerText.trim() ?? ''});
                continue;
            }

            // 分割线
            if (cls.includes('sl-divider')) {
                results.push({type: 'divider'});
                continue;
            }

            // 表格
            const tbl = el.querySelector('table');
            if (tbl) {
                const rows = [];
                for (const tr of tbl.querySelectorAll('tr')) {
                    const cells = [];
                    for (const td of tr.querySelectorAll('td, th')) cells.push(td.innerText.trim());
                    if (cells.length) rows.push(cells);
                }
                results.push({type: 'table', rows});
                continue;
            }

            // 普通段落
            const txt = el.innerText.trim();
            if (txt) results.push({type: 'paragraph', text: txt});
        }
        return results;
    }""")

    blocks: list[Block] = []
    for item in raw:
        t = item.get("type", "unknown")
        if t.startswith("heading"):
            level = int(t[-1])
            blocks.append(Block(type=f"heading{level}", text=item.get("text", ""), level=level))
        elif t == "highlight":
            blocks.append(Block(type="highlight", text=item.get("text", "")))
        elif t == "divider":
            blocks.append(Block(type="divider"))
        elif t == "table":
            blocks.append(Block(type="table", rows=item.get("rows", [])))
        elif t == "paragraph":
            blocks.append(Block(type="paragraph", text=item.get("text", "")))
        else:
            blocks.append(Block(type="unknown", text=str(item)))

    log.info("读取到 %d 个 block", len(blocks))
    return blocks


def blocks_to_markdown(blocks: list[Block]) -> str:
    """将 Block 列表转换为 Markdown 字符串，便于阅读和调试。"""
    lines: list[str] = []
    for b in blocks:
        if b.type.startswith("heading"):
            lines.append("#" * b.level + " " + b.text)
        elif b.type == "highlight":
            lines.append(f"> 👉 {b.text}")
        elif b.type == "divider":
            lines.append("---")
        elif b.type == "table":
            if b.rows:
                lines.append(" | ".join(b.rows[0]))
                lines.append(" | ".join(["---"] * len(b.rows[0])))
                for row in b.rows[1:]:
                    lines.append(" | ".join(row))
        else:
            lines.append(b.text)
        lines.append("")
    return "\n".join(lines)
