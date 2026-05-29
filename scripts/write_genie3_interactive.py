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
log = get_logger("write_genie3_interactive")
SS = Path("/tmp/write_genie3_interactive")
SS.mkdir(exist_ok=True)
_step = 0

TARGET_URL = "https://joyspace.jd.com/pages/49OA61gl7Mm8jqcz9O22"

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

        # 这个文档是 show-title 模式：标题在 Slate 第一行
        # set_title("") 会识别到 show-title 并清空第一行，clear() 清正文其余行
        await w.set_title("")
        await w.clear()
        await w.set_title("Genie 3：闭环交互还是视频生成？")
        await w.focus()
        await w.set_page_font("京东朗正体")
        await shot(page, "cleared")

        # ── 引言
        await w.paragraph(
            "是后者——机器人被放在里面主动尝试，不是被动看视频。"
            '这正是 Genie 系列论文名字里"Interactive"那个词的含义。'
        )
        await w.divider()

        # ── 第一节
        await w.heading(2, "Genie 3 的工作方式：闭环交互")
        await w.paragraph(
            "机器人发出动作 a_t\n"
            "      ↓\n"
            "Genie 3 根据（当前帧，动作）→ 生成下一帧\n"
            "      ↓\n"
            "机器人看到新帧，发出下一个动作 a_{t+1}\n"
            "      ↓\n"
            "循环往复"
        )
        await w.paragraph(
            "这是一个真正的闭环——机器人的行为影响世界，世界的变化影响机器人的下一个决策。"
            "这和 Sora/Wan 有本质区别。"
        )
        await w.divider()
        await shot(page, "section1")

        # ── 第二节
        await w.heading(2, "和 Sora/Wan 的根本区别：有没有动作条件化")
        await w.table(
            rows=[
                ["",      "Sora / Wan",            "Genie 3"],
                ["输入",  "文字/图像",              "当前帧 + 动作"],
                ["输出",  "一段完整视频",            "下一帧（实时响应）"],
                ["交互性", "无，生成完就结束",       "有，每步响应 agent 的行为"],
                ["用途",  "内容创作、数据增广",      "训练强化学习 agent"],
            ],
            bold_header_row=True,
            bold_header_col=True,
            full_width=True,
            col_weights=[2, 3, 3],
        )
        await w.paragraph(
            'Sora/Wan 生成的视频里"发生什么"完全由模型自己决定，你没有办法在视频播放到一半时'
            "让画面里的机械臂换个方向。Genie 3 的每一帧都是对 agent 上一个动作的响应。"
        )
        await w.divider()
        await shot(page, "section2")

        # ── 第三节
        await w.heading(2, "你的物理精度判断是对的")
        await w.paragraph(
            "因为 Genie 3 本质是视频模型，它的物理是视觉上合理，而不是几何上精确。"
        )
        await w.paragraph("具体表现：")
        await w.bullet_list([
            "物体运动轨迹看起来自然，但位置可能差几厘米",
            '接触点、摩擦力、重力效果是"学出来的视觉规律"，不是物理引擎算出来的',
            "长时间交互后场景一致性会下降（物体消失、形状变形）",
        ])
        await w.paragraph("现阶段比较适合的具身任务：")
        await w.bullet_list([
            "导航规划（走廊里找路、避开障碍物）：厘米级误差无所谓",
            "语义级操作（走到桌子旁边、打开柜子门）：动作粗粒度，视觉一致性够用",
            "多样场景泛化训练：最强项，可以无限生成新环境让 agent 探索",
        ])
        await w.paragraph("现阶段不太适合的任务：")
        await w.bullet_list([
            "灵巧手操作（拧螺丝、叠衣服）：需要毫米级精度，视频模型给不了",
            "接触密集任务（双手协作、精确插销）：物理接触建模不可靠",
            "需要精确力反馈的任务：视频里根本没有力这个维度",
        ])
        await w.divider()
        await shot(page, "section3")

        # ── 第四节
        await w.heading(2, "一个微妙之处值得补充")
        await w.paragraph(
            "Genie 3 目前用于机器人训练的主要方式，实际上两种都有，但侧重不同。"
        )
        await w.paragraph(
            "方式 A（真正的强化学习环境）：把 agent 放进去，让它用 RL 自由探索，"
            "学到策略后迁移。这是理想状态，但计算成本极高（每步都要运行视频扩散模型），"
            "而且长序列物理一致性还不够好。"
        )
        await w.paragraph(
            "方式 B（数据生成）：用 Genie 3 生成大量多样的场景视频，作为模仿学习的训练数据，"
            "而不是真的把 agent 放进去交互。这更接近 Waymo 实际的用法——用它生成各种罕见驾驶"
            "场景的视频数据，扩充数据集，而不是真的在里面跑 RL。"
        )
        await w.paragraph(
            '所以 Genie 3 现阶段更多是在做"高质量多样化数据引擎"，'
            '而不是"完全替代 MuJoCo/Isaac Sim 的物理仿真器"。'
            "真正要做精确物理仿真的任务，还是得用传统物理引擎（Isaac Sim、MuJoCo），"
            "Genie 3 的价值是在场景多样性和视觉真实感上补传统仿真器的短板，"
            "而不是在物理精度上替代它们。"
        )

        await shot(page, "final")
        log.info("写入完成")
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
