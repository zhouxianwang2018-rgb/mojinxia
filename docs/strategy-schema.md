# 策略文件数据总线（strategy_index.json + strategy.json schema）

> v1.1 · 2026-06-04

摸金虾 7 个 CRON 通过策略文件交换数据。这是整个系统的**唯一数据总线**。

## strategy_index.json（调度索引）

路径：`~/.hermes/cron/state/moni/strategy_index.json`

```json
{
  "current_trading_day": "2026-06-04",
  "active_strategy": "2026-06-04",
  "chain": ["2026-05-28", "2026-05-29", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
  "last_closed_day": "2026-06-03",
  "market_status": "open"
}
```

| 字段 | 类型 | 写者 | 说明 |
|:--|:--|:--|:--|
| `current_trading_day` | string | 收盘复盘 | 当前交易日 YYYY-MM-DD |
| `active_strategy` | string | 收盘复盘 | 当前活跃策略文件（与 current_trading_day 一致） |
| `chain` | string[] | 收盘复盘 | 策略链历史（最多保留 30 天） |
| `last_closed_day` | string | 收盘复盘 | 上一个已平仓交易日 |
| `market_status` | enum | 盘前定调 | `pre_open` / `open` / `closed` |

---

## strategy.json（单日策略文件）

路径：`~/.hermes/cron/state/moni/strategies/YYYY-MM-DD.json`

### 顶层结构

| 字段 | 类型 | 写者 | 说明 |
|:--|:--|:--|:--|
| `trading_day` | string | 收盘复盘 | 交易日 |
| `parent_strategy` | string | 收盘复盘 | 父策略日期 |
| `status` | enum | 多个 | `pending` → `active` → `closed` |
| `created_by` | string | 收盘复盘 | 创建来源 |
| `created_at` | ISO8601 | 收盘复盘 | 创建时间 |
| `valid_until` | ISO8601 | 收盘复盘 | 失效时间（通常=次日 15:00） |
| `closed_at` | ISO8601\|null | 收盘复盘 | 关闭时间 |
| `risk_state` | object | calc_risk_state | 风控状态 |
| `current_strategy` | object | 收盘复盘 | 当日策略 |
| `overrides` | array | 午后侦察 | 手动覆盖 |
| `execution_log` | array | 午盘/尾盘 | 执行日志 |
| `market_context` | object | 盘前定调 | 市场环境上下文 |

### risk_state（风控状态）

```json
{
  "level": "cautious",
  "level_reason": "昨日亏损，进入谨慎模式",
  "consecutive_loss_days": 1,
  "drawdown_from_peak": 0.0206,
  "peak_total": 1130323.0,
  "hard_position_cap": 0.5,
  "hard_single_stock_cap": 0.25,
  "new_position_ban": true,
  "stop_loss_triggered": false
}
```

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `level` | `normal`\|`cautious`\|`defensive` | 风险等级 |
| `consecutive_loss_days` | int | 连续亏损天数 |
| `new_position_ban` | bool | 新开仓禁令（连续亏损时自动触发） |
| `hard_position_cap` | float | 总仓位上限 |
| `hard_single_stock_cap` | float | 单票仓位上限 |

### current_strategy（当日策略）

```json
{
  "id": "复盘-2026-06-03",
  "mode": "conservative",
  "core_thesis": "谨慎模式：昨日亏损，新开仓禁令生效",
  "max_total_buy_today": 0,
  "max_single_trade_pct": 0.25,
  "per_stock": {
    "688012": {
      "code": "688012",
      "name": "中微公司",
      "shares": 250,
      "cost": 285.77,
      "stop_loss": 271.48,
      "take_profit": 295.0,
      "mode": "hold"
    }
  },
  "scenarios": [
    {
      "if": "持仓个股在成本价上方",
      "then": "持有不动。关注半导体板块开盘方向",
      "type": "hold_observe"
    }
  ],
  "candidate_pool": {
    "engine1": {
      "stage2": [],
      "stage3": []
    },
    "engine2": {
      "ranked": []
    }
  }
}
```

| 字段 | 写者 |
|:--|:--|
| `mode` / `core_thesis` / `scenarios` | 收盘复盘（创建时） |
| `per_stock.*` | 收盘复盘（创建）+ 午盘/尾盘（更新止损止盈） |
| `candidate_pool.engine1` | 引擎一扫描 |
| `candidate_pool.engine2` | 引擎二排名 |

### market_context（市场环境）

```json
{
  "written_by": "盘前分析",
  "written_at": "2026-06-04T10:53:58",
  "main_themes": ["半导体", "煤炭", "电力"],
  "day_week_consensus": ["煤炭", "电力"],
  "day_week_divergence": ["半导体（日+2.4% vs 周-4.9%）"],
  "sector_momentum": {
    "煤炭": "+2.98%",
    "半导体": "+2.37%",
    "电力行业": "+1.00%"
  },
  "external_env": "NVDA -3.62% | AMD +4.02% | 美股科技分化",
  "bias": "结构性偏多（科创板独强）",
  "risk_note": "NVDA可能压制半导体开盘；煤炭周+12.8%短期过热"
}
```

| 字段 | 写者 | 读者 |
|:--|:--|:--|
| `main_themes` | 盘前定调 | 午盘/尾盘/复盘 |
| `sector_momentum` | 盘前定调 | 引擎二排名 |
| `external_env` | 盘前定调 | 午盘/尾盘 |
| `bias` | 盘前定调 | 午盘/尾盘/复盘 |
| `risk_note` | 盘前定调 | 午盘/尾盘 |

### execution_log（执行日志）

```json
[
  {
    "time": "2026-06-04T10:03:16",
    "cron": "午盘检查",
    "action": "无操作",
    "scenario_matched": "scenario/wait_hold",
    "deviation": null,
    "details": "BAN禁令阻止新买入。688012+2.21%未触发止盈"
  }
]
```

每次午盘/尾盘执行时追加一条。
