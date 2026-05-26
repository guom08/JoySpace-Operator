#!/usr/bin/env python3
"""
scripts/write_tml_summary.py
────────────────────────────
将 21-Thinking-Machines-Lab-Interaction-Model总结.pdf 的内容
录入到 JoySpace 文档 https://joyspace.jd.com/pages/ypqSBeVkLZCuAicDPt4u

结构：
  标题栏  → 文档标题
  正文区  → H2/H3 + 段落 + 表格 + 引用块
"""
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

from joyspace_operator.browser import launch_persistent_context, get_page
from joyspace_operator.document import open_doc, DocumentWriter
from joyspace_operator.utils import get_logger

load_dotenv()
log = get_logger("write_tml")

DOC_URL = "https://joyspace.jd.com/pages/ypqSBeVkLZCuAicDPt4u"
SS = Path("/tmp/joyspace_screenshots")
SS.mkdir(exist_ok=True)
_step = 0


async def shot(page: Page, label: str) -> None:
    global _step
    _step += 1
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(200)
    p = SS / f"{_step:02d}_{label}.png"
    await page.screenshot(path=str(p), full_page=True)
    log.info("截图 → %s", p.name)


async def write_title(page: Page, text: str) -> None:
    """将文字写入标题栏（.page-title-below），不触碰正文编辑区。
    直接点击标题栏、清空、输入——不需要斜杠命令，标题栏会自动格式化。
    """
    # 用 locator force=True 确保点到标题栏，绕过任何遮挡层
    title_loc = page.locator(".page-title-below").first
    try:
        await title_loc.click(force=True, timeout=3000)
    except Exception:
        # 备用：坐标点击
        coords = await page.evaluate("""() => {
            const el = document.querySelector('.page-title-below');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: Math.round(r.x + r.width * 0.15),
                    y: Math.round(r.y + r.height / 2)};
        }""")
        if coords:
            await page.mouse.click(coords["x"], coords["y"])
    await page.wait_for_timeout(300)

    # 清空现有标题，直接输入新标题
    await page.keyboard.press("Meta+a")
    await page.wait_for_timeout(150)
    await page.keyboard.type(text, delay=12)
    await page.wait_for_timeout(300)
    log.info("标题栏写入: %s", text[:60])


async def focus_body(page: Page) -> None:
    """保留此函数签名以免调用方报错，实际已被 w.focus() 替代。"""
    pass


# ──────────────────────────────────────────────
#  正文写入
# ──────────────────────────────────────────────

async def write_content(page: Page, w: DocumentWriter) -> None:

    # ── 公司背景
    await w.heading(2, "公司背景")
    await w.paragraph(
        "Thinking Machines Lab 由前 OpenAI CTO Mira Murati 于2025年初创立，"
        "创始团队三分之二来自 OpenAI，成立之初即被视为最具潜力的 OpenAI 竞争者之一。"
    )
    await w.table([
        ["时间",          "事件"],
        ["2025年初",      "创立，创始团队含 Barret Zoph（CTO）、Luke Metz 等六位联创"],
        ["2025年7月",     "完成 $20亿 种子轮，估值 $120亿，NVIDIA 参与"],
        ["2025年11月",    "洽谈以 $500亿 估值再融资"],
        ["2026年1月",     "CTO Barret Zoph 及联创 Luke Metz 离职回归 OpenAI，约50%员工流失"],
        ["2026年5月11日", "发布首个自研模型 TML-Interaction-Small（研究预览版）"],
    ], col_weights=[2, 8])
    await shot(page, "company_bg")

    # ── 核心主张
    await w.heading(2, "核心主张：什么是 Interaction Model")
    await w.paragraph(
        "TML 的出发点是批判现有模型的结构缺陷：当前前沿模型为轮次交互（Turn-Based）设计，"
        "实时交互能力是事后用外部脚手架拼凑出来的，而非模型本身的原生能力。"
        "TML 称这种外挂式实时能力为 Harness（束缚架）。"
    )
    await w.quote(
        "「当前模型即便用于交互式同步操作，效果也不理想。"
        "我们认为交互性应当与智能一起扩展，而不是事后补丁。」—— TML 官方博客"
    )
    await w.paragraph(
        "Interaction Model 的目标：让交互能力和智能能力从训练阶段就融为一体，"
        "实现真正的人机协作，而非问答轮替。"
    )
    await shot(page, "core_claim")

    # ── 技术架构
    await w.heading(2, "TML-Interaction-Small 技术架构")
    await w.table([
        ["参数",       "数值"],
        ["总参数量",   "276B"],
        ["激活参数量", "12B（MoE 架构，每次激活部分专家）"],
        ["架构类型",   "Mixture-of-Experts，全双工"],
        ["输入模态",   "音频 + 视频 + 文本，同时处理"],
        ["处理粒度",   "200ms 微轮次（Micro-Turn）"],
    ], col_weights=[3, 7])
    await shot(page, "arch_table")

    await w.heading(3, "三个关键架构设计")
    await w.paragraph(
        "多流微轮次（Multi-Stream Micro-Turn）：不等用户说完即开始处理，"
        "每 200ms 切一个感知窗口，持续输入、持续思考、持续输出，类似人类边听边想。"
    )
    await w.paragraph(
        "全双工（Full Duplex）：模型说话的同时继续监听，可在回答过程中实时察觉并响应用户打断；"
        "现有模型说话时停止监听（半双工）。"
    )
    await w.paragraph(
        "并行工具调用：模型通过输出流中嵌入结构化 token 触发工具，"
        "多个工具可同时执行而非顺序排队——Agent 场景的关键性能差异。"
    )
    await w.paragraph(
        "Time Awareness：原生感知当前时间，无需外部 system prompt 注入。"
    )
    await shot(page, "arch_design")

    # ── 与现有模型对比
    await w.heading(2, "与现有模型的对比")

    await w.heading(3, "响应延迟（FD-bench v1 Turn-Taking Latency）")
    await w.table([
        ["模型",                    "响应延迟", "对比"],
        ["TML-Interaction-Small",   "0.40s",   "基准（最快）"],
        ["Gemini 3.1 Flash Live",   "0.57s",   "+43%"],
        ["GPT-Realtime-1.5",        "0.59s",   "+48%"],
        ["GPT-Realtime-2.0",        "1.18s",   "+195%"],
    ], col_weights=[4, 2, 2])
    await w.paragraph(
        "TML 延迟接近人类自然对话节奏（0.2–0.5s），GPT-Realtime-2.0 慢近 3 倍。"
    )

    await w.heading(3, "综合能力（FD-bench v3，Audio + Tools）")
    await w.table([
        ["模型",                    "Response Quality", "Pass@1"],
        ["TML-Interaction-Small",   "82.8%",            "68.0%"],
        ["GPT-Realtime-2.0",        "—",                "52.0%"],
        ["Gemini Live",             "N/A",              "N/A"],
    ], col_weights=[4, 3, 2])
    await shot(page, "comparison")

    # ── 关键改进对比总结
    await w.heading(2, "关键改进对比总结")
    await w.table([
        ["维度",         "传统模型",                    "TML-Interaction-Small"],
        ["交互范式",     "轮次制，等用户说完处理",       "全双工，边听边说边思考"],
        ["实时能力来源", "外挂 VAD + 对话管理组件",      "原生训练进模型"],
        ["响应延迟",     "0.57s ～ 1.18s",              "0.40s"],
        ["工具调用",     "串行排队",                    "并行同时执行"],
        ["时间感知",     "依赖 system prompt 注入",      "原生感知当前时间"],
        ["打断处理",     "半双工，说话时停止监听",        "说话时继续监听，实时响应打断"],
    ], col_weights=[3, 4, 4])
    await shot(page, "summary_table")

    # ── 背景注意事项
    await w.heading(2, "背景注意事项")
    await w.paragraph(
        "当前发布为 Research Preview（研究预览），非正式产品；"
        "广泛可用版本计划2026年晚些时候推出。"
    )
    await w.paragraph(
        "发布前公司经历大规模人员流失（含 CTO），此次发布带有向外界证明技术存续的信号意义。"
    )
    await w.paragraph(
        "TML 自主设计了 FD-bench 基准，部分评测维度（如视觉主动性任务）"
        "现有模型无法参与——需关注基准自评的客观性。"
    )
    await w.paragraph(
        "核心技术方向（全双工原生实时交互）与 OpenAI、Google 均不同，"
        "若工程稳定性验证通过，有望定义新一代人机交互范式。"
    )
    await shot(page, "notes")

    log.info("全部内容写入完成，截图保存在 %s", SS)


# ──────────────────────────────────────────────
#  主入口
# ──────────────────────────────────────────────

async def main() -> None:
    async with async_playwright() as pw:
        ctx = await launch_persistent_context(pw)
        page = await get_page(ctx)

        await open_doc(page, DOC_URL)
        await shot(page, "opened")

        w = DocumentWriter(page)

        # 1. 清空正文
        await w.clear()
        await shot(page, "cleared")

        # 2. 写文档标题（标题栏，不是正文区第一行）
        await write_title(page, "Thinking Machines Lab Interaction Model 发布总结")
        await shot(page, "title_done")

        # 3. 点击正文编辑区，让后续写入落在正文
        await w.focus()

        # 4. 写正文
        await write_content(page, w)

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
