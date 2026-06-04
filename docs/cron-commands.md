# CRON 元数据 + 创建命令

> v1.1 · 2026-06-04

7 条 cronjob 的完整参数。`<YOUR_QQ_ID>` 替换为实际 QQ 用户 ID。

## 元数据总表

| # | 名称 | 时间 | 模型 | Provider | Skills | 交付 |
|:--:|------|:--|------|------|------|:--|
| 1 | 盘前定调 | 09:00 | deepseek-v4-pro | deepseek | mx-financial-assistant, mx-finance-search, mx-finance-data, mx-stocks-screener, mx-macro-data, tencent-ecosystem | QQ |
| 2 | 午盘执行 | 10:00 | deepseek-v4-pro | deepseek | mx-financial-assistant, mx-finance-search, mx-finance-data, mx-stocks-screener, tencent-ecosystem | QQ |
| 3 | 午后侦察 | 13:16 | deepseek-v4-pro | deepseek | mx-financial-assistant, mx-finance-data | QQ |
| 4 | 引擎一 | 14:20 | deepseek-v4-pro | deepseek | early-breakout-detection | local |
| 5 | 引擎二 | 14:25 | deepseek-v4-pro | deepseek | (无) | QQ |
| 6 | 尾盘执行 | 14:35 | deepseek-v4-pro | deepseek | mx-financial-assistant, mx-finance-search, mx-finance-data, mx-stocks-screener, tencent-ecosystem | QQ |
| 7 | 收盘复盘 | 15:05 | deepseek-v4-pro | deepseek | mx-financial-assistant, mx-finance-search, mx-finance-data, tencent-ecosystem | QQ |

## 创建命令

### 1. 盘前定调 (09:00)

```
cronjob action=create name="摸金虾·盘前定调" schedule="0 9 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["mx-financial-assistant","mx-finance-search","mx-finance-data","mx-stocks-screener","mx-macro-data","tencent-ecosystem"] prompt="你是A股模拟盘交易员，当前是盘前时段。任务：盘前分析。只分析不交易。..."
```

### 2. 午盘执行 (10:00)

```
cronjob action=create name="摸金虾·午盘执行" schedule="0 10 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["mx-financial-assistant","mx-finance-search","mx-finance-data","mx-stocks-screener","tencent-ecosystem"] prompt="你是A股模拟盘交易员，当前北京时间10:00（午盘）。你有全自动交易权限。任务：执行策略，不做独立市场侦察。..."
```

### 3. 午后侦察 (13:16)

```
cronjob action=create name="摸金虾·午后侦察" schedule="16 13 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["mx-financial-assistant","mx-finance-data"] prompt="你是A股模拟盘交易员，当前北京时间13:16（午后）。任务：结构化侦察+有限策略更新。只侦察和写快照，不交易。5分钟内完成。..."
```

### 4. 引擎一扫描 (14:20)

```
cronjob action=create name="摸金虾·引擎一扫描" schedule="20 14 * * 1-5" repeat=-1 deliver="local" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["early-breakout-detection"] enabled_toolsets=["terminal","file"] prompt="执行早期突破三阶段扫描，筛选STAGE2/STAGE3候选标的，写入策略文件 candidate_pool.engine1。..."
```

### 5. 引擎二排名 (14:25)

```
cronjob action=create name="摸金虾·引擎二排名" schedule="25 14 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} enabled_toolsets=["terminal","file"] prompt="你是引擎二：条件选股+交叉排名。从策略文件读取引擎一候选，运行 engine2_ranker.py 排名，结果写回策略文件 candidate_pool.engine2.ranked，同时生成报纸图片。..."
```

### 6. 尾盘执行 (14:35)

```
cronjob action=create name="摸金虾·尾盘执行" schedule="35 14 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["mx-financial-assistant","mx-finance-search","mx-finance-data","mx-stocks-screener","tencent-ecosystem"] prompt="你是A股模拟盘交易员，当前北京时间14:35（尾盘）。你有全自动交易权限。..."
```

### 7. 收盘复盘 (15:05)

```
cronjob action=create name="摸金虾·收盘复盘" schedule="5 15 * * 1-5" repeat=-1 deliver="qqbot:<YOUR_QQ_ID>" model={"model":"deepseek-v4-pro","provider":"deepseek"} skills=["mx-financial-assistant","mx-finance-search","mx-finance-data","tencent-ecosystem"] prompt="你是A股模拟盘交易员，当前北京时间15:05（收盘）。任务：收盘复盘+关闭策略+创建次日策略。无交易权限。..."
```

## 完整 Prompt

完整 prompt 内容见 GitHub `crons/` 目录下的 7 个 `.md` 文件。
