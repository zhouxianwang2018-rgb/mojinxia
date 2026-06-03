# 策略链完整架构规范

## 文件布局

```
~/.hermes/cron/state/moni/
├── strategy_index.json          ← 索引指针
├── strategies/
│   ├── 2026-05-28.json          ← 每个交易日一个文件（只增不改）
│   └── 2026-05-29.json
└── archive/                     ← >30天归档
```

## strategy_index.json Schema

```json
{
  "current_trading_day": "2026-05-29",
  "active_strategy": "2026-05-29",
  "chain": ["2026-05-28", "2026-05-29"],
  "last_closed_day": "2026-05-28",
  "market_status": "open"
}
```

## 单日策略文件 Schema (strategies/{date}.json)

```json
{
  "trading_day": "2026-05-29",
  "parent_strategy": "2026-05-28",
  "status": "pending",
  "created_by": "收盘复盘",
  "created_at": "2026-05-28T15:30:00+08:00",
  "valid_until": "2026-05-29T15:00:00+08:00",
  "closed_at": null,

  "risk_state": {
    "level": "cautious",
    "level_reason": "连续2日亏损，回撤2.05%",
    "consecutive_loss_days": 2,
    "drawdown_from_peak": 0.0205,
    "peak_total": 1130323.0,
    "hard_position_cap": 0.50,
    "hard_single_stock_cap": 0.30,
    "new_position_ban": true,
    "stop_loss_triggered": false
  },

  "current_strategy": {
    "id": "复盘-20260528",
    "mode": "保底防守",
    "core_thesis": "一句话操作逻辑",
    "max_total_buy_today": 0,
    "max_single_trade_pct": 0.30,

    "per_stock": {
      "600584": {
        "name": "长电科技",
        "max_hold": 4875,
        "min_hold": 875,
        "max_sell_today": 4000,
        "can_buy": false,
        "stop_loss_price": 80.00,
        "note": "4000新仓可减，875底仓禁动"
      }
    },

    "scenarios": [
      {
        "if": "科创50 +2%以上 且 中微回升至470+",
        "then": "卖出中微200股，其余持有",
        "type": "reduce"
      }
    ],

    "valid_until": "2026-05-29T15:00:00+08:00"
  },

  "overrides": [
    {
      "time": "2026-05-29T09:35:00+08:00",
      "by": "盘前分析",
      "overrides_strategy_id": "复盘-20260528",
      "reason": "长电Q2超预期+板块反弹",
      "changes": {"max_total_buy_today": 100000, "per_stock.600584.can_buy": true},
      "status": "active"
    }
  ],

  "execution_log": [
    {
      "time": "2026-05-29T10:05:00+08:00",
      "cron": "午盘检查",
      "action": "卖出 中微公司 688012 200股@470.00",
      "scenario_matched": "reduce - 中微回升至470+",
      "deviation": "null"
    }
  ]
}
```

## 生命周期状态机

```
复盘创建 → pending → (次日盘前激活) → active → (次日复盘关闭) → closed → (30天后) → archived
```

## CRON 协议汇总

| CRON | Step -1 | Step 0 | Step 0a | 写权限 |
|------|:---:|:---:|:---:|:---:|
| 盘前分析 | ✅ | ✅ 加载策略 | — | overrides[] |
| 午盘检查 | ✅ | ✅ 加载策略 | ✅ 硬约束 | execution_log[] |
| 午后检查 | ✅ | ✅ 加载策略 | — | execution_log[] (只写预警) |
| 早期突破 | — | ✅ 加载策略 | — | 只读 |
| 尾盘检查 | ✅ | ✅ 加载策略 | ✅ 硬约束 | execution_log[] |
| 收盘复盘 | ✅ +3检查 | ✅ 归档+计算 | — | 关闭旧+创建新+索引 |

## 并发安全

- 策略文件只追加不修改，每个人只写自己的字段
- overrides[] 只有盘前写（09:25）
- execution_log[] 午盘(10:00)和尾盘(14:35)写，天然时间隔离
- 复盘(15:05)是唯一全文件覆写者（关闭+创建）
- 15:00 错峰排布消除车牌/产业链的资源竞争
