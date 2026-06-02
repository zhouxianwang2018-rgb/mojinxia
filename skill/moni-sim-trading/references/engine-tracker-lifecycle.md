# 引擎推荐生命周期设计

> 来源：`products/摸金虾/roadmap/20260603-engine-path-closure.md` v1.1 Feature 设计  
> 用途：执行层 CRON（午盘/尾盘/收盘复盘）在操作 engine_tracker.json 时的参考规范

## 四态模型

| 状态 | 含义 | 触发条件 | 终态？ |
|------|------|---------|:---:|
| `open` | 推荐已生成，等待盘中触发买入 | 收盘复盘 Step 4 写入 | 否 |
| `holding` | 已被买入，持仓中 | 午盘/尾盘执行买入操作 | 否 |
| `closed` | 全部卖出，盈亏已结算 | 主动卖完 或 T+5 强制平仓 | ✅ |
| `expired` | 触发窗口内未买入，推荐作废 | T+1 收盘复盘检测超期 | ✅ |

```
                    trigger_window (T→T+1 15:05)
推荐产生 ──→ open ──────────────────────→ expired
  (T日15:05)  │   (超期未买入)
              │
              │ 触发买入 → holding ──→ 全部卖出 ──→ closed
              │                       ──→ T+5 强制平仓 ──→ closed
```

## 时间窗口

**trigger_window（买入窗口）**：T 日 15:05 → T+1 日 15:05  
覆盖执行窗口：T+1 午盘(10:00) + T+1 尾盘(14:35)

**holding_window（持仓窗口）**：买入时刻 → T+5 日 14:35  
到期未卖 → 尾盘执行 CRON 强制市价平仓，`forced_sell=true`

## 状态转换规则

| 当前 | 事件 | 新状态 | 执行者 |
|------|------|:---:|------|
| `open` | T+1 收盘复盘未买入 | `expired` | 收盘复盘 |
| `open` | 午盘/尾盘买入 | `holding` | 执行层 |
| `holding` | 全部卖出 | `closed` | 收盘复盘结算 |
| `holding` | T+5 14:35 仍有持仓 | `closed` | 尾盘平仓 → 复盘结算 |
| `holding` | 部分卖出 | `holding` | 仅追加 trade_actions |

## 写入职责

```
收盘复盘(15:05): 遍历引擎推荐 → upsert engine_tracker
  ├─ 新推荐: status=open
  ├─ open 超期: expired + leakage_reason
  ├─ holding 持仓清零: 计算 P&L → closed
  └─ 写全量 engine_tracker.json

午盘执行(10:00): 买入 → open→holding + append trade_actions
尾盘执行(14:35): 买入 → open→holding + append trade_actions
                 卖出 → append trade_actions
                 T+5 检测 → forced_sell → append trade_actions
```

## 匹配规则

执行层匹配操作到 tracker 记录：
1. 按 `code` 查找 `status=open` 的记录
2. 多条匹配 → 所有匹配记录均追加 trade_actions
3. 尾盘买入无匹配 → 拒绝交易（引擎唯一来源原则）
4. 同一标的双引擎推荐 → 各自独立生命周期，均追加

## 盈亏结算

`realized_pnl = Σ(卖出金额) - Σ(买入金额)`  
`realized_pnl_pct = realized_pnl / Σ(买入金额) × 100%`

- 部分卖出不结算，全部卖完一次性算
- 强制平仓标记 `forced_sell=true`，照样结算

## 合并指标去重

分引擎指标各自独立。合并指标（combined）按 `code` 去重，选 `rank_priority` 最小的推荐为代表。

## 边缘情况

- **加仓**：追加 trade_actions(action=buy)，不重置 T+5 时钟
- **跌停卖不掉**：部分成交后继续 holding，次日重试
- **tracker 文件丢失**：从策略文件 candidate_pool + engine2.ranked 重建 open 记录（丢失历史 trade_actions）
