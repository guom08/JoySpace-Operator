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
log = get_logger("write_vla_classification")
SS = Path("/tmp/write_vla_classification")
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
        await shot(page, "cleared")
        await w.focus()

        rows = [
            ["机构",                   "产品",          "技术路线",       "说明"],
            ["Physical Intelligence",  "Pi0.7",         "Cascaded WAM",  ""],
            ["Nvidia",                 "GR00T N系列",   "Cascaded WAM",  ""],
            ["星动纪元",               "ERA-42",         "Cascaded WAM",  ""],
            ["智源研究院",             "UniVLA",         "Cascaded WAM",  ""],
            ["阿里达摩院",             "RynnVLA-002",   "Joint WAM",     ""],
            ["Figure AI",              "",              "传统 VLA",       ""],
            ["Boston Dynamics",        "",              "传统 VLA",       ""],
            ["Agility Robotics",       "",              "传统 VLA",       ""],
            ["千寻智能",               "",              "传统 VLA",       ""],
            ["原力灵机",               "",              "传统 VLA",       ""],
        ]

        await w.table(
            rows=rows,
            bold_header_row=True,
            bold_header_col=False,
            full_width=True,
            col_weights=[2, 2, 2, 3],
        )

        await shot(page, "final")
        log.info("写入完成")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
