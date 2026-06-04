# 引擎路径闭环

> SRS-001 · 创建：2026-06-03 · 状态：已关闭（被 SRS-013 吸收）

---

## 一、业务需求

### 问题

| # | 问题 | 影响 |
|:--:|------|------|
| 1 | Scenario 触达率 21%（3/14），进攻型 0/5 | 引擎选了但买不进去 |
| 2 | 尾盘有独立选股兜底（mx_xuangai） | 绕过了引擎，两条线可能不一致 |
| 3 | 没有引擎绩效数据 | 不知道哪个引擎在什么市况下有效 |

### 目标

引擎成为唯一标的来源——选出来的能买进去，买进去的能验证效果。

### 成功指标

| # | 指标 | 当前 | 目标 | 衡量方式 |
|:--:|------|:--:|:--:|------|
| 1 | Scenario 触达率 | 21% | ≥60% | `scenario_audit.py` 每周审计 |
| 2 | 进攻型触达率 | 0/5 | ≥3/5 | `scenario_audit.py` 每周审计 |
| 3 | 引擎唯一来源 | 否 | 是 | 尾盘 `execution_log` 无独立选股记录 |
| 4 | 引擎胜率可见 | 无数据 | 按引擎+市况分组统计 | 审计脚本输出 |

---

## 二、方案设计

### 2.1 引擎绩效指标体系

| # | 问题 | 决策用途 |
|:--:|------|------|
| 1 | 哪个引擎的推荐被执行比例最高？ | 决定引擎权重 |
| 2 | 哪个引擎的推荐盈利比例最高？ | 决定信任哪个引擎 |
| 3 | 什么市况下哪个引擎表现最好？ | 趋势市加权引擎一、震荡市加权引擎二 |
| 4 | 引擎推荐→实际执行，损耗多少？ | 量化 Scenario 损耗 |
| 5 | 引擎驱动的组合跑赢大盘多少？ | 证明引擎价值 |

| 指标 | 公式 | 说明 |
|------|------|------|
| **触达率** | `executed / recommended` | 按引擎分开 |
| **胜率** | `pnl > 0 笔数 / 已完结笔数` | 排除仍持仓的 |
| **平均收益** | `avg(pnl%)` | 已完结推荐的平均盈亏百分比 |
| **Scenario 损耗** | `status=expired / recommended` | 推荐了但没执行 |
| **超额收益** | 引擎组合收益率 − 基准收益率 | 基准用科创50或沪深300，按周/月 |

### 2.2 文件布局

```
~/.hermes/cron/state/moni/
├── strategy_index.json
├── strategies/{date}.json      ← 每日策略（scenarios[] 结构变更）
├── engine_tracker.json         ← 新增：引擎推荐全生命周期追踪
└── issues.json
```

### 2.3 engine_tracker.json 数据结构

```json
{
  "recommendations": [{
    "id": "rec-20260603-001",
    "engine": "engine1",
    "code": "688012",
    "name": "中微公司",
    "recommended_at": "2026-06-03T14:20:00",
    "signal": "STAGE3 弹簧触发 评分3/3",
    "status": "executed",
    "execution": {
      "entry_date": "2026-06-04",
      "entry_price": 290.5,
      "exit_date": null,
      "exit_price": null,
      "pnl": null,
      "pnl_pct": null
    }
  }]
}
```

### 2.4 生命周期

```
引擎推荐 ──→ status=recommended ──→ 被执行 ──→ status=executed
                │                                    │
                │ (N天未执行)                         │ (卖出/清仓)
                ▼                                    ▼
         status=expired                       status=closed
                                           (含 entry/exit/pnl)
```

### 2.5 写入职责

| 时机 | CRON | 写入字段 |
|------|------|------|
| 14:20 | 引擎一/二 | `id` + `engine` + `code` + `name` + `signal`，状态 `recommended` |
| 10:00/14:35 | 午盘/尾盘（买入时） | 匹配引擎推荐 → 写 `entry_date` + `entry_price`，状态 → `executed` |
| 卖出/清仓时 | 午盘/尾盘/收盘复盘 | 写 `exit_date` + `exit_price` + `pnl` + `pnl_pct`，状态 → `closed` |
| 周六 | 审计脚本 | 只读，按引擎+市况分组统计 |

### 2.6 匹配规则

执行买入时：从 `engine_tracker.json` 中找 `code` 匹配且 `status=recommended` 的最新一条。找不到 → 标注 deviation。

---

## 三、风险与缓解

| 风险 | 缓解 |
|------|------|
| Scenario 生成逻辑改崩 → 次日空 scenarios 无法交易 | 改完后 `cronjob run` 验证 |
| 砍独立选股后引擎全挂 → 当天无交易 | 首次上线后盯盘确认引擎一+二都在输出 |
| 改动分散在多个 CRON prompt → 遗漏 | 逐条对照改动清单 check |
| engine_tracker 写入失败 → 绩效数据缺失 | 写入失败时在 issues.json 留记录，审计时标注缺口 |

---

## 四、关联

| Feature | 关系 |
|------|------|
| FEATURE-002 引擎一动态候选池 | 互不阻塞，可并行开发 |

---

## 五、更新日志

| 日期 | 变更 |
|:-----|------|
| 2026-06-03 | 创建，对齐四段模板 |
