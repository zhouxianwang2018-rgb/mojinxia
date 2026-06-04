# 数据流向 + API 依赖矩阵

> v1.1 · 2026-06-04

## 数据流向图

```
收盘复盘(15:05)
  │
  ├─ 创建次日 strategy.json（risk_state + current_strategy）
  └─ 更新 strategy_index.json
        │
        ▼
盘前定调(09:00) ──────────────────────────┐
  │                                         │
  ├─ 读: strategy.json（risk_state）        │
  ├─ 写: strategy.json.market_context       │
  └─ 输出: 报纸图片 → QQ                    │
        │                                   │
        ▼                                   │
午盘执行(10:00) ◄──────────────────────────┘
  │
  ├─ 读: market_context + risk_state + per_stock
  ├─ 执行: scenarios 匹配 + 交易决策
  └─ 写: execution_log + per_stock（止损止盈更新）
        │
        ▼
午后侦察(13:16)
  │
  ├─ 读: market_context + per_stock
  ├─ 侦察: 持仓 + 候选池快速扫描
  └─ 写: overrides（如有策略调整）
        │
        ▼
引擎一扫描(14:20)
  │
  ├─ 运行: early_breakout_scanner.py
  ├─ 扫描: 全市场 STAGE2/STAGE3 候选
  └─ 写: candidate_pool.engine1
        │
        ▼
引擎二排名(14:25)
  │
  ├─ 读: candidate_pool.engine1 + market_context.sector_momentum
  ├─ 运行: engine2_ranker.py
  ├─ 交叉: 条件选股 + 板块集中度排名
  └─ 写: candidate_pool.engine2.ranked
        │
        ▼
尾盘执行(14:35)
  │
  ├─ 读: market_context + risk_state + candidate_pool
  ├─ 执行: scenarios 匹配 + 尾盘交易
  └─ 写: execution_log + per_stock
        │
        ▼
收盘复盘(15:05) ── 关闭当日策略，创建次日策略 ──▶ 循环
```

## 字段读写矩阵

| 字段路径 | 盘前 | 午盘 | 午后 | 引擎一 | 引擎二 | 尾盘 | 复盘 |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `risk_state` | R | R | R | - | - | R | **W** |
| `current_strategy.mode` | - | R | R | - | - | R | **W** |
| `current_strategy.core_thesis` | - | R | - | - | - | R | **W** |
| `current_strategy.scenarios` | - | R | R | - | - | R | **W** |
| `current_strategy.per_stock` | - | R**W** | R | - | - | R**W** | **W** |
| `current_strategy.candidate_pool.engine1` | - | - | - | **W** | R | R | R |
| `current_strategy.candidate_pool.engine2` | - | - | - | - | **W** | R | R |
| `market_context` | **W** | R | R | - | R | R | R |
| `execution_log` | - | **W** | - | - | - | **W** | R |
| `overrides` | - | - | **W** | - | - | R | R |

> R=读取, W=写入, R**W**=读写

## API / Skill 依赖矩阵

| Cron | 妙想 MCP | 腾讯 K线 | mx-finance-assistant | early-breakout | engine2_ranker | premarket_image |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|
| 盘前定调 | ✅ | - | ✅ | - | - | ✅ |
| 午盘执行 | ✅ | ✅ | ✅ | - | - | - |
| 午后侦察 | ✅ | - | ✅ | - | - | - |
| 引擎一 | - | ✅ | - | ✅ | - | - |
| 引擎二 | ✅ | - | - | - | ✅ | ✅ |
| 尾盘执行 | ✅ | ✅ | ✅ | - | - | - |
| 收盘复盘 | ✅ | ✅ | ✅ | - | - | ✅ |

### 数据源说明

| 数据源 | 用途 | 稳定性 |
|:--|:--|:--:|
| 妙想 MCP（mx-financial-assistant） | 行情查询、板块分析、选股、财务 | ⚠️ 间歇性失败，有 5实体/次上限 |
| 腾讯 K 线 API | 日 K 线、实时行情 | ✅ 稳定 |
| Eastmoney push2 | 分时数据 | 🔴 已屏蔽，不可用 |
| engine2_ranker.py | 板块集中度查询 | ⚠️ 妙想 API 鉴权方式变更后不稳定 |
