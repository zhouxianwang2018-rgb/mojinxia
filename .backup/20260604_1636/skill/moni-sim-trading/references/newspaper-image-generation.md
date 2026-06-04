# 报纸风格图片生成

盘前分析、引擎扫描、收盘复盘三者使用统一报纸风格图片交付。

## 生成命令

```bash
# 盘前分析
python3 ~/.hermes/scripts/premarket_image.py --type premarket /tmp/report.md

# 收盘复盘
python3 ~/.hermes/scripts/premarket_image.py --type close /tmp/report.md

# 引擎二排名
python3 ~/.hermes/scripts/premarket_image.py --type rank /tmp/report.md

# 周度复盘
python3 ~/.hermes/scripts/premarket_image.py --type weekly /tmp/report.md
```

`--type` 参数自动设置对应的标题、副标题和尾部总结标签：

| --type | 标题 | 副标题 | 尾部标签 |
|--------|------|--------|----------|
| `premarket` | 摸金虾·盘前早参 | MO JIN XIA · PRE-MARKET BRIEFING | 📊 盘前定调 |
| `close` | 摸金虾·收盘复盘 | MO JIN XIA · CLOSING REVIEW | 📊 收盘定调 |
| `rank` | 摸金虾·引擎扫描 | MO JIN XIA · ENGINE SCAN | 📊 排名摘要 |
| `weekly` | 摸金虾·周度复盘 | MO JIN XIA · WEEKLY REVIEW | 📊 周度总结 |

**⚠️ 常见错误**：引擎二排名不要用 `--type close`——虽然报头会在 TITLE_MAP 中找到对应的「收盘复盘」，但尾部硬编码的「📊 盘前定调」会和正文脱节（已修复为按 report_type 动态取值）。引擎二必须用 `--type rank`。

## 引擎扫描 · 双引擎合并布局（2026-06-04）

引擎扫描报纸**必须包含引擎一的扫描结果**，形成「双引擎扫描」报纸。板块顺序：

1. 🔥 引擎一 · STAGE3 弹簧触发（表格：代码/名称/价格/异动日/异动涨幅/MA5/评分）
2. 🟡 引擎一 · STAGE2 回踩确认（表格：代码/名称/价格/异动日/异动涨幅/MA5）
3. 📊 引擎二 · 条件选股排名（表格：排名/代码/名称/涨幅/换手/市值/行业）
4. 🔗 双引擎交叉命中（命中为 ⭐ 最高优先级，无命中说明原因）
5. 📌 策略约束（风险等级/仓位上限/新仓禁制/当前持仓）

Markdown 标题用 `# 🔍 双引擎扫描 · {日期}`，各板块用 `##` 小节。

## 渲染引擎

**纯 Playwright，无回退链。** Chromium 探测顺序：snap → 系统 → Playwright 捆绑。

| 项目 | 值 |
|------|-----|
| 输出目录 | `~/.hermes/tmp/premarket/`（**不是 /tmp/**，snap chromium 沙箱禁止访问 /tmp） |
| Chromium 路径 | `/snap/chromium/current/usr/lib/chromium-browser/chrome` |
| Node 工作目录 | `~/.hermes/hermes-agent`（node_modules/playwright 所在地） |
| 沙箱 | `--no-sandbox --disable-setuid-sandbox`（snap 必须） |

## 字体

使用**系统本地字体**，不从 Google Fonts CDN 加载（snap chromium 无网络访问）：

| 用途 | 字体栈 |
|------|--------|
| 标题 | `Noto Serif CJK SC` → `SimHei` → serif |
| 正文 | `Noto Serif CJK SC` → `SimSun` → serif |
| 标签/日期 | `Noto Sans CJK SC` → sans-serif |

系统已安装 `fonts-noto-cjk`，Noto Serif CJK SC / Noto Sans CJK SC 开箱可用。

## HTML 模板要素

红色报头（#b30000→#8b0000 渐变），报纸质感的米白底色（#fffdf8）。

### 标准板块结构
1. **报头区**: 红色 masthead + 中文标题（letter-spacing: 6px）+ 英文副标题
2. **日期栏**: 日期 + 系统名 + 免责声明
3. **内容区**: 按 markdown 内容自动渲染（表格、高亮框、新闻条目等）

### CSS 关键样式
```css
.paper { width: 800px; background: #fffdf8; }
.masthead { background: linear-gradient(180deg, #b30000 0%, #8b0000 100%); }
.section-title { color: #b30000; border-left: 4px solid #b30000; }
table th { background: #b30000; color: white; }
```

## 故障排查

### Chromium 缺失 / 网关重启后图片生成失败

**根因**：Hermes gateway 重启（08:28 的 SIGTERM）会清理 npx 临时缓存，Playwright 捆绑的 Chromium 恰好放在 npx 缓存中而非 `~/.cache/ms-playwright/`。重启后 `chromium.launch()` 找不到浏览器。

**修复**（已在 premarket_image.py 中实现）：
1. 优先使用 snap chromium（`/snap/chromium/current/usr/lib/chromium-browser/chrome`）——2026-05-14 安装，不受 npx 缓存影响
2. 启动参数加 `--no-sandbox --disable-setuid-sandbox`
3. HTML 文件保存到 `~/.hermes/tmp/premarket/`（snap 可访问），不用 `/tmp/`
4. 字体改用系统本地 Noto CJK，不依赖 Google Fonts CDN

### 图片内容为空/残缺

- **snap chromium 渲染空白**：HTML 路径在 `/tmp/` → snap 沙箱隔离。改为 `~/.hermes/tmp/premarket/`
- **中文乱码/缺字**：Google Fonts CDN 不可达 → 改用系统 `Noto Serif CJK SC`
- **分页/截断**：weasyprint 默认分页 → 已移除 weasyprint，Playwright `fullPage: true` 天然单页

## Cron 验证技巧

**⚠️ 关键陷阱：Agent 会跳过图片生成步骤。**

Agent 在处理多步骤 prompt 时经常在倒数第二步就输出最终回复，跳过错在最后的图片生成步骤。2026-06-04 实例：盘前定调完成 5 步分析后，直接输出纯文本 markdown，跳过图片生成。

**防御写法（写入 cron prompt 的最终回复段落）：**
```
## 最终回复（必须）
1. 先用 cat <<'MDEOF' 将下方完整 markdown 写入 /tmp/premarket_report.md
2. 执行 PNG=$(python3 ~/.hermes/scripts/premarket_image.py /tmp/premarket_report.md)
3. 最终回复：第一行 MEDIA:$PNG，第二行一句话摘要。禁止输出纯文本替代品。
```

不要在步骤列表中把图片生成作为最后一个编号步骤——移到独立的「最终回复」段落并明确标注「必须」。
