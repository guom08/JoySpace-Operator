# ──────────────────────────────────────────────────────────
# JoySpace Operator 一键迁移脚本 (Windows PowerShell)（含 Writer + Reader）
# 在目标机器上运行，自动完成环境配置
# 前置条件：JoySpace-Operator 代码已复制到 ~/JoySpace-Operator
# 用法：powershell -ExecutionPolicy Bypass -File scripts\migrate_joyspace_writer.ps1
# ──────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"

function Info  ($msg) { Write-Host "[✓] $msg" -ForegroundColor Green }
function Warn  ($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail  ($msg) { Write-Host "[✗] $msg" -ForegroundColor Red; exit 1 }

$HomeDir     = $env:USERPROFILE
$OperatorDir = Join-Path $HomeDir "JoySpace-Operator"
$ClaudeDir   = Join-Path $HomeDir ".claude"
$PluginDir   = Join-Path $ClaudeDir "plugins\local\joyspace-writer"
$ReaderPluginDir = Join-Path $ClaudeDir "plugins\local\joyspace-reader"
$SettingsFile = Join-Path $ClaudeDir "settings.json"

Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  JoySpace Writer 迁移工具 (Windows)"
Write-Host "═══════════════════════════════════════════════"
Write-Host ""

# ── Step 0: 检查前置条件 ──
if (-not (Test-Path $OperatorDir)) {
    Fail "未找到 $OperatorDir，请先将代码复制到该目录：`ngit clone <仓库地址> ~/JoySpace-Operator"
}
Info "代码目录已就绪: $OperatorDir"

try {
    $pyVer = & python --version 2>&1
    Info "Python: $pyVer"
} catch {
    try {
        $pyVer = & python3 --version 2>&1
        Info "Python: $pyVer"
    } catch {
        Fail "未找到 python/python3，请先安装 Python 3.11+"
    }
}

# 确定 python 命令
$pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }

try {
    $claudeVer = & claude --version 2>&1
    Info "Claude Code CLI 已安装"
} catch {
    Warn "未检测到 claude 命令（Claude Code CLI），请确认已安装"
}

# ── Step 1: 安装 Python 依赖 ──
Write-Host ""
Write-Host "── Step 1: 安装 Python 依赖 ──"
Push-Location $OperatorDir
& $pythonCmd -m pip install -e . 2>&1 | Select-Object -Last 3
Pop-Location
Info "Python 依赖安装完成"

# ── Step 2: 安装 Playwright 浏览器 ──
Write-Host ""
Write-Host "── Step 2: 安装 Playwright 浏览器 ──"
& $pythonCmd -m playwright install chromium 2>&1 | Select-Object -Last 3
Info "Playwright Chromium 安装完成"

# ── Step 3: 创建 .env ──
Write-Host ""
Write-Host "── Step 3: 配置 .env ──"
$envFile = Join-Path $OperatorDir ".env"
if (Test-Path $envFile) {
    Warn ".env 已存在，跳过（如需修改请手动编辑）"
} else {
    @"
JOYSPACE_BASE_URL=https://joyspace.jd.com
LOG_LEVEL=INFO
"@ | Out-File -FilePath $envFile -Encoding utf8
    Info ".env 已创建"
}

# ── Step 4: 创建 Claude Code Plugin 目录结构 ──
Write-Host ""
Write-Host "── Step 4: 注册 Claude Code Plugin ──"
$pluginJsonDir = Join-Path $PluginDir ".claude-plugin"
$skillDir      = Join-Path $PluginDir "skills\joyspace-writer"
New-Item -ItemType Directory -Path $pluginJsonDir -Force | Out-Null
New-Item -ItemType Directory -Path $skillDir -Force | Out-Null

@"
{
  "name": "joyspace-writer",
  "description": "Write structured content into JoySpace documents using Playwright automation",
  "author": {
    "name": "joyspace-team"
  }
}
"@ | Out-File -FilePath (Join-Path $pluginJsonDir "plugin.json") -Encoding utf8
Info "plugin.json 已创建"

# ── Step 4b: 创建 Reader Plugin ──
$readerJsonDir = Join-Path $ReaderPluginDir ".claude-plugin"
$readerSkillDir = Join-Path $ReaderPluginDir "skills\joyspace-reader"
New-Item -ItemType Directory -Path $readerJsonDir -Force | Out-Null
New-Item -ItemType Directory -Path $readerSkillDir -Force | Out-Null

@"
{
  "name": "joyspace-reader",
  "description": "Read and extract structured content from JoySpace documents using Playwright automation",
  "author": {
    "name": "joyspace-team"
  }
}
"@ | Out-File -FilePath (Join-Path $readerJsonDir "plugin.json") -Encoding utf8

$readerSkillDst = Join-Path $readerSkillDir "SKILL.md"
$readerSources = @(
    (Join-Path $OperatorDir "plugins\joyspace-reader\SKILL.md"),
    (Join-Path $ClaudeDir "plugins\local\joyspace-reader\skills\joyspace-reader\SKILL.md")
)
foreach ($s in $readerSources) {
    if ((Test-Path $s) -and ($s -ne $readerSkillDst)) {
        $content = Get-Content $s -Raw
        $content = $content -replace "/Users/guomu/JoySpace-Operator", ($OperatorDir -replace "\\", "/")
        $content = $content -replace "/Users/guomu/", ($HomeDir -replace "\\", "/") + "/"
        $content | Out-File -FilePath $readerSkillDst -Encoding utf8
        break
    }
}
Info "joyspace-reader plugin 已创建"

# ── Step 5: 复制并替换 SKILL.md 中的路径 ──
Write-Host ""
Write-Host "── Step 5: 部署 SKILL.md（自动替换路径）──"
$skillDst = Join-Path $skillDir "SKILL.md"

# 查找 SKILL.md 源文件
$skillSources = @(
    (Join-Path $OperatorDir ".claude\plugins\local\joyspace-writer\skills\joyspace-writer\SKILL.md"),
    (Join-Path $ClaudeDir "plugins\local\joyspace-writer\skills\joyspace-writer\SKILL.md"),
    (Join-Path $ClaudeDir "skills\joyspace-writer\SKILL.md")
)
$sourcePath = $null
foreach ($s in $skillSources) {
    if ((Test-Path $s) -and ($s -ne $skillDst)) {
        $sourcePath = $s
        break
    }
}

if ($sourcePath) {
    $content = Get-Content $sourcePath -Raw
    $content = $content -replace "/Users/guomu/JoySpace-Operator", ($OperatorDir -replace "\\", "/")
    $content = $content -replace "/Users/guomu/", ($HomeDir -replace "\\", "/") + "/"
    $content | Out-File -FilePath $skillDst -Encoding utf8
    Info "SKILL.md 已部署（路径已替换为 $HomeDir）"
} elseif (Test-Path $skillDst) {
    $content = Get-Content $skillDst -Raw
    $content = $content -replace "/Users/guomu/JoySpace-Operator", ($OperatorDir -replace "\\", "/")
    $content = $content -replace "/Users/guomu/", ($HomeDir -replace "\\", "/") + "/"
    $content | Out-File -FilePath $skillDst -Encoding utf8
    Info "SKILL.md 路径已更新"
} else {
    Warn "未找到 SKILL.md 源文件，请手动复制到: $skillDst"
}

# ── Step 6: 更新 settings.json 启用 plugin ──
Write-Host ""
Write-Host "── Step 6: 启用 Plugin ──"
New-Item -ItemType Directory -Path $ClaudeDir -Force | Out-Null

if (-not (Test-Path $SettingsFile)) {
    @"
{
  "enabledPlugins": {
    "joyspace-writer@local": true,
    "joyspace-reader@local": true
  }
}
"@ | Out-File -FilePath $SettingsFile -Encoding utf8
    Info "settings.json 已创建并启用 plugin"
} else {
    $cfg = Get-Content $SettingsFile -Raw | ConvertFrom-Json
    if (-not $cfg.enabledPlugins) {
        $cfg | Add-Member -NotePropertyName "enabledPlugins" -NotePropertyValue @{} -Force
    }
    $changed = $false
    foreach ($p in @("joyspace-writer@local", "joyspace-reader@local")) {
        if ($cfg.enabledPlugins.$p -ne $true) {
            $cfg.enabledPlugins | Add-Member -NotePropertyName $p -NotePropertyValue $true -Force
            $changed = $true
        }
    }
    if ($changed) {
        $cfg | ConvertTo-Json -Depth 10 | Out-File -FilePath $SettingsFile -Encoding utf8
        Info "settings.json 已更新，plugin 已启用"
    } else {
        Info "plugin 已启用（之前已配置）"
    }
}

# ── 完成 ──
Write-Host ""
Write-Host "═══════════════════════════════════════════════"
Write-Host "  迁移完成！" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════"
Write-Host ""
Write-Host "  下一步："
Write-Host "  1. 启动 Claude Code（在任意目录运行 claude）"
Write-Host "  2. 输入: 写到 JoySpace 或 新建一个 JoySpace 文档"
Write-Host "  3. 首次运行会弹出京东登录二维码，用手机扫码登录"
Write-Host "     登录后状态会保存，之后无需再登录"
Write-Host ""
Write-Host "  文件位置："
Write-Host "  - 代码库:  $OperatorDir"
Write-Host "  - Plugin:  $PluginDir"
Write-Host "  - 配置:    $SettingsFile"
$browserDir = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data\JoySpaceProfile"
Write-Host "  - 浏览器:  $browserDir"
Write-Host ""
