# 引擎路径闭环 · v1.1 Feature 设计

> 文件：`products/摸金虾/roadmap/feature-20260603-engine-path-closure.md`  
> 版本：v1.1  
> 日期：2026-06-03  
> 状态：🟡 设计完成，待 Phase 0 验证后开工  
> Phase：内部里程碑 0→1→2→3，统一在一个版本内交付

---

## 一、业务需求

### 1.1 背景：引擎推荐与实盘执行的脱节

当前三体联动架构（v1.0）已建立引擎一（早期突破扫描）+ 引擎二（选股排名）的候选池生成能力，但存在系统性断裂：

| 问题 | 数据 | 影响 |
|------|------|------|
| Scenario 触达率低 | 首次审计 21%（5/24 触达） | 79% 的策略方案从未被执行层使用 |
| 进攻型 Scenario 零触发 | 0/5 从未被激活 | 唯一主动进攻路径形同虚设 |
| 尾盘独立选股 | LLM 可在 14:35 即兴选股，绕过引擎推荐 | 引擎工作被架空，无法评估推荐价值 |
| 收盘复盘"凭感觉" | 次日 scenarios 来源混杂（引擎结果 + LLM 即兴 + 用户口头偏好） | 策略生成不可复现，无法度量引擎贡献 |

**一句话诊断**：引擎推荐是"参考"，不是"来源"。场景方案和执行层之间有道透明墙。

### 1.2 目标

实现 **引擎 → Scenario → 交易** 的全链路闭合：

1. **引擎成为唯一标的来源**。任何交易标的必须出自引擎推荐，消灭 LLM 即兴选股。
2. **每一条引擎推荐可追踪全生命周期**：从推荐产生 → 进入 Scenario → 被执行/被跳过 → 盈亏结算。
3. **量化引擎贡献**。按引擎、按市况、按时间窗口，知道引擎赚了多少、亏了多少、漏了多少。

### 1.3 成功标准

| 指标 | 基线（v1.0） | 目标（v1.1 交付） |
|------|:---:|:---:|
| Scenario 触达率 | 21% | ≥60% |
| 引擎驱动交易占比 | ~0%（数据不可得） | 100%（引擎是唯一来源） |
| 进攻型 Scenario 触发率 | 0/5 | ≥50% 的交易日至少触发一次 |
| 按引擎/按市况的绩效归因能力 | 无 | 基础归因（按引擎、按周）可用 |

---

## 二、绩效指标体系

### 2.1 指标体系总览

| # | 指标 | 定义 | 统计频率 | 闭环目标 |
|:---:|------|------|:---:|------|
| K1 | **触达率** | 推荐→被执行的推荐占比 | 每交易日 / 周滚动 | ≥60% |
| K2 | **胜率** | 已完结推荐中盈利占比 | 每交易日 / 周滚动 | ≥55% |
| K3 | **平均收益** | 已完结推荐的平均盈亏% | 周 / 月滚动 | 正值（优于基准） |
| K4 | **Scenario 损耗** | 推荐但未执行的比例及原因分布 | 周 | <40%（即 K1≥60%） |
| K5 | **超额收益** | 引擎推荐组合 vs 基准 | 周 / 月 | ≥0（相对科创50/沪深300） |

### 2.2 各指标详细定义

#### K1 · 触达率（Hit Rate）

```
触达率 = 至少被交易过一次的推荐数 / 总推荐数 × 100%
```

- 分子：`engine_tracker` 中 `trade_actions` 非空的推荐（含 `closed` 和 `holding`）
- 分母：`engine_tracker` 中所有当日/当周产生的推荐
- 分引擎统计：`engine1` / `engine2` 各有独立触达率
- 排除：`status=expired` 的推荐（计入 K4）

#### K2 · 胜率（Win Rate）

```
胜率 = 已完结推荐中实现盈利的推荐数 / 所有已完结推荐数 × 100%
```

- 分子：`status=closed` 且 `realized_pnl > 0` 的推荐
- 分母：`status=closed` 的推荐（排除 `open` 和 `expired`）
- 不按金额加权——统计的是**推荐质量**，不是资金权重
- 分引擎统计

#### K3 · 平均收益（Average Return）

```
平均收益 = Σ(已完结推荐的 realized_pnl_pct) / 已完结推荐数
```

- `realized_pnl_pct`：该推荐对应的所有交易加权平均盈亏%
- 排除 `open` 状态的推荐（未完结不计算）
- 同时提供加权平均（按交易金额加权）作为辅助参考
- 分引擎 / 合并统计

#### K4 · Scenario 损耗（Scenario Leakage）

```
损耗率 = (未执行推荐数 + 过期推荐数) / 总推荐数 × 100%
```

原因分布：
| 损耗类型 | 含义 |
|---------|------|
| `not_triggered` | Scenario 存在但盘中未达到触发条件 |
| `ranked_out` | 被更高优先级 Scenario 挤出（只在 20 条淘汰时发生） |
| `skipped` | Scenario 被触发但执行层主动跳过（风控/仓位/判断） |
| `engine_expired` | 推荐超过有效期（T+1 收盘后仍未执行） |

- 每种原因统计占比，周报中展示损耗结构
- `ranked_out` 在 Phase 1 去除上限后应趋近于 0

#### K5 · 超额收益（Excess Return）

```
超额收益 = 引擎推荐等权组合周/月收益 — 基准周/月收益
```

- 基准：科创50（权重 60%）+ 沪深300（权重 40%），模拟盘主要池在科创+中小
- 计算方式：每周六取当周所有 `closed` 推荐的 `realized_pnl_pct` 等权平均，减去同期基准涨跌幅
- 引擎推荐组合：不模拟资金分配，只做等权收益率（衡量选股能力，隔离仓位管理）

### 2.3 数据来源与承载

所有指标数据来源于 `engine_tracker.json`（详见四、技术方案）。每周六审计时生成绩效快照，写入 `engine_tracker_summary.json`：

```json
{
  "period": "2026-W23",
  "generated_at": "2026-06-07T10:00:00",
  "engines": {
    "engine1": { "hit_rate": 0.60, "win_rate": 0.67, "avg_return": 0.032, "leakage": 0.40 },
    "engine2": { "hit_rate": 0.55, "win_rate": 0.50, "avg_return": 0.015, "leakage": 0.45 }
  },
  "combined": { "hit_rate": 0.57, "win_rate": 0.58, "avg_return": 0.023, "leakage": 0.43 },
  "excess_return": { "engine_portfolio": 0.023, "benchmark": 0.010, "alpha": 0.013 },
  "leakage_breakdown": {
    "not_triggered": 0.25,
    "ranked_out": 0.05,
    "skipped": 0.08,
    "engine_expired": 0.05
  }
}
```

---

## 三、技术方案

### 3.1 engine_tracker.json 文件设计

#### 路径与生命周期

```
~/.hermes/cron/state/moni/engine_tracker.json
```

- 不纳入 git（已加入 `.gitignore`）
- 每次写入为全量覆盖（单写者：收盘复盘负责写入；执行层通过 `patch` 追加 `trade_actions`）
- 长期保留（不按日归档），用于跨周跨月统计和 Phase 3 回溯

#### Schema

```json
{
  "version": "1.0",
  "created_at": "2026-06-03T15:05:00",
  "last_updated": "2026-06-07T15:05:00",
  "recommendations": [
    {
      "id": "eng1-20260603-001",
      "engine": "engine1",
      "date": "2026-06-03",
      "code": "300750",
      "name": "宁德时代",
      "concept": "新能源电池",
      "stage": "STAGE3",
      "engine_score": 3.0,
      "rank_priority": 7,
      "scenario_id": "scenario_1",
      "scenario_type": "主线顺势建仓",
      "status": "closed",
      "entered_at": "2026-06-03T15:05:00",
      "closed_at": "2026-06-05T14:35:00",
      "realized_pnl": 1520.50,
      "realized_pnl_pct": 0.038,
      "trade_actions": [
        {
          "timestamp": "2026-06-04T10:05:00",
          "action": "buy",
          "cron": "午盘执行",
          "price": 195.20,
          "amount": 40000.00
        },
        {
          "timestamp": "2026-06-05T14:30:00",
          "action": "sell",
          "cron": "尾盘执行",
          "price": 202.61,
          "amount": 41520.50,
          "forced_sell": false
        }
      ],
      "leakage_reason": null
    },
    {
      "id": "eng2-20260603-005",
      "engine": "engine2",
      "date": "2026-06-03",
      "code": "688981",
      "name": "中芯国际",
      "concept": "半导体制造",
      "stage": null,
      "engine_score": 2.5,
      "rank_priority": 12,
      "scenario_id": "scenario_5",
      "scenario_type": "回调介入",
      "status": "expired",
      "entered_at": "2026-06-03T15:05:00",
      "closed_at": "2026-06-04T15:05:00",
      "realized_pnl": null,
      "realized_pnl_pct": null,
      "trade_actions": [],
      "leakage_reason": "not_triggered"
    }
  ]
}
```

#### 字段说明

| 字段 | 类型 | 写入者 | 说明 |
|------|------|:---:|------|
| `id` | string | 收盘复盘 | 格式 `{engine}-{date}-{seq}`，如 `eng1-20260603-001` |
| `engine` | enum | 收盘复盘 | `engine1` / `engine2` |
| `date` | date | 收盘复盘 | 推荐产生的交易日 |
| `code` | string | 收盘复盘 | 股票代码 |
| `name` | string | 收盘复盘 | 股票简称 |
| `concept` | string | 收盘复盘 | 所属概念板块 |
| `stage` | string? | 收盘复盘 | 引擎一专用：STAGE2/STAGE3 |
| `engine_score` | float | 收盘复盘 | 引擎给的原始评分 |
| `rank_priority` | int | 收盘复盘 | 收盘复盘综合排名后的优先级（1 最高） |
| `scenario_id` | string | 收盘复盘 | 该推荐被编入的 scenario ID |
| `scenario_type` | string | 收盘复盘 | scenario 类型 |
| `status` | enum | 收盘复盘(创建+关闭) / 执行层(更新) | `open` → `holding` → `closed` / `expired` |
| `entered_at` | timestamp | 收盘复盘 | 推荐录入时间 |
| `closed_at` | timestamp? | 收盘复盘 | 关闭时间 |
| `realized_pnl` | float? | 收盘复盘 | 已实现盈亏（元） |
| `realized_pnl_pct` | float? | 收盘复盘 | 已实现盈亏% |
| `trade_actions` | array | 午盘/尾盘执行 | 交易记录追加 |
| `leakage_reason` | string? | 收盘复盘 | 未触达原因（仅在 status=expired 时有值） |

### 3.2 写入职责与时机

```
14:20  引擎一 CRON ──→ 写入 candidate_pool.engine1（不改 tracker）
14:25  引擎二 CRON ──→ 写入 candidate_pool.engine2.ranked（不改 tracker）
14:35  尾盘执行 ────→ 若操作标的在 tracker open 列表中 → append trade_actions
15:05  收盘复盘 ────→ Step 4: 遍历引擎推荐 → upsert engine_tracker
                     ├─ 新推荐：追加 open 记录
                     ├─ 已存在 open：检查是否过期 → expired / 保持 open
                     ├─ 已平仓：计算 P&L → closed
                     └─ 写全量 engine_tracker.json
次日   午盘执行 ────→ 若操作标的在 tracker open 列表中 → append trade_actions
```

### 3.3 推荐生命周期（全状态机）

#### 3.3.1 四态模型

一条引擎推荐从产生到终结，经过四个状态：

```
                    trigger_window
                    (T日15:05 → T+1日15:05)
推荐产生 ──→ open ──────────────────────→ expired
  (T日15:05)  │   (超期未买入)               │
              │                             │
              │ 触发买入                     │
              ▼                             │
           holding ────→ 全部卖出 ──→ closed │
              │                             │
              │ 超期未卖出                   │
              │ (T+5日14:35 强制平仓)        │
              └──────────────────→ closed ──┘
              (forced_sell=true)
```

| 状态 | 含义 | 触发条件 | 终态？ |
|------|------|---------|:---:|
| `open` | 推荐已生成，等待盘中触发买入 | 收盘复盘 Step 4 写入 | 否 |
| `holding` | 已被买入，持仓中 | 午盘/尾盘执行买入操作 | 否 |
| `closed` | 全部卖出，盈亏已结算 | 主动卖完 或 T+5 强制平仓 | ✅ |
| `expired` | 触发窗口内未买入，推荐作废 | T+1 收盘复盘检测超期 | ✅ |

#### 3.3.2 时间窗口

```
交易日 T               T+1              T+2  ...  T+5
    │                   │                 │          │
    ├─ 15:05 ───────────┼─ 15:05 ─────────┼──────────┼─ 14:35
    │  推荐产生          │  trigger_window │          │  holding 截止
    │  status=open       │  关闭           │          │  强制平仓
    │                    │  未买入→expired │          │
    │                    │                 │          │
    └─ trigger_window ──┘                 └─ holding ─┘
       (买入窗口)                           (持仓窗口)
```

**触发窗口（trigger_window）**：
- 起：T 日 15:05（推荐产生）
- 止：T+1 日 15:05（次日收盘复盘）
- 覆盖的盘中执行窗口：T 日尾盘（14:35，但此时推荐尚未产生）→ 实际只有 T+1 日午盘（10:00）和 T+1 日尾盘（14:35）
- 窗口内仍未买入 → `expired`，记录 `leakage_reason`

**持仓窗口（holding_window）**：
- 起：买入时刻
- 止：T+5 日 14:35（强制平仓线）
- T+5 即买入日后第 5 个交易日尾盘。例：周一买入 → 下周一 14:35 强制平仓
- 强制平仓由尾盘执行 CRON 处理，在 `trade_actions` 中标记 `forced_sell=true`

#### 3.3.3 状态转换规则

| 当前状态 | 事件 | 新状态 | 执行者 | 备注 |
|---------|------|:---:|------|------|
| `open` | T+1 收盘复盘，未被买入 | `expired` | 收盘复盘 | `leakage_reason` 写入 |
| `open` | 午盘/尾盘执行买入 | `holding` | 执行层 CRON | 追加 `trade_actions` |
| `holding` | 全部卖出（主动） | `closed` | 收盘复盘 | 计算 `realized_pnl` |
| `holding` | T+5 14:35，仍有持仓 | `closed` | 尾盘执行 | 先强制平仓，收盘复盘计算盈亏 |
| `holding` | 部分卖出 | `holding` | 不变 | 仅追加 `trade_actions` |
| `expired` | — | 终态 | — | 不可逆 |
| `closed` | — | 终态 | — | 不可逆 |

#### 3.3.4 盈亏结算规则

**`realized_pnl` 计算**：`Σ(卖出金额) - Σ(买入金额)`

- 部分卖出时不计算，等全部卖完再一次性结算
- 多次买入（加仓）+ 多次卖出（分批）→ 用累计买卖差额
- `realized_pnl_pct = realized_pnl / Σ(买入金额) × 100%`

**强制平仓（T+5）**：
- 尾盘执行 CRON 检测 `holding` 中的推荐是否已到 T+5
- 是 → 以市价卖出剩余全部持仓
- `trade_actions` 追加 `{"action": "sell", "forced_sell": true, ...}`
- 当日收盘复盘检测到持仓清零 → `status=closed`，结算 P&L

#### 3.3.5 边缘情况

**同一标的、两个引擎同时推荐**：

```
引擎一推荐 300750 → id=eng1-20260603-001, status=open
引擎二推荐 300750 → id=eng2-20260603-002, status=open
```

- 两条记录独立追踪生命周期
- 若执行层买入 300750：匹配到**两条** `open` 记录，均追加 `trade_actions`
- 若买入后只有一个引擎的记录被卖出：另一条保持在 `holding`
- **分引擎指标**：各自独立计算（这笔交易为两个引擎都贡献一次触达）
- **合并指标**（combined）：按 `code` 去重，同一笔交易只计一次，选 `rank_priority` 最小的推荐为代表

**买入后加仓**：
- 同一推荐下的加仓 → 追加 `trade_actions`（`action=buy`），不重置状态
- 不影响 `holding_window` 的 T+5 截止时间（以首次买入起算）

**T+5 强制平仓但部分成交**：
- A 股 T+1 交收，正常情况下 T+5 尾盘可以全部卖出
- 极端情况（跌停封板）：`trade_actions` 追加 `forced_sell` 但仅部分成交
- 剩余持仓保留在 `holding`，次日继续尝试卖出，直到全部清仓 → `closed`

### 3.4 匹配规则

执行层（午盘/尾盘）如何匹配操作到 engine_tracker 记录：

```
1. 按 code 查找 engine_tracker.recommendations 中 status=open 的记录
2. 若找到多条（同一标的多次推荐），按 rank_priority 最小（优先级最高）匹配
3. 若找到一个交易日内的多条 open 记录（不同引擎推荐），均追加 trade_actions
4. 尾盘买入必须匹配 open 推荐 → 若无匹配，拒绝交易（引擎唯一来源原则）
```

### 3.5 绩效快照计算逻辑（周度）

每周六执行（收盘复盘或独立脚本）：

```python
# 伪代码
def compute_engine_metrics(tracker, start_date, end_date):
    recs = [r for r in tracker.recommendations 
            if start_date <= r.date <= end_date]
    
    # K1 触达率
    total = len(recs)
    hit = len([r for r in recs if len(r.trade_actions) > 0])
    hit_rate = hit / total if total > 0 else 0
    
    # K2 胜率 + K3 平均收益
    closed = [r for r in recs if r.status == "closed"]
    win = len([r for r in closed if r.realized_pnl and r.realized_pnl > 0])
    win_rate = win / len(closed) if closed else 0
    avg_return = sum(r.realized_pnl_pct for r in closed) / len(closed) if closed else 0
    
    # K4 损耗
    expired = len([r for r in recs if r.status == "expired"])
    leakage = expired / total if total > 0 else 0
    
    # 损耗原因分布
    reasons = Counter(r.leakage_reason for r in recs if r.status == "expired")
    
    # K5 超额收益
    engine_return = sum(r.realized_pnl_pct for r in closed) / len(closed) if closed else 0
    benchmark_return = fetch_benchmark(start_date, end_date)  # 科创50*60% + 沪深300*40%
    alpha = engine_return - benchmark_return
    
    return EngineMetrics(...)
```

---

## 四、风险与上线

### 4.1 上线策略

| 项目 | 方案 |
|------|------|
| 上线时间 | Scenario 重写（Phase 1）+ 绩效追踪（Phase 2）同一天（周六）上线，不设观察期。Phase 3 回溯验证随后上线，不依赖实时交易数据 |
| 验证手段 | 改完后 `cronjob run` 全部 7 个 CRON，检查无 error |
| 失败处理 | 上线后首个交易日失败 → 当天不交易，周六修，下周一重试 |

### 4.2 回滚路径

| 场景 | 操作 |
|------|------|
| Phase 1 Scenario 重写有问题 | 回滚收盘复盘 CRON prompt 到 v1.0 |
| Phase 2 engine_tracker 写入失败 | 回滚收盘复盘 / 执行层 CRON prompt；`engine_tracker.json` 删除重建 |
| 引擎唯一来源导致交易受阻 | 尾盘 CRON 恢复到 v1.0 允许独立选股 |

所有回滚走 `DEVELOPMENT.md` 三条回滚路径（Git 历史 / tag / `.backup`）。

### 4.3 数据安全

- `engine_tracker.json` 不进 git，在 `.gitignore` 中
- `.backup/` 自动备份包含 `state/moni/engine_tracker.json`
- 如果 tracker 文件损坏或丢失：当日收盘复盘重建（从策略文件 candidate_pool + engine2.ranked 重新生成 open 记录），丢失历史 trade_actions 但不断流

---

## 附录 A：与现有 CRON 的改动对照

| CRON | v1.0 现状 | v1.1 改动 |
|------|----------|----------|
| 盘前定调 | 读取策略文件 | **无改动** |
| 午盘执行 | 读取策略文件 scenarios | **+** 操作时更新 `engine_tracker.trade_actions` |
| 午后侦察 | 独立侦察 | **无改动** |
| 引擎一扫描 | 写入 `candidate_pool.engine1` | **无改动** |
| 引擎二排名 | 读 engine1 + 写入 `engine2.ranked` | **无改动** |
| 尾盘执行 | 读候选池 + 可独立选股 | **改** 禁止独立选股 + 新增 tracker 写入 |
| 收盘复盘 | 读 ranked + 生成 scenarios | **改** Scenario 重写 + 引擎来源化 + tracker 写入 |

## 附录 B：v1.0 → v1.1 数据流变化

```
v1.0:
引擎一 ─→ candidate_pool.engine1 ─┐
引擎二 ─→ candidate_pool.engine2 ─┤
LLM 即兴 ─────────────────────────┼─→ scenarios（来源混杂，上限 14）─→ 执行层
用户偏好 ─────────────────────────┘

v1.1:
引擎一 ─→ candidate_pool.engine1 ─┐
引擎二 ─→ candidate_pool.engine2 ─┤
                                  ├─→ engine_tracker（所有推荐，可追踪）
                                  └─→ scenarios（引擎唯一来源，无限）─→ 执行层
执行层 ─→ engine_tracker.trade_actions（追加交易记录）
周六审计 ─→ engine_tracker_summary.json（K1-K5 快照）
```

## 附录 C：开工前置检查（Phase 0）

上线前必须在真实数据上确认以下 5 项全部通过：

| # | 验证项 | 方法 | 通过条件 |
|:---:|------|------|------|
| V1 | 引擎一 → 策略文件 | `cronjob run` 后检查策略文件 `candidate_pool.engine1` | 字段非空，含 STAGE2/3 标注 |
| V2 | `engine2_ranker.py` 可执行 | 检查脚本存在 + `cronjob run` 引擎二 | output 目录有内容，`engine2.ranked` 非空 |
| V3 | 尾盘读候选池 | `cronjob run` 尾盘 | 尾盘输出引用候选池，不报读取异常 |
| V4 | risk_state 一致性 | `cronjob run` 收盘复盘 | `risk_state.level` 与 `current_strategy.mode` 匹配 |
| V5 | 全部 CRON 健康 | `cronjob list` | 7 个 CRON `last_status` 全部 `ok` |

**阻断规则**：V2 失败 → 不开工，先修脚本。V4 失败 → 立即 hotfix。V1/V3 失败 → 可开工，限期内修复。
