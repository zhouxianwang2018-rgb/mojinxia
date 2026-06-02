# 摸金虾 · 模拟盘交易系统

> 版本 1.0 · 2026-06-02

A 股全自动模拟盘交易系统。七道 CRON 接力流水线覆盖 09:00→15:05 全交易日，策略文件驱动状态机，双引擎选股 + 三体联动，五级硬编码风控。

## 文件索引

| 文档 | 说明 |
|------|------|
| [DEVELOPMENT.md](DEVELOPMENT.md) | **开发手册**（迭代节奏 / 版本管理 / 回滚） |
| [changelog.md](changelog.md) | 版本历史（v0.1 → v1.0） |
| [roadmap.md](roadmap.md) | 路线图 |
| [architecture.md](architecture.md) | 架构决策记录（ADR） |
| [cron-optimization.md](cron-optimization.md) | CRON 分层优化方案 |
| [triple-linkage.md](triple-linkage.md) | 三体联动选股架构 |
| [audits/](audits/) | 每周审计报告（Scenario 审计 + 平衡计分卡） |

## 技术栈

- **运行时**: Hermes CRON 引擎（7 job，deepseek-v4-pro）
- **数据**: 妙想金融 API（东方财富） + 模拟交易 API
- **交付**: QQ bot，报纸风格 PNG（Playwright） + 结构化 Markdown
- **运维**: 策略链状态机（pending→active→closed），`calc_risk_state.py` 硬编码风控

## 关键指标

| 指标 | 目标 | 当前 |
|------|------|------|
| 年化收益 | +100%（¥2,000,000） | +11%（¥1,107,958） |
| 月增长率 | ≥15% | 6月待核算 |
| CRON 健康 | 7/7 正常 | 7/7 |
