# 摸金虾 开发手册

> v1.0.1 · 2026-06-03

本文档定义摸金虾的全生命周期流程：需求 → 迭代 → 开发 → 发布 → 运维。

---

## 一、需求管理

### 1.1 从想法到规格

```
有人提想法 ──→ 需求清单.md（一行一条）──→ 迭代计划选中 ──→ 需求池/SRS-NNN-xxx.md
                   │                              │
                   │ 轻量：描述+关闭条件+优先级      │ 五段完整规格
                   │                              │
                   └── 不通过 ← 讨论后关闭          └── 实施 → 完成 → SRS 更新日志写一笔
```

### 1.2 操作规则

| 时机 | 操作 | 文件 |
|------|------|------|
| 有新想法时 | 在 `需求清单.md` 新增一行，状态=待排期 | 需求清单 |
| 迭代排期时 | 从需求清单挑，状态→已排期，填关联=SRS-NNN | 迭代计划 |
| 排中后 | 在 `需求池/` 建 SRS 文件（五段模板），SRS-编号=需求清单#号 | 需求池 |
| 实施完成 | SRS 更新日志写一笔完成记录 | SRS |
| 想法被否 | 状态→已关闭，写关闭原因 | 需求清单 |

### 1.3 SRS 文件规范

- 命名：`需求池/SRS-NNN-description.md`，NNN=需求清单#号，三位补零
- 结构：业务需求 → 方案设计 → 风险与缓解 → 关联 → 更新日志
- 方案设计不展开时状态=设计完成待排期，展开后状态=实施中

---

## 二、问题管理

### 2.1 两层问题，一条链路

```
问题清单.md（设计文档）          issues.json（运行态）
┌─────────────────────┐       ┌──────────────────────┐
│ 已知 Bug/瓶颈        │       │ 每日盯盘发现的异常      │
│ 审计发现的系统性问题   │       │ CRON 报错 / 策略不一致   │
│ 长期跟踪             │       │ 临时记录、快速关闭       │
└─────────┬───────────┘       └──────────┬───────────┘
          │                              │
          │  系统性/需设计                 │  临时/当天能修
          ▼                              ▼
     进入迭代计划                     当天或周六修，
     升级为 SRS                       修完即关
```

### 2.2 操作规则

| 来源 | 写入哪 | 何时清 |
|------|------|------|
| 盯盘红灯 | `issues.json` | 周六修完移 done，P0 当天修 |
| 审计报警 | `问题清单.md` | 排入迭代后状态→已排期，修完→已关闭 |
| 临时异常 | `issues.json` | 修完即删 |
| 结构性问题 | `问题清单.md` | 长期跟踪，可能升级为 SRS |

### 2.3 issues.json 条目格式

```json
{
  "id": "issue-20260603-001",
  "severity": "P1",
  "source": "盯盘-策略一致性",
  "detail": "risk_state.level=defensive 但 mode=aggressive",
  "status": "open",
  "opened": "2026-06-03",
  "resolution": null
}
```

---

## 三、迭代管理

### 3.1 三层节奏

| 层级 | 频率 | 做什么 | 不改什么 |
|------|------|------|---------|
| **盯盘** | 每日 15:05 后 | 三信号检查，红灯记 issues.json | 不改代码 |
| **迭代** | 每周六 | 跑审计 + 排下周 + 集中改 | — |
| **大版本** | 每月末 | 月目标核算 + 回溯 + roadmap 刷新 | — |

### 3.2 每周六流程

1. **计分卡**：`python3 ~/.hermes/scripts/balanced_scorecard --format markdown`
2. **Scenario 审计**：`python3 ~/.hermes/scripts/scenario_audit.py`
3. **排期**：打开 `迭代计划.md`——
   - 从 `需求清单.md` 挑 1-2 条待排期 → 状态→已排期 → 建 SRS
   - 从 `问题清单.md` 挑需修的 → 状态→已排期
   - 更新迭代计划，写本周要做的
4. **集中改**：改 CRON prompt → 改脚本 → 更新 skill → `cronjob run` 验证
5. **关 issues**：修完的从 `issues.json` 移 done 或删除

### 3.3 迭代计划格式

```
# 迭代 N · 日期范围

## 来自需求清单
- [ ] REQ-001 xxx → SRS-NNN

## 来自问题清单
- [ ] BUG-001 yyy → 直接修

## 本周不排
- REQ-003 — 阻塞于 xxx
```

### 3.4 盘中安全规则

- **09:00-15:05 不改任何 CRON prompt**
- **不改策略链文件**（`strategies/{date}.json`）
- 盯盘发现的问题记 issues.json，不改代码

### 3.5 变更安全规则

- **改完必验证**：`cronjob run` 或当天数据生成样图
- **双写**：改 CRON prompt 同时更新 `moni-sim-trading` skill
- **改 ≥3 个 CRON → 次版本号 +1**

---

## 四、发布管理

### 4.1 版本号规则

```
v<主版本>.<次版本>.<修订号>

主版本：架构重构、策略链大改     → 2.0
次版本：新功能、≥3 个 CRON 改动  → 1.1
修订号：单 CRON bugfix、脚本修复  → 1.0.1
```

### 4.2 同步机制

通过 `sync-to-git.sh` 一键同步 Hermes 运行态到 GitHub 仓库：

```bash
~/.hermes/scripts/sync-to-git.sh
```

做的事：
1. 从 Hermes 各目录 cp 最新文件到 git 仓库
2. 检查 diff，无变化则跳过
3. 自动导出当前 CRON prompt 到 `crons/`
4. 存档 Hermes 状态到 `.backup/YYYYMMDD_HHMM/`

### 4.3 Commit 规范

```
v<版本号>: <一句话总结>

- <改动1>
- <改动2>
```

### 4.4 发布 Checklist

```
[ ] 所有改动 CRON 已 cronjob run 验证
[ ] skill SKILL.md 已同步更新
[ ] changelog.md 已追加新版本条目
[ ] SRS 更新日志已记录完成
[ ] 迭代计划.md 已完成项打勾
[ ] sync-to-git.sh 执行无 diff 残留
[ ] git commit 含版本号 + 改动摘要
[ ] git tag v1.x.x
[ ] git push --tags
```

---

## 五、运维管理

### 5.1 每日盯盘三信号

| 信号 | 看什么 | 红灯条件 |
|------|------|:--:|
| CRON 健康 | `cronjob list` → `last_status` + `last_delivery_error` | 任一非 `ok` |
| 策略一致性 | `risk_state.level` vs `current_strategy.mode` | 不一致 |
| 硬约束穿透 | `execution_log` 中 `deviation` 非 null | 有偏离 |

三全绿 → 无需操作。红灯 → 记 `issues.json`，不当天修。

### 5.2 回滚流程

| 场景 | 操作 |
|------|------|
| 单 CRON prompt | 从 Git 历史取旧版 → `cronjob update` 回灌 |
| 脚本回滚 | `git checkout <tag> -- scripts/xxx.py` |
| 批量回滚 | 用 `.backup/` 快照恢复 |

**回滚安全原则**：盘中不回滚、单 CRON 优先、回滚也是版本（发新版本号）、Git tag 不可删。

### 5.3 回滚后必做

```
[ ] cronjob run 验证
[ ] changelog 标注 [REVERTED]
[ ] 根因分析 → 记入问题清单.md
[ ] 发修订版本号
```

---

## 六、关键文件路径

| 类别 | 文件 | 路径 |
|------|------|------|
| 规划 | 需求清单 | `~/.hermes/products/摸金虾/roadmap/需求清单.md` |
| 规划 | 问题清单 | `~/.hermes/products/摸金虾/roadmap/问题清单.md` |
| 规划 | 迭代计划 | `~/.hermes/products/摸金虾/roadmap/迭代计划.md` |
| 规划 | SRS 文件 | `~/.hermes/products/摸金虾/roadmap/需求池/SRS-NNN-*.md` |
| 规划 | 版本历史 | `~/.hermes/products/摸金虾/changelog.md` |
| 系统 | 架构 | `~/.hermes/products/摸金虾/docs/architecture.md` |
| 系统 | 运行态 issues | `~/.hermes/cron/state/moni/issues.json` |
| 系统 | 策略文件 | `~/.hermes/cron/state/moni/strategies/{date}.json` |
| 运维 | skill | `~/.hermes/skills/finance/moni-sim-trading/SKILL.md` |
| 运维 | sync 脚本 | `~/.hermes/scripts/sync-to-git.sh` |
| 运维 | git 仓库 | `/tmp/mojinxia-repo` |
