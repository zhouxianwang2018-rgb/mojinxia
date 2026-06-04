# 摸金虾 · 复刻指南（SETUP）

> v1.1 · 2026-06-04

从零搭建摸金虾模拟盘交易系统。

## 一、前置条件

| 依赖 | 版本 | 用途 |
|:--|:--|:--|
| Hermes Agent | >= v0.15.1 | AI Agent 框架，提供 CRON/skill/工具调度 |
| Python | >= 3.11 | 脚本运行环境 |
| Node.js | >= 22 | Playwright 截图依赖 |
| snap chromium | 148.x | 报纸图片渲染 |
| Git | 任意 | 代码同步 |

## 二、API Key 配置

写入 `~/.hermes/.env`：

| Key | 用途 | 获取方式 |
|:--|:--|:--|
| `EM_API_KEY` | 妙想金融数据（行情/财务/选股/宏观） | https://ai.eastmoney.com/mxClaw |
| `DEEPSEEK_API_KEY` | LLM 推理（deepseek-v4-pro） | https://platform.deepseek.com |
| `QQBOT_APP_ID` | QQ Bot 应用 ID | https://q.qq.com |
| `QQBOT_CLIENT_SECRET` | QQ Bot 密钥 | https://q.qq.com |

## 三、安装

```bash
# 1. Hermes Agent
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# 2. Python 依赖
pip install httpx pandas openpyxl

# 3. 系统依赖（poppler-utils 用于 pdf2image）
sudo apt-get install -y poppler-utils
sudo snap install chromium

# 4. 克隆摸金虾仓库
git clone https://github.com/zhouxianwang2018-rgb/mojinxia.git /tmp/mojinxia-repo

# 5. 安装技能
cp -r /tmp/mojinxia-repo/skill/moni-sim-trading ~/.hermes/skills/finance/moni-sim-trading

# 6. 安装脚本
cp /tmp/mojinxia-repo/scripts/*.py ~/.hermes/scripts/
cp /tmp/mojinxia-repo/scripts/sync-to-git.sh ~/.hermes/scripts/

# 7. 确认 Playwright 可访问 snap chromium
~/.hermes/hermes-agent/node_modules/.bin/playwright --version
```

## 四、初始化运行时目录

```bash
mkdir -p ~/.hermes/cron/state/moni/strategies
mkdir -p ~/.hermes/cron/state/moni/risk
mkdir -p ~/.hermes/tmp/premarket

# 策略索引（首个交易日）
cat > ~/.hermes/cron/state/moni/strategy_index.json << 'EOF'
{
  "current_trading_day": "YYYY-MM-DD",
  "active_strategy": "YYYY-MM-DD",
  "chain": ["YYYY-MM-DD"],
  "last_closed_day": null,
  "market_status": "pre_open"
}
EOF

# 初始持仓（100万模拟资金）
cat > ~/.hermes/cron/state/moni/holdings.json << 'EOF'
{
  "total_asset": 1000000,
  "cash": 1000000,
  "positions": {},
  "peak_total": 1000000,
  "drawdown_from_peak": 0,
  "consecutive_loss_days": 0
}
EOF
```

## 五、创建 CRON 作业

7 条完整 cronjob 创建命令见 [cron-commands.md](cron-commands.md)。

## 六、验证

```bash
hermes cron list | grep 摸金虾          # 确认 7 条作业
hermes cron run <盘前定调 job_id>        # 手动触发测试
ls ~/.hermes/cron/output/               # 检查输出
```

## 七、关键路径速查

| 内容 | 路径 |
|:--|:--|
| 策略文件 | `~/.hermes/cron/state/moni/strategies/YYYY-MM-DD.json` |
| 策略索引 | `~/.hermes/cron/state/moni/strategy_index.json` |
| 持仓 | `~/.hermes/cron/state/moni/holdings.json` |
| Cron 输出 | `~/.hermes/cron/output/<job_id>/` |
| 脚本 | `~/.hermes/scripts/` |
| 技能 | `~/.hermes/skills/finance/moni-sim-trading/` |
| 报纸图片 | `~/.hermes/tmp/premarket/` |
