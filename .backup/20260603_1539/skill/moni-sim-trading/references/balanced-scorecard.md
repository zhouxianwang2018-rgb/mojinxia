# 平衡计分卡（Balanced Scorecard）

独立于模拟盘主流程的四维绩效评估系统。只读消费策略链数据，零耦合。纯 Python stdlib，零第三方依赖。

## 快速使用

```bash
cd ~/.hermes/scripts

python3 -m balanced_scorecard                      # 今天的
python3 -m balanced_scorecard --format markdown    # 只看报告
python3 -m balanced_scorecard --last 7             # 最近7个交易日
python3 -m balanced_scorecard --trend 30           # 30日趋势
python3 -m balanced_scorecard --window 30 date     # 指定日期+窗口
```

### CLI 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `date` | 日期，默认 today | `2026-06-01` / `last` |
| `--format` | 输出格式 | `markdown`（人可读）/ `json` / `both` |
| `--last N` | 最近N个交易日 | `--last 7` |
| `--trend N` | N日趋势线 | `--trend 30` |
| `--window N` | 计算窗口天数 | `--window 30`（默认） |

## 数据流

```
策略链文件 (strategies/*.json) ──→ collectors/strategy_reader
trade_log.json                ──→ collectors/trading_reader
dahainu_patterns.json        ──→ collectors/pattern_reader
                                      │
                              ┌───────┴────────┐
                              ▼      ▼      ▼      ▼
                         returns  risk  execution  evolution
                         (40%)   (25%)   (20%)     (15%)
                              │      │      │      │
                              └──────┴──────┴──────┘
                                      │
                                 engine.aggregate()
                                      │
                              ┌───────┴────────┐
                              ▼                ▼
                        scorecard.json    markdown报告
```

## 架构

三层管道：Collectors（只读数据采集）→ Calculators（纯函数计算）→ Presentation（JSON+Markdown输出）。配两套自有轻量状态：缺陷状态机 + 信号注册表。

```
~/.hermes/scripts/balanced_scorecard/
├── engine.py          ← 编排入口
├── types.py           ← 数据契约
├── collectors/        ← 只读 reader
├── calculators/       ← 四个纯函数计算器
├── registry/          ← 自有状态
└── presentation/      ← 输出层
```

### 计算器接口契约

```python
compute_returns(files: list[dict]) -> DimensionScore
compute_risk(files: list[dict]) -> DimensionScore
compute_execution(files: list[dict], trades: list[dict]) -> DimensionScore
compute_evolution(files, patterns, defects, predictions) -> DimensionScore
```

所有计算器都是纯函数，相同输入永远产生相同输出。

## 四维权重

| 维度 | 权重 | KPI |
|------|:----:|-----|
| 💰 收益 | 40% | 月收益达成率(50%)·盈亏比(20%)·胜率(15%)·年化进度(15%) |
| 🛡️ 风控 | 25% | 硬约束遵守率(35%)·止损执行率(25%)·最大回撤(25%)·熔断天数(15%) |
| ⚙️ 执行 | 20% | 策略偏离率(35%)·Override质量(20%)·Cron可靠性(25%)·滑点控制(20%) |
| 🧬 进化 | 15% | 重复错误率(20%)·缺陷修复(20%)·策略迭代(20%)·信号准确率(20%)·Scenario质量(20%) |

## 进化维度特殊规则

- **P0 锁上限**：P0 缺陷未清零 → 进化维度上限锁 50 分
- **重复错误检测**：同错误类型 + 同上下文哈希，20 个交易日内出现 ≥2 次 → 标记复发
- **错误分类**：process / discipline / risk / judgment / data / unknown（自动正则匹配）

### Scenario质量 KPI（2026-06-01 新增）

解决之前只看 scenario 数量不看质量的盲点。

- **触达率**: 只评估 ≥3 天前的 scenario（给触发留时间窗口）。>50%满分，<10%零分
- **重复惩罚**: 跨文件相同 (type, if-condition) 的 scenario 占比 >30% 开始扣分
- **发现**: 首次审计触达率仅 9%，重复率 45%——大量"反弹至 X 价格"类死条件从未触发

## 等级映射

```
≥85 🟢 A级 — 职业级
70-84 🟡 B级 — 及格
50-69 🟠 C级 — 警告
<50  🔴 D级 — 失能
```

## 缺陷状态机

`~/.hermes/cron/state/moni/scorecard/known_defects.json` — 11 条初始缺陷（全 resolved），从 moni-sim-trading SKILL.md 已知缺陷表初始化。缺陷状态在计分卡运行时自动更新，不依赖任何 cron。

## 输出位置

```
~/.hermes/cron/state/moni/scorecard/
├── index.json                  ← 历史索引
├── known_defects.json          ← 11条初始缺陷（all resolved）
├── predictions.json            ← 引擎2信号注册表（待填充）
└── daily/
    └── scorecard_{date}.json   ← 每日计分卡
```

## 嵌入收盘复盘

收盘复盘 cron (`38f4374a2705`) 的 Step 6 已嵌入。复盘消息末尾自动追加计分卡。出错静默跳过不阻塞主流程。

## 关键设计决策

- **零依赖**：纯 Python stdlib，不引入第三方包
- **确定性**：四个计算器全是纯函数，不依赖 LLM 判断
- **零耦合**：不嵌入任何 cron，不修改任何策略链文件
- **只读消费**：所有数据源都是 Read-Only

## 已知局限

- 收益计算依赖策略链文件中的总资产快照，如果 execution_log 未记录 total_assets，会从 risk_state 反推（peak_total × (1 - drawdown)）
- 滑点计算从 action 文本正则提取信号价（`@价格`），如果 details 缺 fill_price 则跳过
- 信号准确率（引擎2）依赖 predictions.json 中的回填数据，目前该文件为空
- 仅 3 个交易日数据时，月度收益率几乎无意义
