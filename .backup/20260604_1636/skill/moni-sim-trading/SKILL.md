---
name: moni-sim-trading
description: 摸金虾模拟盘交易系统的架构设计、策略链机制、多CRON接力协调、风控体系和运维规范。
---

# 摸金虾模拟盘 · 架构与运维

> 产品设计文档见 `~/.hermes/products/摸金虾/`

## 量化目标（2026-05-29 设定）

| 维度 | 目标 | 当前进度 |
|------|------|---------|
| **年目标** | 2026年最后一个交易日收盘资产 ≥ ¥2,000,000（+100%） | ~¥1,110,000（+11%） |
| **月目标** | 每月增长率 ≥ 15% | 待核算 |

**月复合路径（15% 月增长）：**
```
5月底 ~111万 → 6月 127.7万 → 7月 146.8万 → 8月 168.8万 → 9月 194.1万 → 10月 223万
```
200 万里程碑预计在 **9 月中下旬** 触及。

**考核规则：**
- 每月最后一个交易日收盘复盘，输出当月增长率 vs 15% 目标
- 月末未达标 → 强制深度复盘，输出偏差根因和改进方案
- 每日/每周复盘输出「距月目标差距」和「年化进度百分比」

## 触发条件
- 创建、修改、调试摸金虾模拟盘相关的CRON任务
- 调整风控参数、止损线、仓位约束
- 跨CRON策略协调问题
- 复盘分析系统性缺陷
- 新增或重构模拟盘流水线中的任意一环

## 架构概览

### 七道接力流水线（含模型分配 + 数据流）🆕 v5 侦察收敛

```
        策略层                    侦察层                     执行层
    ┌──────────────┐       ┌──────────────┐       ┌─────────────────────┐
    │ 收盘复盘(15:05)│       │              │       │                     │
    │ 创建T+1蓝图    │       │              │       │                     │
    │ 盘前定调(09:00)│       │ 午后侦察(13:16)│       │ 午盘执行(10:00)      │
    │ 微调+写语境    │       │ 侦察+快照+追加 │       │ 读语境→执行          │
    └──────┬───────┘       └──────┬───────┘       │ 尾盘执行(14:35)      │
           │                      │               │ 读快照→执行          │
           ▼                      ▼               └─────────────────────┘
    market_context         market_snapshot                 │
    (盘前主线/偏向)         (指数/板块/异动/建议)            ▼
           │                      │               execution_log
           └──────────────────────┼───────────────────┘
                                  │
    引擎一扫描(14:20) ──→ 引擎二排名(14:25) ──→ ranked
         三阶段扫描        选股+交叉排名     ──→ 收盘复盘自动生成scenarios
```

**数据流关键**：盘前(09:00)写 `market_context` → 午盘(10:00)读 → 午后(13:16)写 `market_snapshot` → 尾盘(14:35)读。引擎扫描(14:22)顺序执行：early_breakout_scanner.py → engine2_ranker.py → 写入 engine_tracker.json → 双引擎报纸图。所有数据通过策略文件传递，不使用 `context_from` 注入。

### 交付格式标准

**📰 报纸风格（盘前分析 + 引擎扫描 + 收盘复盘）：**
- 渲染引擎：Playwright + snap chromium（路径探测：snap → 系统 → bundled）
- 沙箱参数：`--no-sandbox --disable-setuid-sandbox`
- 字体：系统本地 Noto CJK（`Noto Serif CJK SC` / `Noto Sans CJK SC`），不从 Google Fonts CDN 加载
- 输出目录：`~/.hermes/tmp/premarket/`（snap chromium 沙箱兼容）
- 生成脚本：`python3 ~/.hermes/scripts/premarket_image.py --type {premarket|close|rank|weekly} <markdown_file>`
  - `premarket` — 盘前早参（报头「摸金虾·盘前早参」）
  - `close` — 收盘复盘（报头「摸金虾·收盘复盘」）
  - `rank` — 引擎扫描（报头「摸金虾·引擎扫描」，含双引擎合并布局）
  - `weekly` — 周度复盘
- 引擎扫描报纸为双引擎合并布局：引擎一 STAGE3 + STAGE2 表格 + 引擎二排名表格 + 交叉命中 + 策略约束
- 详见 `references/newspaper-image-generation.md`

**📝 精简文本（午盘执行 / 午后侦察 / 尾盘执行）：**
- **午盘执行**：≤5行。只报风险等级+仓位+操作（有则逐笔，无则说明原因）。不报大盘/板块/账户（盘前已报，午后更新）
- **午后侦察**：短文本。标题行（总资产+仓位+预警数）+ 告警详情 + 结论
- **尾盘执行**：纯文本。操作列表+持仓一览+决策逻辑一句话
- 格式规范见各CRON prompt 中的「交付格式」章节

**🔇 内部流转（引擎一扫描）：**
- `deliver: local`，输出仅保存到本地归档
- 引擎一将扫描结果写入策略文件 `candidate_pool.engine1`（STAGE3/STAGE2 + 过滤 + 时间戳）
- 引擎二从策略文件读取 `candidate_pool.engine1`，排名后写入 `candidate_pool.engine2.ranked`
- 尾盘执行/收盘复盘从策略文件读取 `candidate_pool`——不通过 `context_from` 注入

### 15:00 错峰排布（避免 API 资源竞争）

```
15:02  韬产业链·收盘汇报（18只标的）
15:05  摸金虾收盘复盘 ⭐（最关键）
```

车牌跟踪 cron 已迁移至 17:00+ 窗口，与收盘复盘错峰：

```
17:00  车牌#2026-05-22
17:03  车牌#2026-05-26
17:06  车牌#2026-05-28
17:09  车牌#2026-05-29
17:12  车牌#2026-05-19
```

### CRON 分工

| 时间 | CRON | 权限 | 模型 | 交付格式 | 核心职责 |
|------|------|------|------|---------|---------|
| 09:00 | 盘前定调 | 只读 | deepseek-v4-pro | 📰 报纸 | 加载策略 / 写market_context / 6步分析 / 供午盘读取 |
| 10:00 | 午盘执行 | 交易 | deepseek-v4-pro | 📝 精简文本 ≤5行 | 读market_context→硬约束→场景匹配执行。只报操作+仓位+风险，不报大盘/板块/账户 |
| 13:16 | 午后侦察 | 侦察+有限写 | deepseek-v4-pro | 📝 短文本 | 侦察→写market_snapshot(JSON) / 可追加stop_loss scenario |
| 14:22 | 引擎扫描 | 只读 | deepseek-chat | 📰 报纸 | 引擎一扫描(读 engine1_pool.json) → 引擎二排名(engine2_ranker.py) → 写入 engine_tracker.json → 双引擎合并报纸图。顺序执行，无竞态 |
| 15:10 | 引擎池管理 | 只读 | deepseek-chat | 🔇 local（内部） | 收盘后全市场异动流入 + 淘汰判定 + 周六概念补充。写 engine1_pool.json |
| 14:35 | 尾盘执行 | 交易 | deepseek-v4-pro | 📝 文本 | 读market_snapshot→硬约束→执行。纯文本交付：操作+持仓+决策逻辑 |
| 15:05 | 收盘复盘 | 只读 | deepseek-v4-pro | 📰 报纸+计分卡 | 归档→calc_risk_state→读ranked→自动生成scenarios→生成报纸图片→更新索引 |

## 策略链机制（Strategy Chain）

**核心问题**：各CRON之间不共享上下文，盘后复盘写的策略次日盘中无法加载。

### 文件布局

```
~/.hermes/cron/state/moni/
├── strategy_index.json          ← 索引指针（原子读写）
├── strategies/
│   ├── 2026-05-27.json          ← 每交易日一个文件，只增不改
│   ├── 2026-05-28.json
│   └── 2026-05-29.json
├── archive/                     ← 7天以上归档
└── scorecard/                   ← 平衡计分卡（独立子系统）
    ├── index.json
    ├── known_defects.json
    ├── predictions.json
    └── daily/
```

### 生命周期状态机

```
复盘创建 → pending → (次日盘前激活) → active → (次日复盘关闭) → closed → (7天后) → archived
```

### 加载协议（所有CRON两步启动）

**Step -1: 安全校验（所有CRON第一步）**
```bash
检查1: 策略文件是否存在 → 不存在=非交易日/周末/假期 → 终止
检查2: 策略status是否closed → 是=已执行过/重复触发 → 终止
检查3(盘中专属): execution_log中是否有同名cron记录 → 是=重复触发 → 终止
检查4(复盘专属): 索引active_strategy是否与今天一致 → 否=状态错乱 → 终止
检查5(复盘专属): 次日策略是否已存在(pending) → 是=跳过创建只出报告
```

**Step 0: 加载策略链**
```bash
1. cat strategy_index.json → 验证 trading_day == 今天
2. cat strategies/{today}.json → 加载 risk_state + current_strategy + overrides + execution_log
```

**Step 0a: 硬约束检查（午盘/尾盘强制执行，死命令不可绕过）**
```
规则1: emergency模式 → 立即全清，终止
规则2: 仓位 > hard_position_cap → 强制卖出超额部分（优先砍浮亏最大）
规则3: new_position_ban=true → 禁止任何买入（即使盘前override也不行）
规则4: consecutive_loss_days >= 2 → 单票上限减半，禁加仓浮亏标的
规则5: execution_log中有午后检查stop_loss_breached → 立即止损
```

### 冲突解决规则

| 规则 | 内容 |
|------|------|
| 规则1 | 复盘策略是当日基准，有效期到次日15:00 |
| 规则2 | 盘前可override复盘策略，写入overrides[]并说明理由。不可改risk_state硬约束 |
| 规则3 | 盘中（午盘/尾盘）只能走scenarios匹配，不可自由发挥。紧急情况（科创50暴跌-5%+）可emergency bypass，必须写deviation |
| 规则4 | 每次交易必须记录 applied_strategy_id 或 deviation 的 root_cause |
| 规则5 | 收盘复盘归档旧策略、统计偏离、产生新策略 |
| 规则6 | risk_state 是累积硬约束，任何CRON必须先读 |

### 写入原则

- 策略文件**只追加不覆写**
- strategy_index.json 是唯一会被覆写的文件（复盘时更新）
- overrides[] 由盘前独占写入
- execution_log[] 由午盘/尾盘/午后写入（天然时间隔离，不会并发）
- 🆕 `market_context` 由盘前独占写入
- 🆕 `market_snapshot` 由午后独占写入
- 🆕 午后可追加 scenario（type: afternoon_stop_loss / afternoon_emergency），不可改已有 scenarios / per_stock / risk_state

## 风控体系 v4

### risk_state 计算（确定性脚本，禁止 LLM 自行判断）

**必须调用 `~/.hermes/scripts/calc_risk_state.py` v2**：
```bash
# Step 1: 从父策略文件读取收盘后的 consecutive_loss_days（end-of-day 值）
PARENT_CONSEC=$(python3 -c "
import json
d=json.load(open('~/.hermes/cron/state/moni/strategies/{parent_strategy}.json'))
print(d.get('risk_state',{}).get('consecutive_loss_days',0))
")

# Step 2: 传入 parent_consecutive 绕过策略文件 start-of-day 偏移
python3 ~/.hermes/scripts/calc_risk_state.py <今日盈亏> <总资产> <parent_strategy日期> <历史最高点> $PARENT_CONSEC
```

🔴🔴🔴 **绝对规则：`calc_risk_state.py` 的输出即为最终 risk_state，禁止 LLM 对任何字段（consecutive_loss_days、level、drawdown_from_peak、new_position_ban 等）做手动修正。** 即使怀疑输出有误也必须信任脚本——怀疑错误应修脚本，而非运行时覆盖。违反此规则将导致熔断状态永久无法解除（2026-06-02 实际案例：CRON prompt 缺少此规则导致 consecutive_loss_days 跨交易日偏移不归零，熔断误持续 2 天）。

**熔断解除条件（by calc_risk_state.py）：**
- `today_pnl >= 0` → `consecutive_loss_days = 0`（重置）
- 空仓日 P&L=0 自动触发重置
- 解除路径：consecutive_loss_days 归零 + drawdown < 8% + 无 stop_loss → level 降至 normal/cautious
- 策略文件关闭时必须将 end-of-day risk_state 写回文件，确保下次加载的是收盘值而非 start-of-day 值

硬编码规则（不允许 LLM "灵活解释"）：
```
if consecutive_loss_days >= 3 or drawdown >= 0.08 or stop_loss_triggered:
    level = "emergency"    → cap=0.00, single=0.00, ban=True
elif consecutive_loss_days >= 2 or drawdown >= 0.05:
    level = "defensive"    → cap=0.30, single=0.15, ban=True
elif consecutive_loss_days >= 1:
    level = "cautious"     → cap=0.50, single=0.25, ban=True
elif drawdown >= 0.03:
    level = "cautious"     → cap=0.50, single=0.30, ban=False
else:
    level = "normal"       → cap=0.80, single=0.40, ban=False
```

### 辅助脚本

| 脚本 | 用途 |
|------|------|
| `~/.hermes/scripts/calc_risk_state.py` | 确定性风险计算（硬编码规则） |
| `~/.hermes/scripts/engine2_ranker.py` 🆕 | 引擎二：选股+查行业+交叉排名 |
| `~/.hermes/scripts/early_breakout_scanner.py` | 引擎一：三阶段扫描 |
| `~/.hermes/scripts/moni_check_trades.py` | 交易检测（orders API + 快照双重验证） |
| `~/.hermes/scripts/next_trading_day.py` | 计算下一个交易日（跳过周末） |
| `~/.hermes/scripts/scenario_audit.py` | Scenario 触达率审计（死亡条件/重复检测/攻防比） |
| `~/.hermes/scripts/balanced_scorecard/` | 平衡计分卡子系统（17文件，零依赖） |
| `~/.hermes/scripts/sync-to-git.sh` 🆕 | Hermes → GitHub 一键同步（含 .backup 快照） |

### Scenario 设计规范（🆕 2026-06-01 审计驱动）

**关键教训：** 首次审计发现 14 个 scenario 触达率仅 21%，进攻型 0/5 触达。根源：

1. **禁止绝对价格触发** — "反弹至 X 元"在下跌市形同虚设。改用相对指标（连续 N 日未创新低 / 站上 M 日线 / 量比 > T）
2. **继承 ≠ 复制** — 复盘创建次日策略时，前日的 scenario 必须根据当日市场变化调整条件，不允许原文复制。5/28→5/29 全量复制已证实无效
3. **攻防比目标** — 当前 5:5，目标 3:5（至少 3 个进攻型 scenario 对应 5 个防御型）
4. **运维型 scenario 不应占名额** — retry_unfreeze/monitor_only 应在硬约束中处理，不占用 scenario 配额

详见 `references/scenario-audit.md`

### orders API 降级方案

`moni_check_trades.py` 使用双重验证解决 orders API 空返回问题：
1. orders API 有记录 → 有交易
2. 快照对比（balance + positions 变化）→ 有交易
3. 两者都无 → 确认无交易

午盘 CRON 启动时保存快照，后续任何 CRON 即使遇到 orders API 空返回，也能通过快照检测。5/28 真实案例：orders 空 + 快照检测到长电 875→4875 (+4000)。

**⚠️ 数据格式陷阱：** `moni_check_trades.py` 的 `check_trades()` 函数期望**原始 API 格式**（`{"data": {"totalAssets": ..., "records": [...]}}` 嵌套结构），但 `moni_engine.get_balance()` 和 `get_positions()` 返回的是**已解析的扁平格式**（`{"total_assets": ..., "avail_balance": ...}` 和 `[{"name": ..., "qty": ...}]`）。直接传入 moni_engine 的返回值会导致 `check_trades()` 取不到数据（`.get("data", {}).get("totalAssets", 0) == 0`），静默返回 "orders API空+快照无变化"。使用时必须包装成 `{"data": {"totalAssets": total, ...}}` 结构，或直接手动对比 orders API 返回的原生数据。

## 🔴 已知陷阱

### context_from 旁路注入

**症状**：尾盘执行曾经设置了 `context_from: ["ce7bb0928324"]`，引擎一的原始对话文本直接注入尾盘 prompt——绕过了策略文件数据总线。

**危害**：
- 引擎一/二的选股结果以"对话文本"形式传递，无法被下游结构化消费
- 尾盘执行收到的是自然语言描述，不是 `candidate_pool` 对象，需要 LLM 重新解读
- 和策略文件的 `candidate_pool.engine1/engine2.ranked` 形成两套数据源，可能不一致

**正确做法**：
- 引擎一写入策略文件 `candidate_pool.engine1`（结构化 JSON）
- 引擎二从策略文件读取，排名后写入 `candidate_pool.engine2.ranked`
- 尾盘执行从策略文件读取 `candidate_pool`，计算交叉命中
- 所有 CRON 的 `context_from` 保持为 `None`

**6/2 修复**：尾盘执行的 `context_from` 已清零，引擎一/二改为策略文件读写。验证命令：
```bash
python3 -c "import json; d=json.load(open('~/.hermes/cron/jobs.json')); [print(j['name'],j.get('context_from')) for j in d['jobs'] if '摸金虾' in j.get('name','')]"
```
全部应输出 `None`。

### risk_state.level 与 current_strategy.mode 不一致

**症状**（6/2 案例）：`risk_state.level = normal`（空仓日 P&L=0 触发熔断重置），但 `current_strategy.mode = emergency`，`core_thesis` 仍写"触发熔断"——策略文案与风控数据不同步。

**检查方法**（每日盯盘三信号之一）：
```bash
python3 -c "
import json
d=json.load(open('strategies/{today}.json'))
r=d['risk_state']['level']
m=d['current_strategy']['mode']
print(f'risk={r} mode={m} {\"✅\" if r==m or (r==\"normal\" and m==\"conservative\") else \"🔴 不一致！\"}')"
```

**修复原则**：收盘复盘关闭策略时，`current_strategy.mode` 必须根据 `risk_state.level` 填写，不允许出现 `level=normal` 但 `mode=emergency` 的断层。

| # | 问题 | 严重度 | 状态 |
|---|------|:---:|:---:|
| 1 | 策略不流通（盘后策略盘中看不到） | P0 | ✅ 策略链+Step0加载 |
| 2 | orders API不可靠（空返回但交易已发生） | P0 | ✅ moni_check_trades.py双重验证 |
| 3 | 锁仓未校验（不查avail就下单） | P0 | ✅ 交易前强制查avail |
| 4 | 单次仓位跳变过大（5/28: 45%→75%） | P1 | ✅ 硬约束仓位上限检查 |
| 5 | 10:00→14:20真空4小时 | P1 | ✅ 新增13:00午后检查 |
| 6 | 连续回撤无自动熔断 | P1 | ✅ calc_risk_state.py硬编码规则 |
| 7 | 盘后策略与盘中执行脱节 | P1 | ✅ 策略链流通+硬约束 |
| 8 | CRON重复触发无防护 | P1 | ✅ Step-1安全检查 |
| 9 | 模型降级 | P2 | ✅ 升级v4-pro |
| 10 | 15:00多CRON并发抢API | P2 | ✅ 错峰排布 |
| 11 | API失败无降级方案 | P3 | ✅ 重试+跳过+记录 |
| 12 | 收盘复盘凭感觉选股（无引擎数据驱动） | P1 | 🟡 v1.0三体联动建管道 / v1.1引擎路径闭环（触达率21%，引擎非唯一来源） |
| 13 | Scenario触达率21%、进攻型0触发、引擎推荐无法追踪绩效 | P1 | 🟡 v1.1 SRS设计中 → `products/摸金虾/roadmap/需求池/SRS-001-engine-path-closure.md` |
| 14 | 午盘/尾盘各做独立侦察，重复4次/天 | P2 | ✅ v5侦察收敛（6/2） |
| 15 | 午后检查只能写文本预警 | P2 | ✅ v5升级（6/2） |
| 16 | 文档杂乱：INDEX+backlog+issues.json 三套追踪 | P2 | ✅ 统一→需求清单+问题清单+迭代计划（6/3）。问题清单为唯一问题源，P0/P1/P2 分流 |
| 17 | 报纸图片生成失败：Chromium缺失 + Agent跳过Step 6 | P0 | ✅ 已修复。premarket_image.py探测snap chromium（2026-05-14安装）+ `--no-sandbox` + 系统Noto CJK字体 + OUTPUT_DIR=`~/.hermes/tmp/premarket/`。无需WeasyPrint回退。cron prompt将图片生成从编号步骤移到「最终回复（必须）」独立段落 |

## 策略链数据结构

详见 `references/strategy-chain-spec.md`

### market_snapshot 数据结构（午后检查写入）

```json
{
  "market_snapshot": {
    "written_by": "午后检查",
    "written_at": "2026-06-03T13:16:00+08:00",
    "indices": {
      "sse": {"price": 3350, "change_pct": 0.15},
      "star50": {"price": 1020, "change_pct": 1.66},
      "csi300": {"price": 4200, "change_pct": -0.19},
      "gem": {"price": 2180, "change_pct": 0.01}
    },
    "sectors": {
      "semiconductor": {"change": "+1.03", "flow": "-48亿", "trend": "V型反弹"}
    },
    "alerts": [
      {"level": "🚨", "type": "sector_reversal", "detail": "半导体-1.85%→+1.03%，午后V反"},
      {"level": "🔴", "type": "stop_loss_breached", "stock": "688012", "price": 280, "stop": 285}
    ],
    "midday_news": ["半导体设备ETF涨2.89%"],
    "bias": "偏多",
    "recommendation": "关注半导体尾盘确认，若科创50守住+1.5%可建仓"
  }
}
```

### market_context 数据结构（盘前分析写入）

```json
{
  "market_context": {
    "written_by": "盘前分析",
    "written_at": "2026-06-03T09:00:00+08:00",
    "main_themes": ["半导体", "AI算力", "机器人"],
    "sector_momentum": {"半导体": "+1.7%", "科创50": "+1.6%"},
    "external_env": "美股温和",
    "bias": "偏多",
    "risk_note": ""
  }
}
```

### 午后可追加的 scenario 类型

- `afternoon_stop_loss` — 触发止损价，尾盘无条件卖出
- `afternoon_emergency` — 板块暴跌>3%，尾盘全清
- 约束：不可改 risk_state / per_stock / 已有 scenarios / overrides

## v1.1 引擎路径闭环 + 动态候选池 → 被 SRS-013 吸收

> 完整设计：`products/摸金虾/roadmap/需求池/SRS-013-engine-layer-restructure.md`  
> SRS-001（引擎路径闭环）和 SRS-002（动态候选池）已关闭，全部设计吸收进 SRS-013。  
> SRS-013 = 引擎层完整蓝图：CRON合并(14:22 扫描 + 15:10 池管理) + 全市场动态池 + engine_tracker.json 绩效追踪 + 消除尾盘独立选股 + 模型降级 deepseek-chat。

---

## 迭代运维机制

### 开发运维流程

**完整流程见** `~/.hermes/products/摸金虾/docs/development.md`。要点：

- **三层节奏**：每日盯盘（三信号检查，红灯记问题清单）→ 每周六（审计+排期+集中改）→ 每月末（月目标核算+回溯）
- **盘中不改**：09:00-15:05 不改任何 CRON prompt 或策略文件
- **问题管理**：问题清单为唯一追踪源，P0 立即修、P1 周六修、P2 周六修或走需求流程
- **需求管理**：想法→需求清单→SRS（四态：设计→待实施→实施中→已完成）
- **报纸三节点**：盘前定调 + 引擎二排名 + 收盘复盘使用报纸图片。午盘/午后/尾盘用精简文本
- **策略文件**：超过30天移入 archive/
- **cron 交付**：统一 `qqbot:458685AEDAC4C90FCF3C8EF692BBC9DC`
- **产品设计文档**：`~/.hermes/products/摸金虾/`。完整规范见 `references/product-doc-conventions.md`
- **迭代计划**是唯一版本规划源（累积不清空），changelog 由此提取——需要发更新公告时从 ✅ 迭代提取，不单独维护
- **GitHub**：`zhouxianwang2018-rgb/mojinxia`，同步脚本 `sync-to-git.sh`
- **审计**：平衡计分卡（`balanced_scorecard`）+ Scenario 审计（`scenario_audit.py`），建议每周六跑

### GitHub 同步

```bash
bash ~/.hermes/scripts/sync-to-git.sh "v1.x: 描述"
```

一键完成：① 导出 7 个 CRON prompt ② cp 设计文档 / skill / 脚本到 git 仓库 ③ 存档 Hermes 运行态快照到 `.backup/` ④ git commit + push。

每次版本更新后执行。无参数时自动从迭代计划提取版本号生成 commit message。

### 🔴 盘前定调必须翻转 status（2026-06-04 事故）

**症状**：尾盘执行直接 `[SILENT]`，止盈/止损/交易全部跳过。持仓有研硅从-0.67%拉到+7.17%，午后侦察明确标注 `TAKE_PROFIT_BREACHED`，全部因 status 检查失败被丢弃。

**根因**：盘前定调 Step 5 只写 `market_context`，没翻 `status`。尾盘 Step -1 检查 `status=='active'` 失败 → 终止。

**修复**：盘前 CRON prompt 的 Step 5 必须在写入 `market_context` 的同时执行 `strategy['status'] = 'active'`。缺失这一步会导致当天所有执行层 CRON（午盘/尾盘）全部静默跳过。

**验证**：
```bash
python3 -c "import json; d=json.load(open('~/.hermes/cron/state/moni/strategies/$(date +%Y-%m-%d).json')); print(d['status'])"
# 必须是 "active"，不能是 "pending" 或 "closed"
```

### 产品文档

`~/.hermes/products/摸金虾/` 完整文档体系：

| 文档 | 用途 |
|:--|:--|
| README.md | 入口导航 |
| SETUP.md | 从零复刻指南（环境/API Key/初始化/验证） |
| docs/architecture.md | 三体联动+CRON分层+ADR |
| docs/strategy-schema.md | 策略文件数据总线完整schema |
| docs/cron-commands.md | 7条cron完整参数+创建命令 |
| docs/data-flow.md | ASCII数据流向图+字段读写矩阵+API依赖 |
| docs/development.md | 需求/问题/迭代/发布/运维全生命周期 |
| docs/troubleshooting.md | 常见故障+排查命令 |
| roadmap/ | 需求清单/问题清单/迭代计划/SRS文件 |

### 运行时文件

```
~/.hermes/cron/state/moni/
├── engine_tracker.json      ← v1.1 引擎推荐生命周期追踪（不进 git）
├── engine1_pool.json        ← v1.x 引擎一动态观察池（不进 git）
└── audit/                   ← 每周自动生成的计分卡/审计报告
```
