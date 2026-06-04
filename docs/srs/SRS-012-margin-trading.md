# 盘前嵌入融资融券数据

> SRS-012 · 创建：2026-06-04 · 状态：已完成（2026-06-05）

---

## 一、业务需求

### 问题

| # | 问题 | 影响 |
|:--:|------|------|
| 1 | 盘前定调无资金面数据 | 只靠消息面+外盘判断，缺市场杠杆情绪这个关键维度 |
| 2 | 两融数据是市场风险偏好的领先指标 | 融资余额趋势可预示当日多空，但未在盘前阶段纳入 |
| 3 | 午盘/尾盘/复盘无两融上下文 | 盘中决策不知道全市场杠杆是在加还是减 |

### 目标

盘前 09:00 自动拉取两市融资融券数据（余额、趋势、行业分布），写入 `market_context.margin_trading`，盘前报纸图「资金弹药」章节展示，盘中全部 CRON 可读取。

### 成功指标

| # | 指标 | 当前 | 目标 | 衡量方式 |
|:--:|------|:--:|:--:|------|
| 1 | 盘前报告含两融章节 | 否 | 是 | 报纸图 manifest 包含 margin_trading |
| 2 | market_context 含 margin_trading | 否 | 是 | `strategy_index.json` 字段存在 |
| 3 | 盘中 CRON 可读取两融趋势 | 否 | 是 | 午盘/尾盘/复盘引用 margin_trading 数据 |
| 4 | 数据时效性 | — | T-1 日（09:00 可获取前一交易日数据） | API 返回数据的 date 字段校验 |

---

## 二、方案设计

### 2.1 数据来源

妙想 `mx-finance-data` 工具的融资融券查询能力，涵盖：

| 数据项 | 说明 | 来源 |
|--------|------|------|
| 两市融资余额 | 沪市+深市合计 | 妙想 finance_data |
| 两市融券余额 | 沪市+深市合计 | 同上 |
| 近 5 日趋势 | 融资余额/净买入额变化 | 同上（逐日查询后聚合） |
| 行业两融分布 | Top N 行业融资净买入 | 同上 |

> 妙想 API 的融资融券数据基于东方财富数据库，T 日盘后可获取 T 日数据，T+1 日盘前可用。

### 2.2 数据结构

#### market_context 新增字段

```json
{
  "margin_trading": {
    "as_of": "2026-06-03",
    "total_margin_balance": 27980,
    "unit": "亿元",
    "daily_change": 82.5,
    "daily_change_pct": 0.30,
    "trend_5d": [
      {"date": "2026-05-28", "balance": 27650, "net_buy": 45.2},
      {"date": "2026-05-29", "balance": 27730, "net_buy": 80.1},
      {"date": "2026-05-30", "balance": 27610, "net_buy": -120.3},
      {"date": "2026-06-02", "balance": 27898, "net_buy": 288.0},
      {"date": "2026-06-03", "balance": 27980, "net_buy": 82.5}
    ],
    "trend_signal": "震荡回升",
    "top_sectors_buy": [
      {"sector": "半导体", "net_buy": 15.2},
      {"sector": "电力设备", "net_buy": 12.8},
      {"sector": "人工智能", "net_buy": 9.5}
    ],
    "risk_flag": null
  }
}
```

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `as_of` | date | 数据截止日（T-1） |
| `total_margin_balance` | float | 两市融资余额（亿元） |
| `unit` | string | 固定 "亿元" |
| `daily_change` | float | 融资余额日变动（亿元） |
| `daily_change_pct` | float | 融资余额日变动百分比 |
| `trend_5d` | array | 近 5 个交易日逐日余额 |
| `trend_signal` | string | 趋势定性：持续流入/持续流出/震荡回升/高位回落/平稳 |
| `top_sectors_buy` | array | 融资净买入 Top 3 行业 |
| `risk_flag` | string\|null | 风险信号：null=正常，"融资骤降>200亿"/"融券激增" 等 |

### 2.3 写入职责

| 时机 | CRON | 操作 |
|------|------|------|
| 09:00 | 盘前定调 | 查询两融数据 → 写入 `market_context.margin_trading` → 报纸图「资金弹药」节展示 |

盘前定调是 `market_context` 的唯一写者，其他 CRON 只读。

### 2.4 报纸图展示

盘前报纸图「资金弹药」章节模板：

```
💰 资金弹药（融资融券 · T-1）

两市融资余额 27,980 亿 | 日变动 +82.5 亿 (+0.30%)
近 5 日趋势：震荡回升 ↗️

融资买入 Top 3：
  半导体 +15.2 亿  |  电力设备 +12.8 亿  |  人工智能 +9.5 亿

市场杠杆情绪：温和偏多
```

### 2.5 下游消费者

| CRON | 读什么 | 怎么用 |
|------|--------|--------|
| 午盘执行 | `trend_signal` | 上午放量时对照两融趋势判断主力方向 |
| 尾盘执行 | `trend_signal` + `top_sectors_buy` | 尾盘选股参考两融热钱流向 |
| 收盘复盘 | 全量 `margin_trading` | 复盘时对照当日涨跌验证两融信号有效性 |
| 引擎二 | `top_sectors_buy` | 板块集中度排名可参考两融行业分布做加权 |

### 2.6 边界情况

| 情况 | 处理 |
|------|------|
| API 无数据返回 | `margin_trading` 字段为 `null`，报纸图跳过该章节，不阻塞其他输出 |
| 非交易日（周一/节后首日） | `as_of` 显示最近交易日，`trend_5d` 可能只有 3-4 条（允许少于 5） |
| 数据取值异常（余额为 0 或 NaN） | 写入 `risk_flag: "数据异常"`，不写入数值字段 |

---

## 三、风险与缓解

| 风险 | 缓解 |
|------|------|
| 妙想两融 API 不稳定/返回空 | 降级处理：`margin_trading=null`，不阻塞盘前报告生成 |
| 盘前 cron prompt 变长 → Agent 跳过步骤 | 报纸图生成独立为 Step，prompt 用强迫性措辞约束 |
| 两融数据延迟（节假日 T-2 才出） | `as_of` 字段标注数据日期，避免用户误解 |
| 两融行业分类与板块概念不匹配 | 只展示 Top 3，用于定性参考不定量决策 |

---

## 四、关联

| Feature | 关系 |
|------|------|
| SRS-001 引擎路径闭环 | 无关，独立字段扩展 |
| 报纸图生成 (`premarket_image.py`) | 需新增「资金弹药」HTML section |
| 需求清单 #007 日报摘要 | 后续可联动：两融骤变时触发摘要告警 |

---

## 五、实施说明

| 组件 | 路径 | 说明 |
|:--|:--|:--|
| 两融查询脚本 | `~/.hermes/scripts/margin_query.py` | 查询融资余额/融券余额/融资买入额/5日趋势，输出 JSON |
| 盘前 CRON | job `9975270744c3` | Step 3.5 调用 margin_query.py → Step 5 写入 market_context.margin_trading → Step 6 报纸含资金弹药章节 |
| 数据写入 | `strategies/{date}.json` → `market_context.margin_trading` | 结构见 2.2 |
| 报纸展示 | `premarket_image.py --type premarket` | `### 💰 资金弹药` 章节，markdown → HTML 自动渲染 |

**已知限制**：mx_query 不支持行业维度两融数据，`top_sectors_buy` 固定为空数组。行业分布需 mx-search 或人工补充。

## 六、更新日志

| 日期 | 变更 |
|:-----|------|
| 2026-06-05 | ✅ 实施完成。margin_query.py + CRON prompt 更新。行业分布标记为不支持。 |
| 2026-06-04 | 创建 |
