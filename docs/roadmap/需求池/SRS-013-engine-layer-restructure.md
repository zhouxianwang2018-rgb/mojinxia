# 引擎层完整重构

> SRS-013 · 创建：2026-06-04 · 状态：设计中
>
> **吸收**：SRS-001（引擎路径闭环）+ SRS-002（动态候选池）
> 本 SRS 实施后，SRS-001 和 SRS-002 关闭。

---

## 一、业务需求

### 1.1 问题全景

| # | 维度 | 问题 | 根因 |
|:--:|:--|------|------|
| 1 | 结构 | 两个引擎 CRON 独立 session，5 分钟竞态 | 引擎一→引擎二只靠策略文件一根数据线 |
| 2 | 可见 | 引擎一用户不可见 | deliver=local |
| 3 | 成本 | 两 CRON 各开 deepseek-v4-pro，90% 工作是跑脚本 | CRON 模型未按实际负载选型 |
| 4 | 覆盖 | 固定 55 只观察池，力量钻石 +66% 漏掉 | DEFAULT_WATCHLIST 硬编码（来自 SRS-002） |
| 5 | 闭环 | Scenario 触达率 21%，进攻型 0/5，引擎选了买不进 | 尾盘有 mx_xuangai 独立选股绕过引擎（来自 SRS-001） |
| 6 | 反馈 | 引擎绩效不可见——不知道哪个引擎在什么市况有效 | 无追踪数据结构（来自 SRS-001） |
| 7 | 安全 | 引擎 CRON 不检查策略 status | 策略 pending 时照跑，下游拒收 |

### 1.2 目标

引擎层从"两个 CRON + 固定池 + 无绩效"变为一条完整流水线：

```
池管理（收盘后自动流入/淘汰）
    → 扫描+排名（盘中单 CRON 顺序执行）
        → 绩效追踪（全生命周期记录）
            → 反馈优化（审计脚本按引擎+市况统计）
```

引擎成为标的发现的**唯一入口**，用户一张图看双引擎全景，每条推荐可追踪到盈亏。

### 1.3 成功指标

| # | 指标 | 当前 | 目标 |
|:--:|------|:--:|:--:|
| 1 | 引擎 CRON 数 | 2 | 2（结构不同：扫描 + 池管理） |
| 2 | 模型/天 | 2 × v4-pro | 2 × deepseek-chat |
| 3 | 竞态故障 | 存在 | 0 |
| 4 | 报纸含引擎一 | 否 | 是 |
| 5 | 日异动覆盖率 | 仅 55 只 | 全市场 +8% 量>1.5x |
| 6 | 池规模 | 固定 55 | 50~200 动态 |
| 7 | Scenario 触达率 | 21% | ≥60% |
| 8 | 引擎胜率可见 | 无 | 按引擎+市况分组 |
| 9 | 尾盘独立选股 | 有 | 消除 |

---

## 二、方案设计

### 2.1 整体架构

引擎层从"两个 CRON 各跑各的"重构为一条**四层流水线**：

```
┌──────────────────────────────────────────────────────────────────┐
│                        引擎层架构                                  │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │
│  │ 数据维护层   │    │ 扫描排名层   │    │ 执行消费层   │           │
│  │ (T-1 收盘后) │    │ (T 14:22)   │    │ (T 14:35)   │           │
│  ├─────────────┤    ├─────────────┤    ├─────────────┤           │
│  │             │    │             │    │             │           │
│  │ engine1_    │    │ early_      │    │ 尾盘执行     │           │
│  │ pool_       │───→│ breakout_   │───→│             │           │
│  │ manager.py  │    │ scanner.py  │    │ 读 engine2  │           │
│  │             │    │             │    │ .ranked     │           │
│  │ · 全市场    │    │ · 三阶段    │    │             │           │
│  │   异动流入  │    │   检测      │    │ 匹配        │           │
│  │ · 淘汰判定  │    │             │    │ engine_     │           │
│  │ · 概念补充  │    │ engine2_    │    │ tracker     │           │
│  │             │    │ ranker.py   │    │ → 写        │           │
│  │             │    │             │    │   executed  │           │
│  │             │    │ · 条件选股  │    │             │           │
│  │             │    │ · 交叉排名  │    │ Scenario    │           │
│  │             │    │             │    │ 匹配 → 交易 │           │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘           │
│         │                  │                  │                   │
│         ▼                  ▼                  ▼                   │
│  ┌──────────────────────────────────────────────────┐            │
│  │              数据存储层（策略文件 + 独立 JSON）     │            │
│  │                                                   │            │
│  │  engine1_pool.json    strategies/{date}.json      │            │
│  │  (动态观察池)          (candidate_pool.engine1     │            │
│  │                        + engine2.ranked           │            │
│  │                        + market_context            │            │
│  │                        + execution_log)            │            │
│  │                                                   │            │
│  │  engine_tracker.json   engine_tracker_archive/    │            │
│  │  (实时推荐追踪)         (已完结归档)               │            │
│  └──────────────────────────────────────────────────┘            │
│         ▲                                                        │
│         │                                                        │
│  ┌──────┴──────┐                                                 │
│  │ 反馈审计层   │  每周六                                          │
│  │             │                                                 │
│  │ scenario_   │                                                 │
│  │ audit.py    │  读 engine_tracker                               │
│  │             │  → 按引擎+市况分组统计                            │
│  │             │  → 触达率/胜率/平均收益/超额收益                   │
│  │             │  → 输出审计报告                                   │
│  └─────────────┘                                                 │
└──────────────────────────────────────────────────────────────────┘
```

**四个 CRON 的分工**（引擎层 2 个 + 上层 2 个）：

| CRON | 时间 | 层 | 写什么 |
|:--|:--|:--|:--|
| 引擎池管理 | 15:10 (T-1) | 数据维护 | `engine1_pool.json` |
| **引擎扫描** | **14:22** | **扫描排名** | `candidate_pool.engine1` + `.engine2.ranked` + `engine_tracker` + 报纸图 |
| 尾盘执行 | 14:35 | 执行消费 | `execution_log` + `engine_tracker.execution` |
| 收盘复盘 | 15:05 | 执行消费 | 次日的 `strategies/{date}.json`（含 scenarios） |

**关键设计原则**：

| # | 原则 | 说明 |
|:--:|------|------|
| 1 | 数据维护与扫描分离 | 池在 T-1 收盘后更新，扫描在 T 日盘中只读 |
| 2 | 扫描与排名同 session | 同一 CRON 内顺序执行，消除竞态 |
| 3 | 单写者 | 每份数据只有一个 CRON 写入，读者只读 |
| 4 | 脚本做决策 | LLM 只负责调度脚本 + 拼 markdown + 出图 |

---

### 2.2 数据存储

三份独立数据文件 + 策略文件内嵌：

```
~/.hermes/cron/state/moni/
│
├── engine1_pool.json          ← 引擎池管理(15:10) 写，引擎扫描(14:22) 只读
│   └── 动态观察池：stocks.{code}.status/ anomalies/ last_scan
│       （完整 schema 见 2.2.1）
│
├── strategies/{date}.json     ← 盘前定调/引擎扫描/尾盘/复盘 各写各的字段
│   ├── candidate_pool.engine1    ← 引擎扫描 Step 1 写
│   ├── candidate_pool.engine2    ← 引擎扫描 Step 2 写
│   ├── market_context            ← 盘前定调 写
│   ├── execution_log             ← 午盘/尾盘 追加
│   └── risk_state                ← 复盘 写
│
├── engine_tracker.json        ← 引擎扫描 写 recommended，尾盘 写 executed
│   └── recommendations[] 全生命周期
│       （完整 schema 见 2.4.1）
│
└── engine_tracker_archive/    ← 定期归档 closed/expired 条目
```

#### 2.2.1 engine1_pool.json

```json
{
  "updated": "2026-06-04T15:10:00",
  "stocks": {
    "300975": {
      "name": "商络电子",
      "source": "daily_inflow",
      "first_seen": "2026-06-03",
      "status": "active",
      "anomalies": [{ "date": "2026-06-03", "gain": 12.3, "vol_ratio": 2.1, "open_price": 28.50 }],
      "last_scan": { "date": "2026-06-04", "stage": "STAGE3", "score": 3 }
    }
  }
}
```

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `stocks.{code}` | object | key=代码 |
| `source` | enum | `daily_inflow` / `concept_supplement` / `seed` |
| `status` | enum | `active` / `dead`(累跌破位) / `stale`(20日无进展) / `harvested`(已收割) |
| `anomalies` | array | 异动记录，可多次 |
| `last_scan` | object | 最近一次三阶段扫描快照 |

**生命周期**：

```
全市场+8% → source=daily_inflow → status=active
    │                                   │
    │                     ┌─────────────┼─────────────┐
    │                     ▼             ▼             ▼
    │              累跌>开盘5%   20日无STAGE2/3   触发STAGE3且清仓
    │                  │             │             │
    │                  ▼             ▼             ▼
    │               dead          stale        harvested
    │
每周六: TOP5概念×TOP3标的 → source=concept_supplement → active
```

**冷启动**：旧 `DEFAULT_WATCHLIST`（~55只）导出为初始文件，source=seed。

---

### 2.3 CRON 层设计

#### 2.3.1 引擎池管理（15:10，T-1 收盘后）

**定位**：数据维护层。只写 `engine1_pool.json`，无用户交付。

**模型**：deepseek-chat（纯脚本调度，脚本内做决策）

**三步流水线**：

| Step | 命令 | 频率 |
|:--|:--|:--|
| 流入 | `engine1_pool_manager.py --mode daily_inflow` | 每日 |
| 淘汰 | `engine1_pool_manager.py --mode cull` | 每日 |
| 概念补充 | `engine1_pool_manager.py --mode concept_supplement` | 仅周六 |

**流入规则**：mx-stocks-screener 自然语言查询「全市场 +8% + 量>1.5x」，上限 200 只硬顶，单日新入 ≤50（按量比排序取前 50）。mx 不可用 → 重试 3 次 → 仍失败用上一日池。

**淘汰规则**：

| 条件 | → status |
|:--|:--:|
| 异动后累跌 > 异动日开盘价 5% | `dead` |
| 入池 20 自然日无 STAGE2/3 | `stale` |
| STAGE3 触发后 5 日未执行 | 保留但跳过扫描 |
| STAGE3 已清仓 | `harvested` |

**脚本职责边界**：

| 脚本 | 做什么 | 不做什么 |
|:--|:--|:--|
| `engine1_pool_manager.py` | 流入、淘汰、概念补充、写 pool | 不跑三阶段检测 |
| `early_breakout_scanner.py` | 读 pool → 三阶段检测 → 输出候选 | 不改 pool |

#### 2.3.2 引擎扫描（14:22，T 日盘中）

**定位**：扫描排名层。引擎层核心，单 CRON 内顺序执行引擎一→引擎二→绩效追踪→交付。

**模型**：deepseek-chat

**四步流水线**：

```
Step -1: 安全校验 ──→ status!=active → [SILENT]
    │
Step 1: 引擎一扫描
    │   early_breakout_scanner.py --pool engine1_pool.json
    │   → 读 pool → 三阶段检测 → 写 candidate_pool.engine1
    │
Step 2: 引擎二排名
    │   engine2_ranker.py
    │   → 读 engine1 → 全市场条件选股 → 交叉排名 → 写 engine2.ranked
    │
Step 3: 写入 engine_tracker
    │   引擎一 STAGE3 标的 + 引擎二 ranked 标的 → 各写一条 recommended
    │
Step 4: 报纸图 → QQ
        premarket_image.py --type rank → 双引擎全景报纸
```

**⚠️ 与改前的关键区别**：

| 维度 | 改前 | 改后 |
|:--|:--|:--|
| 引擎一→引擎二数据传递 | 跨 CRON session，策略文件中转 | 同 session 顺序执行，内存中转 |
| 竞态 | 引擎一延迟 → 引擎二读空 | 不存在 |
| 用户可见 | 只看引擎二 | 双引擎一张图 |
| LLM 角色 | 加载 skill + 跑脚本 | 只调度脚本 + 拼模板 |

---

### 2.4 引擎绩效追踪

#### 2.4.1 engine_tracker.json

```json
{
  "recommendations": [
    {
      "id": "rec-20260604-001",
      "engine": "engine1",
      "code": "688012",
      "name": "中微公司",
      "recommended_at": "2026-06-04T14:22:00",
      "signal": "STAGE3 评分3/3 异动+11.82%",
      "status": "recommended",
      "execution": null
    },
    {
      "id": "rec-20260604-008",
      "engine": "engine2",
      "code": "301188",
      "name": "力诺药包",
      "recommended_at": "2026-06-04T14:22:00",
      "signal": "引擎二Top+20% 涨幅20.00%",
      "status": "executed",
      "execution": {
        "entry_date": "2026-06-04",
        "entry_price": 54.54,
        "exit_date": null,
        "exit_price": null,
        "pnl": null,
        "pnl_pct": null
      }
    }
  ]
}
```

#### 2.4.2 生命周期

```
引擎扫描写入  尾盘买入匹配  卖出/清仓匹配   定期归档
    │             │             │             │
    ▼             ▼             ▼             ▼
recommended → executed ──────→ closed  →  engine_tracker_archive/
    │                             ▲
    └─ 5日未执行 → expired ──────┘
```

#### 2.4.3 写入职责

| 时机 | CRON | 操作 |
|:--|:--|:--|
| 14:22 | 引擎扫描 | 引擎一 STAGE3 + 引擎二 ranked → 各写 `recommended` |
| 买入时 | 尾盘执行 | 匹配 code + status=recommended → 写 `entry`，status→`executed` |
| 卖出时 | 午盘/尾盘/复盘 | 匹配 code + status=executed → 写 `exit` + `pnl`，status→`closed` |
| 周六 | 审计脚本 | 只读：按引擎+市况分组统计 |

#### 2.4.4 绩效指标

| 指标 | 公式 | 用途 |
|:--|:--|:--|
| 触达率 | executed / recommended | 哪个引擎推荐被执行 |
| 胜率 | pnl>0 笔数 / closed 笔数 | 哪个引擎推荐能盈利 |
| 平均收益 | avg(pnl%) | 每笔推荐的期望收益 |
| Scenario 损耗 | expired / recommended | 推荐了但没买 |
| 超额收益 | 引擎组合收益 − 基准收益 | 基准=科创50，按周/月 |

---

### 2.5 执行层改动

**消除尾盘独立选股**：当前尾盘 prompt 中有 `mx_xuangai` 独立选股兜底逻辑。实施后删除，尾盘只从 `candidate_pool.engine2.ranked` 取标的。

**匹配规则**：买入时从 `engine_tracker.json` 找 code 匹配且 status=recommended 的最新一条。找不到 → 标注 deviation（偏离引擎，记入 execution_log）。

**引擎无输出时**：当天不交易（不兜底，不强买）。审计时天然暴露引擎哑火问题。

---

### 2.6 报纸图交付

双引擎合并，一张图：

```
┌─ 摸金虾 · 引擎扫描 ────────────────────────────┐
│ 🔥 引擎一 · STAGE3 弹簧触发（X 只）              │
│   表格：代码|名称|价格|异动日|异动涨幅|MA5|评分   │
│ 🟡 引擎一 · STAGE2 回踩确认（X 只）              │
│   表格：代码|名称|价格|异动日|异动涨幅|MA5       │
│ 📊 引擎二 · 条件选股排名（X 只）                 │
│   表格：排名|代码|名称|涨幅|换手|市值|行业        │
│ 🔗 双引擎交叉命中（X只/无）                      │
│ 📌 策略约束（风险等级/仓位上限/禁制/持仓）       │
└──────────────────────────────────────────────────┘
```

### 2.7 模型选择

| CRON | 模型 | 理由 |
|:--|:--|:--|
| 引擎扫描 | deepseek-chat | 跑 2 个脚本 + 按模板拼 markdown + 出图，零推理需求 |
| 引擎池管理 | deepseek-chat | 跑 1 个脚本，脚本内做决策 |

---

## 三、文件布局

```
~/.hermes/cron/state/moni/
├── strategy_index.json
├── strategies/{date}.json         ← candidate_pool.engine1/engine2 在此
├── engine1_pool.json              ← 新增：动态观察池
├── engine_tracker.json            ← 新增：引擎推荐全生命周期
└── engine_tracker_archive/        ← 新增：已 closed 的归档

~/.hermes/scripts/
├── early_breakout_scanner.py      ← 改造：读 engine1_pool.json
├── engine2_ranker.py              ← 不改
├── engine1_pool_manager.py        ← 新增
└── scenario_audit.py              ← 新增（或扩展平衡计分卡）
```

---

## 四、风险与缓解

| 风险 | 缓解 |
|:--|:--|
| 合并后单 CRON 挂了 → 当天无引擎输出 | 比两个各挂一边强；周六审计会发现 |
| 池管理写崩 engine1_pool.json | 写前备份 `.bak`，校验 JSON 再覆盖 |
| 池管理首日无池可读（鸡生蛋） | 冷启动：旧 DEFAULT_WATCHLIST → engine1_pool.json |
| mx-stocks-screener 超时/空 | 重试 3 次，仍失败用上一日池 |
| 牛市池膨胀 >200 | 20 日淘汰 + 跌幅淘汰自然收缩，硬顶 200 |
| 尾盘砍独立选股后引擎全挂 → 无交易 | 上线日盯盘确认引擎一+二都在输出 |
| engine_tracker 写入失败 | 写 issues.json 留记录，审计时标注缺口 |
| deepseek-chat 报纸 markdown 出错 | prompt 给死模板，LLM 只做数据填充 |

---

## 五、关联

| Feature | 关系 |
|:--|:--|
| SRS-001 引擎路径闭环 | **被本 SRS 吸收**（绩效追踪 + 尾盘独立选股消除） |
| SRS-002 动态候选池 | **被本 SRS 吸收**（池管理 CRON + 数据结构） |
| SRS-012 盘前两融 | 无关 |
| #004 引擎权重动态调整 | 受益：合并后权重调整只改一个 CRON |

---

## 六、实施计划

| 节点 | 内容 | 预计 |
|:--|:--|:--|
| Phase 1 | 创建引擎扫描 CRON + 移除旧双 CRON + 验证报纸图 | 本周六 |
| Phase 2 | 冷启动 engine1_pool.json + 创建池管理 CRON | 本周六 |
| Phase 3 | 创建 engine_tracker.json + 尾盘匹配逻辑 + 消除独立选股 | 本周六 |
| Phase 4 | 首次全流程跑通（池管理→扫描→尾盘→tracker） | 下周一 |
| Phase 5 | 审计脚本 scenario_audit.py | 下周六 |

---

## 七、附录

### 附录 A：引擎扫描 CRON prompt

```
你是引擎扫描流水线：引擎一扫描 → 引擎二排名 → 写入 tracker → 双引擎报纸图。

## Step -1: 安全校验

```bash
TODAY=$(date +%Y-%m-%d)
STRATEGY_FILE=~/.hermes/cron/state/moni/strategies/${TODAY}.json
cat $STRATEGY_FILE | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d['status']=='active' else 1)"
```
失败 → [SILENT]

## Step 1: 引擎一扫描

```bash
python3 ~/.hermes/scripts/early_breakout_scanner.py \
  --pool ~/.hermes/cron/state/moni/engine1_pool.json \
  --strategy $STRATEGY_FILE \
  2>&1
```

脚本读取 engine1_pool.json，跑三阶段检测，将 STAGE3/STAGE2 写入策略文件的 candidate_pool.engine1。

## Step 2: 引擎二排名

```bash
python3 ~/.hermes/scripts/engine2_ranker.py 2>&1
```

脚本读 engine1 → 全市场条件选股 → 交叉排名 → 写入 candidate_pool.engine2.ranked。

## Step 3: 写入 engine_tracker

```bash
python3 -c "
import json
from datetime import datetime

# 读策略文件
with open('$STRATEGY_FILE') as f:
    d = json.load(f)

e1 = d['current_strategy']['candidate_pool']['engine1']
e2 = d['current_strategy']['candidate_pool']['engine2']

recs = []
rid = 0
now = datetime.now().isoformat()

# 引擎一 STAGE3 → tracker
for s in e1.get('stage3', []):
    rid += 1
    recs.append({
        'id': f\"rec-{datetime.now().strftime('%Y%m%d')}-{rid:03d}\",
        'engine': 'engine1',
        'code': s['code'],
        'name': s.get('name', ''),
        'recommended_at': now,
        'signal': f\"STAGE3 评分{s['stage3']['score']}/3 异动+{s['signals'][0]['anomaly_gain']}%\",
        'status': 'recommended',
        'execution': None
    })

# 引擎二 ranked → tracker
for r in e2.get('ranked', []):
    rid += 1
    recs.append({
        'id': f\"rec-{datetime.now().strftime('%Y%m%d')}-{rid:03d}\",
        'engine': 'engine2',
        'code': r['code'],
        'name': r.get('name', ''),
        'recommended_at': now,
        'signal': f\"引擎二 {r['reason']} 涨幅{r.get('e2_gain','?')}%\",
        'status': 'recommended',
        'execution': None
    })

# 写 tracker
TRACKER = '/home/agentuser/.hermes/cron/state/moni/engine_tracker.json'
existing = []
try:
    with open(TRACKER) as f:
        existing = json.load(f).get('recommendations', [])
except: pass

with open(TRACKER, 'w') as f:
    json.dump({'recommendations': existing + recs}, f, indent=2, ensure_ascii=False)

print(f'engine_tracker: {len(recs)} 条新推荐')
"
```

## Step 4: 双引擎报纸图（⛔ 绝对不可跳过）

用 execute_code 读策略文件 engine1 + engine2 → 按模板组装 markdown → 出图。

模板：

```markdown
# 🔍 双引擎扫描 · {日期}

---

## 🔥 引擎一 · STAGE3 弹簧触发

| 代码 | 名称 | 价格 | 异动日 | 异动涨幅 | MA5 | 评分 |
|------|------|------|------|------|------|:--:|
{逐行填入 stage3}

## 🟡 引擎一 · STAGE2 回踩确认

| 代码 | 名称 | 价格 | 异动日 | 异动涨幅 | MA5 |
|------|------|------|------|------|------|
{逐行填入 stage2}

---

## 📊 引擎二 · 条件选股排名

> 条件：均线多头 + 换手>5% + 市值>50亿 | 共 X 只

| 排名 | 代码 | 名称 | 涨幅 | 换手 | 市值 | 行业 |
|:--:|------|------|------|------|------|------|
{逐行填入 ranked}

---

## 🔗 双引擎交叉命中

{交叉标的或无}

---

## 📌 策略约束

- 风险等级：{level}
- 仓位上限：{cap}
- 新仓禁制：{ban}
- 持仓：{holdings}
```

```bash
cat <<'MDEOF' > /tmp/engine_scan.md
{完整 markdown，用实际数据，不留占位符}
MDEOF
PNG=$(python3 ~/.hermes/scripts/premarket_image.py --type rank /tmp/engine_scan.md)
echo "IMAGE=$PNG"
```

## 交付

MEDIA: {PNG路径}

`📊 双引擎扫描 | 引擎一STAGE3×{N} STAGE2×{M} | 引擎二{R}只 | 交叉命中{C}只 | {模式}`
```

### 附录 B：引擎池管理 CRON prompt

```
你是引擎池管理系统。收盘后维护 engine1_pool.json：流入 + 淘汰 + 概念补充。

## Step 0: 加载策略链（只读）

```bash
cat ~/.hermes/cron/state/moni/strategy_index.json
```

## Step 1: 全市场异动流入

```bash
python3 ~/.hermes/scripts/engine1_pool_manager.py --mode daily_inflow 2>&1
```

## Step 2: 淘汰判定

```bash
python3 ~/.hermes/scripts/engine1_pool_manager.py --mode cull 2>&1
```

## Step 3: 周度概念补充（仅周六执行）

如果是周六：

```bash
python3 ~/.hermes/scripts/engine1_pool_manager.py --mode concept_supplement 2>&1
```

非周六 → 跳过。

## Step 4: 验证

```bash
python3 -c "
import json
with open('/home/agentuser/.hermes/cron/state/moni/engine1_pool.json') as f:
    d = json.load(f)
active = sum(1 for s in d['stocks'].values() if s['status']=='active')
print(f'池状态: {active}只活跃 / {len(d[\"stocks\"])}只总计')
print(f'更新时间: {d[\"updated\"]}')
"
```

交付：local（无用户消息）
```

### 附录 C：CRON 创建命令

```bash
# 1. 移除旧 CRON
cronjob action=remove job_id=ce7bb0928324
cronjob action=remove job_id=22fcaeab7e5a

# 2. 创建引擎扫描 CRON
cronjob action=create \
  name="摸金虾·引擎扫描" \
  schedule="22 14 * * 1-5" \
  repeat=-1 \
  deliver="qqbot:<QQ_ID>" \
  model='{"model":"deepseek-chat","provider":"deepseek"}' \
  enabled_toolsets='["terminal","file"]' \
  prompt="<附录A完整prompt>"

# 3. 创建引擎池管理 CRON
cronjob action=create \
  name="摸金虾·引擎池管理" \
  schedule="10 15 * * 1-5" \
  repeat=-1 \
  deliver="local" \
  model='{"model":"deepseek-chat","provider":"deepseek"}' \
  enabled_toolsets='["terminal","file"]' \
  prompt="<附录B完整prompt>"
```

---

## 八、更新日志

| 日期 | 变更 |
|:-----|------|
| 2026-06-04 | 创建。综合引擎 CRON 讨论 + 完整吸收 SRS-001 + SRS-002 |
