#!/bin/bash
# sync-to-git.sh — 将 Hermes 运行态源码同步到 GitHub 仓库
# 用法: bash ~/.hermes/scripts/sync-to-git.sh ["commit message"]
# 无参数时自动生成 commit message

set -e

REPO="/tmp/mojinxia-repo"
HERMES="$HOME/.hermes"
TIMESTAMP=$(date +%Y%m%d_%H%M)

# 1. 确保 repo 存在
if [ ! -d "$REPO/.git" ]; then
    echo "❌ Git 仓库不存在: $REPO"
    exit 1
fi

cd "$REPO"
git pull origin main 2>/dev/null || true

# 2. 存档当前 Hermes 状态
BACKUP_DIR="$REPO/.backup/$TIMESTAMP"
mkdir -p "$BACKUP_DIR/crons"

# 导出 CRON prompts
python3 -c "
import json
with open('$HERMES/cron/jobs.json') as f:
    data = json.load(f)
targets = ['摸金虾·盘前定调','摸金虾·午盘执行','摸金虾·午后侦察',
           '摸金虾·引擎一扫描','摸金虾·引擎二排名','摸金虾·尾盘执行','摸金虾·收盘复盘']
for j in data['jobs']:
    name = j.get('name','')
    if name in targets:
        short = name.replace('摸金虾·','')
        with open(f'$BACKUP_DIR/crons/{short}.md','w') as f:
            f.write(j.get('prompt',''))
        print(f'  backup: {short}.md')
" 2>/dev/null

echo "📦 快照: .backup/$TIMESTAMP"

# 3. 同步文件
# 设计文档
cp "$HERMES/products/摸金虾/"*.md docs/ 2>/dev/null

# Skill
mkdir -p skill/moni-sim-trading/references
cp "$HERMES/skills/finance/moni-sim-trading/SKILL.md" skill/moni-sim-trading/
cp "$HERMES/skills/finance/moni-sim-trading/references/"*.md skill/moni-sim-trading/references/ 2>/dev/null

# 脚本
SCRIPTS_DIR="$HERMES/scripts"
for f in moni_engine.py calc_risk_state.py engine2_ranker.py early_breakout_scanner.py \
         moni_check_trades.py next_trading_day.py scenario_audit.py premarket_image.py \
         sync-to-git.sh; do
    [ -f "$SCRIPTS_DIR/$f" ] && cp "$SCRIPTS_DIR/$f" scripts/
done

# 平衡计分卡（目录）
[ -d "$SCRIPTS_DIR/balanced_scorecard" ] && rm -rf scripts/balanced_scorecard && cp -r "$SCRIPTS_DIR/balanced_scorecard" scripts/
find scripts -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# CRON prompts（正式版，从 Hermes jobs.json 导出）
mkdir -p crons
python3 -c "
import json
with open('$HERMES/cron/jobs.json') as f:
    data = json.load(f)
targets = {
    '摸金虾·盘前定调':'盘前定调','摸金虾·午盘执行':'午盘执行','摸金虾·午后侦察':'午后侦察',
    '摸金虾·引擎一扫描':'引擎一扫描','摸金虾·引擎二排名':'引擎二排名',
    '摸金虾·尾盘执行':'尾盘执行','摸金虾·收盘复盘':'收盘复盘'
}
for j in data['jobs']:
    name = j.get('name','')
    if name in targets:
        short = targets[name]
        prompt = j.get('prompt','')
        schedule = j.get('schedule','')
        model = j.get('model','') or 'default'
        provider = j.get('provider','') or 'default'
        deliver = j.get('deliver','')
        content = f'# 摸金虾·{short}\n\n> schedule: \`{schedule}\` | model: \`{model}\` | provider: \`{provider}\` | deliver: \`{deliver}\`\n\n---\n\n{prompt}\n'
        with open(f'crons/{short}.md','w') as f:
            f.write(content)
        print(f'  export: {short}.md')
" 2>/dev/null

echo "📂 文件同步完成"

# 4. 检查 diff
if git diff --quiet && git diff --cached --quiet; then
    echo "✅ 无变更，跳过提交"
    exit 0
fi

# 5. 自动生成 commit message
if [ -n "$1" ]; then
    MSG="$1"
else
    # 从 changelog 提取最新版本号
    VER=$(head -20 docs/changelog.md | grep -oP 'v[\d.]+' | head -1)
    [ -z "$VER" ] && VER="v1.0"
    MSG="$VER: 自动同步 $(date +%Y-%m-%d)"
fi

# 6. 提交 + 推送
git add -A
git commit -m "$MSG"
git push origin main

echo "🚀 已推送: $MSG"
