# 摸金虾 开发手册

> 本文档定义摸金虾的迭代节奏、版本管理规范和回滚流程。适用于 v1.0+。

---

## 一、迭代节奏

### 三层节奏

| 层级 | 频率 | 做什么 | 不改什么 |
|------|------|--------|---------|
| **盯盘** | 每日 15:05 后 | 检查 CRON 健康 / 策略一致性 / 硬约束穿透。记录异常到 `issues.json` | 不改代码 |
| **审计+排期** | 每周六 | 跑计分卡 + Scenario 审计 + issues 排期 + 集中改 | — |
| **大版本** | 每月末 | 月目标核算 + 回溯总结 + roadmap 刷新 | — |

### 每日盯盘三信号

| 信号 | 看什么 | 红灯条件 |
|------|--------|:----:|
| CRON 健康 | `cronjob list` → `last_status` + `last_delivery_error` | 任一非 `ok` |
| 策略一致性 | `risk_state.level` vs `current_strategy.mode` | 不一致 |
| 硬约束穿透 | `execution_log` 中 `deviation` 非 null | 有偏离 |

三个全绿 → 无需操作。有红灯 → 记入 `~/.hermes/cron/state/moni/issues.json`，不当天修。

### 每周六流程

1. **计分卡**：`python3 ~/.hermes/scripts/balanced_scorecard --format markdown`
2. **Scenario 审计**：`python3 ~/.hermes/scripts/scenario_audit.py`（触达率 < 30% → 标记）
3. **Issues 排期**：

| 严重度 | 含义 | 处理 |
|:---:|------|------|
| P0 | 影响当天交易正确性 | 立即 hotfix |
| P1 | 影响下周交易质量 | 周六改，周日验证 |
| P2 | 体验/洞察提升 | 排到下周六 |
| P3 | 远期 | 放 roadmap 清单 |

4. **集中改**：改 CRON prompt → 改脚本 → 更新 skill → `cronjob run` 验证

### 变更安全规则

- **盘中不改**：09:00-15:05 窗口内不修改任何 CRON prompt
- **改完必验证**：`cronjob run` 或用当天数据生成样图
- **双写**：改 CRON prompt 同时更新 `moni-sim-trading` skill
- **改 ≥3 个 CRON → 次版本号 +1**

---

## 二、版本管理

### 版本号规则

```
v<主版本>.<次版本>.<修订号>

主版本：架构重构、策略链大改     → 2.0
次版本：新功能、≥3 个 CRON 改动  → 1.1
修订号：单 CRON bugfix、脚本修复  → 1.0.1
```

### 同步机制

Hermes 是运行态源码，GitHub 是版本镜像。通过 `sync-to-git.sh` 一键同步：

```bash
~/.hermes/scripts/sync-to-git.sh
```

做的事：
1. 从 Hermes 各目录 cp 最新文件到 git 仓库
2. 检查 diff，无变化则跳过
3. 自动导出当前 7 个 CRON prompt 到 `crons/`
4. 存档当前 Hermes 状态到 `.backup/YYYYMMDD_HHMM/`

### Commit 规范

```
v<版本号>: <一句话总结>

- <改动1>
- <改动2>
```

例：
```
v1.0.1: 修复午盘执行风险等级显示 + 引擎二脚本异常处理

- 午盘执行：补回 risk_state.level 显示
- 引擎二：engine2_ranker.py 增加 mx_xuangai 失败降级
```

### 发布 Checklist

```
[ ] 所有改动 CRON 已 cronjob run 验证
[ ] skill SKILL.md 已同步更新
[ ] changelog.md 已追加新版本条目
[ ] roadmap.md 已完成项划掉
[ ] sync-to-git.sh 执行无 diff 残留
[ ] git commit 含版本号 + 改动摘要
[ ] git tag v1.x.x
[ ] git push --tags
[ ] issues.json 已关闭条目移到 done
```

---

## 三、回滚流程

### 场景 A：单个 CRON prompt 回滚

```bash
# 1. 从 Git 历史拿旧版本
cd /tmp/mojinxia-repo
git log --oneline crons/午盘执行.md

# 2. 提取内容
git show <commit>:crons/午盘执行.md

# 3. 回灌到 Hermes
# 用 cronjob update 把旧 prompt 写回去
```

### 场景 B：脚本回滚

```bash
cd /tmp/mojinxia-repo
git checkout v1.0.0 -- scripts/engine2_ranker.py
cp scripts/engine2_ranker.py ~/.hermes/scripts/
```

### 场景 C：利用 .backup 快照回滚

每次 `sync-to-git.sh` 自动在 `.backup/` 留 Hermes 运行态快照：

```bash
cd /tmp/mojinxia-repo
ls .backup/                          # 找到目标时间点
cp .backup/20260603_0930/crons/* crons/
```

### 回滚后必做

```
[ ] cronjob run 验证回滚后的 CRON
[ ] changelog 标注 [REVERTED]，说明回退原因和回退至哪个版本
[ ] 根因分析 → 写入 issues.json
[ ] 发修订版本号（如 v1.1.0 → v1.1.1）
```

### 回滚安全原则

| 原则 | 说明 |
|------|------|
| 盘中不回滚 | 09:00-15:05 不改任何 CRON |
| 单 CRON 优先 | 一个有问题就回滚一个，不牵连 |
| 回滚也是版本 | 发新版本号，不删旧 tag |
| Git tag 不可删 | 即使版本有问题，tag 保留 |

---

## 四、关键文件路径

| 文件 | 路径 | 用途 |
|------|------|------|
| issues | `~/.hermes/cron/state/moni/issues.json` | 待修复清单 |
| changelog | `~/.hermes/products/摸金虾/changelog.md` | 版本历史 |
| roadmap | `~/.hermes/products/摸金虾/roadmap.md` | 路线图 |
| 本手册 | `~/.hermes/products/摸金虾/DEVELOPMENT.md` | 开发流程 |
| skill | `~/.hermes/skills/finance/moni-sim-trading/SKILL.md` | 操作手册 |
| git repo | `/tmp/mojinxia-repo` | 本地 git 仓库 |
| sync 脚本 | `~/.hermes/scripts/sync-to-git.sh` | Hermes → Git 同步 |
