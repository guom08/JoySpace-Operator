#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# JoySpace Writer 一键迁移脚本
# 在目标机器上运行，自动完成环境配置
# 前置条件：JoySpace-Operator 代码已复制到 ~/JoySpace-Operator
# ──────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

HOME_DIR="$HOME"
OPERATOR_DIR="$HOME_DIR/JoySpace-Operator"
CLAUDE_DIR="$HOME_DIR/.claude"
PLUGIN_DIR="$CLAUDE_DIR/plugins/local/joyspace-writer"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

echo ""
echo "═══════════════════════════════════════════════"
echo "  JoySpace Writer 迁移工具"
echo "═══════════════════════════════════════════════"
echo ""

# ── Step 0: 检查前置条件 ──
if [ ! -d "$OPERATOR_DIR" ]; then
    fail "未找到 $OPERATOR_DIR，请先将代码复制到该目录：
    git clone <仓库地址> ~/JoySpace-Operator
    或: scp -r guomu@source:~/JoySpace-Operator ~/JoySpace-Operator"
fi
info "代码目录已就绪: $OPERATOR_DIR"

if ! command -v python3 &>/dev/null; then
    fail "未找到 python3，请先安装 Python 3.11+"
fi
info "Python3: $(python3 --version)"

if ! command -v claude &>/dev/null; then
    warn "未检测到 claude 命令（Claude Code CLI），请确认已安装"
else
    info "Claude Code CLI 已安装"
fi

# ── Step 1: 安装 Python 依赖 ──
echo ""
echo "── Step 1: 安装 Python 依赖 ──"
cd "$OPERATOR_DIR"
pip3 install -e . 2>&1 | tail -3
info "Python 依赖安装完成"

# ── Step 2: 安装 Playwright 浏览器 ──
echo ""
echo "── Step 2: 安装 Playwright 浏览器 ──"
python3 -m playwright install chromium 2>&1 | tail -3
info "Playwright Chromium 安装完成"

# ── Step 3: 创建 .env ──
echo ""
echo "── Step 3: 配置 .env ──"
if [ -f "$OPERATOR_DIR/.env" ]; then
    warn ".env 已存在，跳过（如需修改请手动编辑）"
else
    cat > "$OPERATOR_DIR/.env" << 'ENVEOF'
JOYSPACE_BASE_URL=https://joyspace.jd.com
LOG_LEVEL=INFO
ENVEOF
    info ".env 已创建"
fi

# ── Step 4: 创建 Claude Code Plugin 目录结构 ──
echo ""
echo "── Step 4: 注册 Claude Code Plugin ──"
mkdir -p "$PLUGIN_DIR/.claude-plugin"
mkdir -p "$PLUGIN_DIR/skills/joyspace-writer"

cat > "$PLUGIN_DIR/.claude-plugin/plugin.json" << 'PJEOF'
{
  "name": "joyspace-writer",
  "description": "Write structured content into JoySpace documents using Playwright automation",
  "author": {
    "name": "joyspace-team"
  }
}
PJEOF
info "plugin.json 已创建"

# ── Step 5: 复制并替换 SKILL.md 中的路径 ──
echo ""
echo "── Step 5: 部署 SKILL.md（自动替换路径）──"
SKILL_SRC="$PLUGIN_DIR/skills/joyspace-writer/SKILL.md"

if [ -f "$OPERATOR_DIR/.claude/plugins/local/joyspace-writer/skills/joyspace-writer/SKILL.md" ]; then
    SOURCE_SKILL="$OPERATOR_DIR/.claude/plugins/local/joyspace-writer/skills/joyspace-writer/SKILL.md"
elif [ -f "$CLAUDE_DIR/plugins/local/joyspace-writer/skills/joyspace-writer/SKILL.md" ]; then
    SOURCE_SKILL="$CLAUDE_DIR/plugins/local/joyspace-writer/skills/joyspace-writer/SKILL.md"
elif [ -f "$CLAUDE_DIR/skills/joyspace-writer/SKILL.md" ]; then
    SOURCE_SKILL="$CLAUDE_DIR/skills/joyspace-writer/SKILL.md"
else
    SOURCE_SKILL=""
fi

if [ -n "$SOURCE_SKILL" ] && [ "$SOURCE_SKILL" != "$SKILL_SRC" ]; then
    sed "s|/Users/guomu/JoySpace-Operator|$OPERATOR_DIR|g; s|/Users/guomu/|$HOME_DIR/|g" \
        "$SOURCE_SKILL" > "$SKILL_SRC"
    info "SKILL.md 已部署（路径已替换为 $HOME_DIR）"
elif [ -f "$SKILL_SRC" ]; then
    sed -i.bak "s|/Users/guomu/JoySpace-Operator|$OPERATOR_DIR|g; s|/Users/guomu/|$HOME_DIR/|g" \
        "$SKILL_SRC" && rm -f "$SKILL_SRC.bak"
    info "SKILL.md 路径已更新"
else
    warn "未找到 SKILL.md 源文件，请手动复制到: $SKILL_SRC"
fi

# ── Step 6: 更新 settings.json 启用 plugin ──
echo ""
echo "── Step 6: 启用 Plugin ──"
mkdir -p "$CLAUDE_DIR"

if [ ! -f "$SETTINGS_FILE" ]; then
    cat > "$SETTINGS_FILE" << 'SJEOF'
{
  "enabledPlugins": {
    "joyspace-writer@local": true
  }
}
SJEOF
    info "settings.json 已创建并启用 plugin"
else
    if python3 -c "
import json, sys
with open('$SETTINGS_FILE') as f:
    cfg = json.load(f)
plugins = cfg.setdefault('enabledPlugins', {})
if plugins.get('joyspace-writer@local') is True:
    sys.exit(0)
plugins['joyspace-writer@local'] = True
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
sys.exit(2)
" 2>/dev/null; then
        info "plugin 已启用（之前已配置）"
    else
        info "settings.json 已更新，plugin 已启用"
    fi
fi

# ── 完成 ──
echo ""
echo "═══════════════════════════════════════════════"
echo -e "  ${GREEN}迁移完成！${NC}"
echo "═══════════════════════════════════════════════"
echo ""
echo "  下一步："
echo "  1. 启动 Claude Code（在任意目录运行 claude）"
echo "  2. 输入: 写到 JoySpace 或 新建一个 JoySpace 文档"
echo "  3. 首次运行会弹出京东登录二维码，用手机扫码登录"
echo "     登录后状态会保存，之后无需再登录"
echo ""
echo "  文件位置："
echo "  - 代码库:  $OPERATOR_DIR"
echo "  - Plugin:  $PLUGIN_DIR"
echo "  - 配置:    $SETTINGS_FILE"
echo "  - 浏览器:  ~/.config/playwright-joyspace/"
echo ""
