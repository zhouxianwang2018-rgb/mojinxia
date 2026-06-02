# 三体联动：选股流水线架构

## 概览

2026-06-02 上线。解决收盘复盘"凭感觉选股"的系统性缺陷——策略生成的 scenarios 来源从 LLM 即兴发挥改为三源数据驱动。

## 数据流

```
09:25 盘前分析 CRON ──→ 写入 market_context（主线/板块/偏向）
14:20 引擎一 CRON ─────→ 写入 candidate_pool.engine1（STAGE2/3）
14:25 引擎二 CRON ─────→ engine2_ranker.py → 交叉排名 → 写入 ranked
15:05 收盘复盘 CRON ───→ 读 ranked + market_context → 生成 scenarios
```

## 排名权重

| 权重 | 条件 |
|:---:|------|
| +3 | 引擎一 STAGE3 满分 |
| +2 | 引擎一 STAGE3 或 引擎二 Top10%+ |
| +2 | 匹配主线（market_context.main_themes） |
| +1 | 引擎一 STAGE2 或 引擎二 Top15 |

P0(权重>=5) = 双引擎+主线命中，最高优先级。

## 收盘复盘 Step 4 逻辑

1. 读 candidate_pool.engine2.ranked（已排序）
2. 读 market_context（主线方向）
3. P0+P1 → Scenario 1（顺势建仓）
4. Scenario 2/3/4（观望/防御/止损）
5. 禁止 LLM 即兴选股——候选必须来自 ranked

## 相关脚本

| 脚本 | 用途 |
|------|------|
| engine2_ranker.py | 引擎二：选股+查行业+交叉排名 |
| early_breakout_scanner.py | 引擎一：三阶段扫描 |
