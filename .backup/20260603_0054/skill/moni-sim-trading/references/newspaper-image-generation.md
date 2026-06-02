# 报纸风格图片生成

盘前分析、尾盘执行、收盘复盘三者使用统一报纸风格图片交付。

### 生成命令

```bash
# 盘前分析
python3 ~/.hermes/scripts/premarket_image.py --type premarket /tmp/report.md

# 收盘复盘
python3 ~/.hermes/scripts/premarket_image.py --type close /tmp/report.md

# 尾盘执行（生成 HTML → 手动 Playwright 截图）
# 尾盘使用 baoyu-infographic skill 生成报纸风信息图，流程不同
```

`--type` 参数自动设置对应的标题和副标题：
| --type | 标题 | 副标题 |
|--------|------|--------|
| `premarket` | 摸金虾·盘前早参 | MO JIN XIA · PRE-MARKET BRIEF |
| `close` | 摸金虾·收盘复盘 | MO JIN XIA · CLOSING REVIEW |

## HTML 模板要素

红色报头（#b30000→#8b0000 渐变），报纸质感的米白底色（#fffdf8），Noto Serif SC 衬线字体。

### 标准板块结构
1. **报头区**: 红色 masthead + 中文标题（letter-spacing: 6px）+ 英文副标题
2. **日期栏**: 日期 + 系统名 + 免责声明
3. **风险信号**（尾盘专属）: EMERGENCY/DEFENSIVE 熔断警告框
4. **账户快照**: 四指标卡片（总资产/可用/持仓市值/仓位%）
5. **今日操作**: 表格（时间/方向/标的/数量/价格/理由）
6. **持仓扫描**: 表格（代码/名称/成本/现价/盈亏%/状态）
7. **午后预警**（尾盘专属）: 13:00 侦察写入的预警信息
8. **决策依据**: 一句话逻辑
9. **月目标追踪**: 当前/目标/缺口/进度

### CSS 关键样式
```css
.paper { width: 800px; background: #fffdf8; }
.masthead { background: linear-gradient(180deg, #b30000 0%, #8b0000 100%); }
.section-title { color: #b30000; border-left: 4px solid #b30000; }
table th { background: #b30000; color: white; }
.alert-box { background: #fff5f5; border: 2px solid #b30000; }
```

## Playwright 截图流程

`premarket_image.py` 脚本位于 `~/.hermes/scripts/premarket_image.py`，使用 Playwright 截图。

### 关键路径
```python
PLAYWRIGHT_CWD = os.path.expanduser("~/.hermes/hermes-agent")
PLAYWRIGHT_NODE_PATH = os.path.join(PLAYWRIGHT_CWD, "node_modules")
```

### 截图脚本模板
```javascript
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 860, height: 100 });
  await page.goto('file:///tmp/moni_afternoon_20260601.html', { waitUntil: 'networkidle', timeout: 15000 });
  const bodyHeight = await page.evaluate(() => document.querySelector('.paper').offsetHeight + 80);
  await page.setViewportSize({ width: 860, height: bodyHeight });
  await page.screenshot({ path: '/tmp/moni_afternoon_20260601.png', fullPage: true });
  await browser.close();
})();
```

### Python 调用
```python
import os, subprocess
js_path = "/tmp/screenshot_xxx.js"
with open(js_path, "w") as f:
    f.write(js)
env = os.environ.copy()
env["NODE_PATH"] = PLAYWRIGHT_NODE_PATH
result = subprocess.run(["node", js_path], cwd=PLAYWRIGHT_CWD, env=env,
                        capture_output=True, text=True, timeout=30)
os.unlink(js_path)
```

## Cron 验证技巧

修改 cron 的交付格式后，手动 `cronjob(action='run')` 会被 Step -1 重复检测拦截（当天已执行过）。

**验证方法：** 直接生成样图。
1. 用 `write_file` 写入 HTML 到 `/tmp/`
2. 用 Playwright 截图转 PNG（参考上述流程）
3. 在回复中用 `MEDIA:/path/to/image.png` 展示

正式验证等待下一个交易日自动触发。
