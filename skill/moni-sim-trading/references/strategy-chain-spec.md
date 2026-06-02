# 策略链数据结构规范

## strategy_index.json

```json
{
  "current_trading_day": "2026-05-29",
  "active_strategy": "2026-05-28",
  "chain": ["2026-05-27", "2026-05-28", "2026-05-29"],
  "last_closed_day": "2026-05-28",
  "market_status": "open"
}
```

| 字段 | 说明 |
|------|------|
| current_trading_day | 当前策略链最新的交易日（复盘写入） |
| active_strategy | 当前生效的策略文件 key |
| chain | 策略链序列，新复盘追加 |
| last_closed_day | 最近一次正常关闭的交易日 |
| market_status | "open" / "closed"（周末/假期为closed） |

## 单日策略文件 strategies/{YYYY-MM-DD}.json

```json
{
  "trading_day": "2026-05-29",
  "parent_strategy": "2026-05-28",
  "status": "active",
  "created_by": "收盘复盘",
  "created_at": "2026-05-28T15:30:00+08:00",
  "valid_until": "2026-05-29T15:00:00+08:00",
  "closed_at": null,

  "risk_state": {
    "level": "cautious",
    "level_reason": "连续2日亏损，从高点回撤2.05%",
    "consecutive_loss_days": 2,
    "drawdown_from_peak": 0.0205,
    "hard_position_cap": 0.50,
    "hard_single_stock_cap": 0.30,
    "new_position_ban": true,
    "stop_loss_triggered": false
  },

  "current_strategy": {
    "id": "复盘-20260528",
    "mode": "保底防守",
    "core_thesis": "收官日优先守住¥1,116,000平台",
    "max_total_buy_today": 0,
    "max_single_trade_pct": 0,

    "per_stock": {
      "600584": {
        "name": "长电科技",
        "max_hold": 4875,
        "min_hold": 875,
        "max_sell_today": 4000,
        "can_buy": false,
        "stop_loss_price": 80.00,
        "note": "新加4000股可减，875股底仓禁动"
      }
    },

    "scenarios": [
      {
        "if": "科创50 +2%以上 且 中微回升至470+",
        "then": "卖出中微200股，其余不动",
        "type": "reduce"
      },
      {
        "if": "中微跌破430",
        "then": "清仓中微全部800股，不计价格",
        "type": "stop_loss"
      },
      {
        "if": "科创50暴跌-3%以上",
        "then": "全面清仓所有标的",
        "type": "emergency"
      }
    ],

    "valid_until": "2026-05-29T15:00:00+08:00"
  },

  "overrides": [
    {
      "time": "2026-05-29T09:35:00+08:00",
      "by": "盘前分析",
      "overrides_strategy_id": "复盘-20260528",
      "reason": "长电Q2超预期预告，半导体板块盘前期货+1.8%",
      "changes": {
        "mode": "正常",
        "max_total_buy_today": 100000,
        "per_stock.600584.can_buy": true
      },
      "status": "active"
    }
  ],

  "execution_log": [
    {
      "time": "2026-05-28T10:05:00+08:00",
      "cron": "午盘检查",
      "action": "买入 长电科技 4000股@84.77",
      "strategy_applied": null,
      "deviation": "5/27复盘策略明确'不宜在下跌趋势中加仓'，但未加载策略文件",
      "root_cause": "策略不流通"
    }
  ]
}
```

## risk_state.level 硬约束映射

| level | 触发条件 | 仓位上限 | 单票上限 | 新开仓 |
|-------|---------|---------|---------|--------|
| aggressive | 连续盈利+板块强势 | 80% | 50% | 允许 |
| normal | 默认 | 70% | 35% | 允许 |
| cautious | 连续2日亏损 | 50% | 30% | 禁止 |
| defensive | 连续3日亏损 | 30% | 20% | 禁止 |
| emergency | 从高点回撤>5% | 0% | 0% | 禁止 |

## execution_log.scenarios 匹配规则

盘中CRON（午盘/尾盘）执行流程：

```
1. 读取 risk_state → 检查硬约束
2. 读取 scenarios[] → 遍历匹配
3. 若多个 scenario 同时匹配 → 优先执行 type=emergency > stop_loss > reduce > buy
4. 若没有任何 scenario 匹配 → 默认动作: 持有不动
5. 大盘暴跌超-5% 时（scenario未覆盖） → emergency bypass
   → 写入 execution_log，deviation 记录 bypass 原因
```

## overrides 规则

- 只能由盘前CRON写入
- 不能改 risk_state 中的 hard_* 字段
- 不能改 per_stock.max_hold/min_hold/stop_loss_price（这些是复盘基于风控算的硬线）
- 可以改：mode, core_thesis, max_total_buy_today, can_buy, scenarios（追加情景）
- status 初始 "active"，复盘归档时改为 "reviewed"
