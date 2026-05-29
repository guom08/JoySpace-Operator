#!/usr/bin/env python3
"""写入葡萄酒合作会议纪要到 JoySpace"""
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
log = get_logger("write_wine_meeting")
SS = Path("/tmp/write_wine_meeting")
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

        await w.set_title("")      # 1. 清空旧标题
        await w.clear()            # 2. 清空正文
        await w.set_title("【战略BD沟通纪要】食百-葡萄酒业务部 -260529")  # 3. 写实际标题
        await w.focus()            # 4. 最后把焦点定到正文区，之后不再碰标题栏
        await shot(page, "cleared")

        # ── 会议信息（高亮块，含会议纪要表格）
        await w.heading(2, "会议信息")

        await w.table(
            rows=[
                ["会议主题", "战略BD需求沟通-食百-葡萄酒业务部", "", ""],
                ["会议日期", "2026-05-29", "会议时间", "14:00-14:30"],
                ["会议地点", "C座15层", "", ""],
                ["参会人员", "章力，Cherry，文昊，李梦瑶", "", ""],
            ],
            bold_header_row=False,
            bold_header_col=True,
            full_width=True,
            col_weights=[1, 2, 1, 2],
        )
        await shot(page, "table_info")

        # ── 内容概述
        await w.heading(2, "内容概述")
        await w.paragraph(
            "本次会议围绕葡萄酒品类与海外优质酒庄的合作引进展开。"
            "ASC Fine Wines 在华代理资源丰富，双方已就扣点模式及独家渠道权益初步达成意向，"
            "预计本月底前完成合同框架确认。张裕旗下进口葡萄酒线正寻求线上渠道突破，"
            "合作谈判进展顺利，后续将重点对齐618促销资源。"
            "对于部分无中国分公司的小众精品酒庄（如 Penfolds 澳洲区直供批次），"
            "需通过赛夫协调总部完成供货授权，目前正在梳理授权文件清单。"
        )
        await shot(page, "overview")

        # ── 章节纪要
        await w.heading(2, "章节纪要")

        await w.heading(3, "1. ASC Fine Wines 合作进展")
        await w.paragraph(
            "ASC Fine Wines 作为在华最大精品葡萄酒代理商，目前已在平台有部分 SKU 在售，"
            "但覆盖深度不足。会议明确以「旗舰店直营+品牌专区」模式推进合作，"
            "扣点区间初步定为 18%–22%，品牌方对此表示接受。"
            "合同框架将于 2026-05-31 前完成确认，并在 618 前完成上线。"
        )

        await w.heading(3, "2. 张裕进口葡萄酒线线上渠道拓展")
        await w.paragraph(
            "张裕进口葡萄酒线（以爱斐堡、先锋系列为主）线下渠道饱和，急需线上增量。"
            "双方就 618 大促资源展开讨论，平台拟提供首页专题位及品类频道露出，"
            "张裕承诺提供不低于 15% 的价格让利及 5 万元品牌广告投放。"
            "后续由文昊对接张裕电商负责人，确认 SKU 清单及备货计划。"
        )

        await w.heading(3, "3. 精品小众酒庄授权问题")
        await w.paragraph(
            "对于 Penfolds 澳洲区直供批次等无中国分公司的精品酒庄，"
            "平台无法直接与其签署供货协议，需借助赛夫欧亚业务团队协调总部授权。"
            "会议决定由 Cherry 整理授权文件清单，下周提交赛夫，"
            "由赛夫以自上而下方式推动总部完成书面授权，预计 6 月中旬前到位。"
        )
        await shot(page, "sections")

        # ── 会议待办
        await w.heading(2, "会议待办")
        await w.todo_list([
            "Cherry 整理需总部授权的精品酒庄清单，下周三（6月5日）前提交赛夫对接",
            "文昊对接张裕电商负责人，确认 618 SKU 清单及备货计划，6月3日前回复",
            "BD团队完成 ASC Fine Wines 合同框架初稿，5月31日前发送品牌方确认",
        ])

        await shot(page, "final")
        log.info("写入完成")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
