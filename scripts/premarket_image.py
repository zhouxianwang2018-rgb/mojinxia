#!/usr/bin/env python3
"""摸金虾 · 盘前早参 — 生成报纸风格盘前分析图片。

用法1: 从标准输入读 markdown（cron 首选）
  echo "$MARKDOWN" | python3 premarket_image.py

用法2: 传文件路径
  python3 premarket_image.py /tmp/some_report.md

输出: /tmp/premarket_image_YYYY-MM-DD_HHMMSS.png
"""

import sys, os, json, subprocess, re
from datetime import datetime

OUTPUT_DIR = "/tmp"
PLAYWRIGHT_CWD = os.path.expanduser("~/.hermes/hermes-agent")
PLAYWRIGHT_NODE_PATH = os.path.join(PLAYWRIGHT_CWD, "node_modules")

# ── HTML 模板 ────────────────────────────────────────────
CSS = """
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&family=Noto+Sans+SC:wght@300;400;700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #f0eee8; font-family: 'Noto Serif SC','SimSun','STSong',serif; display: flex; justify-content: center; padding: 40px 20px; }
  .paper { width: 800px; background: #fffdf8; box-shadow: 0 4px 24px rgba(0,0,0,0.12); }
  .masthead { background: linear-gradient(180deg, #b30000 0%, #8b0000 100%); color: white; text-align: center; padding: 24px 40px 16px; border-bottom: 3px solid #660000; }
  .masthead h1 { font-size: 36px; font-weight: 900; letter-spacing: 6px; font-family: 'Noto Serif SC','SimHei',serif; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
  .masthead .subtitle { font-size: 13px; letter-spacing: 3px; opacity: 0.85; margin-top: 2px; font-family: 'Noto Sans SC',sans-serif; }
  .dateline { background: #faf7f0; border-bottom: 2px solid #b30000; padding: 6px 40px; font-size: 12px; color: #888; display: flex; justify-content: space-between; font-family: 'Noto Sans SC',sans-serif; }
  .content { padding: 24px 40px 32px; }
  .section-title { font-size: 20px; font-weight: 900; color: #b30000; border-left: 4px solid #b30000; padding-left: 12px; margin: 24px 0 12px; }
  .section-title:first-child { margin-top: 0; }
  .news-item { margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid #e8e4d8; }
  .news-item:last-child { border-bottom: none; }
  .tag { display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 2px; margin-right: 6px; font-family: 'Noto Sans SC',sans-serif; }
  .tag-red { background: #b30000; color: white; }
  .tag-orange { background: #d4740e; color: white; }
  .tag-blue { background: #2471a3; color: white; }
  .tag-green { background: #1e8449; color: white; }
  .news-item p { font-size: 14px; line-height: 1.8; color: #333; margin-top: 4px; }
  .news-item strong { color: #1a1a1a; }
  table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
  table th { background: #b30000; color: white; padding: 8px 10px; text-align: center; font-weight: 700; font-family: 'Noto Sans SC',sans-serif; font-size: 12px; }
  table td { padding: 7px 10px; border-bottom: 1px solid #e8e4d8; text-align: center; color: #333; }
  table tr:nth-child(even) td { background: #faf7f0; }
  .highlight-box { background: #fff8f0; border: 1px solid #e8c8a0; border-left: 4px solid #b30000; padding: 14px 18px; margin: 14px 0; font-size: 13px; color: #5c3a1e; line-height: 1.8; }
  .highlight-box strong { color: #b30000; }
  .conclusion-box { background: #f8f4f0; border: 2px solid #b30000; padding: 18px 22px; margin: 18px 0; }
  .conclusion-box h3 { color: #b30000; font-size: 16px; margin-bottom: 8px; text-align: center; letter-spacing: 2px; }
  .conclusion-box table { margin: 0; }
  .conclusion-box table th { background: #660000; }
  .footer { border-top: 2px solid #b30000; padding: 10px 40px; text-align: center; font-size: 11px; color: #aaa; font-family: 'Noto Sans SC',sans-serif; }
"""

TITLE_MAP = {
    "premarket": ("摸 金 虾 · 盘 前 早 参", "MO JIN XIA · PRE-MARKET BRIEFING", "盘前"),
    "close":     ("摸 金 虾 · 收 盘 复 盘", "MO JIN XIA · CLOSING REVIEW",      "收盘"),
    "weekly":    ("摸 金 虾 · 周 度 复 盘", "MO JIN XIA · WEEKLY REVIEW",       "周报"),
}

def md_to_html(md_text, date_str=None, report_type="premarket", custom_title=None):
    """Very simple markdown→HTML converter tuned for our premarket report format."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    title_h1, subtitle_en, dateline_label = TITLE_MAP.get(report_type, TITLE_MAP["premarket"])
    if custom_title:
        title_h1 = custom_title

    lines = md_text.strip().split("\n")
    body_parts = []

    i = 0
    in_table = False
    in_news = False
    in_highlight = False
    in_conclusion = False
    conclusion_body = []

    def flush_table():
        nonlocal in_table, table_rows, table_header
        if in_table and table_rows:
            rows = ""
            for row in table_rows:
                cells = "".join(f"<td>{c}</td>" for c in row)
                rows += f"<tr>{cells}</tr>"
            body_parts.append(f"<table><tr>{table_header}</tr>{rows}</table>")
        table_rows = []
        table_header = ""
        in_table = False

    def flush_news():
        nonlocal in_news, news_items
        if in_news and news_items:
            for item in news_items:
                body_parts.append(f'<div class="news-item">{item}</div>')
        news_items = []
        in_news = False

    def flush_highlight():
        nonlocal in_highlight, highlight_lines
        if in_highlight and highlight_lines:
            text = "<br>".join(highlight_lines)
            body_parts.append(f'<div class="highlight-box">{text}</div>')
        highlight_lines = []
        in_highlight = False

    table_rows = []
    table_header = ""
    news_items = []
    highlight_lines = []

    while i < len(lines):
        line = lines[i].rstrip()

        # Section title: ## or ###
        if line.startswith("### "):
            flush_table(); flush_news(); flush_highlight()
            title = line[4:].strip()
            body_parts.append(f'<div class="section-title">{title}</div>')
            i += 1; continue

        if line.startswith("## ") and "盘前" in line:
            # main title — skip (goes in masthead)
            i += 1; continue

        # Tables
        if line.startswith("|") and line.strip().endswith("|"):
            flush_news(); flush_highlight()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if i + 1 < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[i+1]):
                # header row
                flush_table()
                table_header = "".join(f"<th>{c}</th>" for c in cells)
                i += 2; in_table = True; continue
            elif in_table:
                if any(c.strip() for c in cells):  # skip empty
                    table_rows.append(cells)
                i += 1; continue
            else:
                # standalone row — treat as regular text
                i += 1; continue

        # Horizontal rules start/end news sections
        if line.strip() == "---":
            flush_table(); flush_news(); flush_highlight()
            i += 1; continue

        # Bullet lists → news items
        if line.startswith("- ") or line.startswith("* "):
            flush_table(); flush_highlight()
            text = line[2:].strip()
            # Parse tags like **🔴 tag**
            tag_match = re.findall(r'\*\*(.*?)\*\*', text)
            tags_html = ""
            content = text
            for tm in tag_match:
                content = content.replace(f"**{tm}**", "")
                tag_class = "tag-red"
                if any(k in tm for k in ["宏观","券商","政策"]): tag_class = "tag-blue"
                elif any(k in tm for k in ["产业","技术","产品","GTC"]): tag_class = "tag-green"
                elif any(k in tm for k in ["减持","警示","利空","风险","⚠"]): tag_class = "tag-orange"
                tags_html += f'<span class="tag {tag_class}">{tm}</span> '

            content = content.strip().lstrip("：:").strip()
            if not in_news:
                flush_news()
                in_news = True
            news_items.append(f'{tags_html}<strong>{content}</strong>')
            i += 1; continue

        # Highlight / quote blocks
        if line.startswith("> "):
            flush_table(); flush_news()
            if not in_highlight:
                flush_highlight()
                in_highlight = True
            text = line[2:].strip()
            # Bold → strong
            text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
            highlight_lines.append(text)
            i += 1; continue

        # Conclusion
        if "盘前结论" in line or "定调" in line:
            flush_table(); flush_news(); flush_highlight()
            # read until end or next ---
            i += 1; continue

        # Regular paragraph — but skip empty lines within sections
        if line.strip() == "":
            i += 1; continue

        # Fallback: treat as paragraph
        flush_table(); flush_news(); flush_highlight()
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
        body_parts.append(f"<p style='font-size:14px;color:#555;margin:4px 0;line-height:1.8'>{text}</p>")
        i += 1

    # Flush remaining
    flush_table(); flush_news(); flush_highlight()

    body = "\n    ".join(body_parts)

    # Generate conclusion box from known data
    conclusion = """<div class="conclusion-box">
      <h3>📊 盘前定调</h3>
      <p style="text-align:center;font-size:15px;font-weight:700;color:#b30000;margin-top:8px;">
        🏁 详细分析请见上方各板块
      </p>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<style>{CSS}</style></head>
<body>
<div class="paper">
  <div class="masthead">
    <h1>{title_h1}</h1>
    <div class="subtitle">{subtitle_en}</div>
  </div>
  <div class="dateline">
    <span>{date_str} {dateline_label}</span>
    <span>摸金虾模拟盘系统</span>
    <span>仅供参考 · 不构成投资建议</span>
  </div>
  <div class="content">
    {body}
    {conclusion}
  </div>
  <div class="footer">
    摸金虾模拟盘系统自动生成 · {date_str} · 市场有风险，投资需谨慎
  </div>
</div>
</body>
</html>"""
    return html


# ── screenshot via Playwright ─────────────────────────────
def screenshot(html_content):
    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    html_path = os.path.join(OUTPUT_DIR, f"premarket_{now}.html")
    png_path = os.path.join(OUTPUT_DIR, f"premarket_{now}.png")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    js = f"""const {{ chromium }} = require('playwright');
(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({{ width: 860, height: 100 }});
  await page.goto('file://{html_path}', {{ waitUntil: 'networkidle', timeout: 15000 }});
  const bodyHeight = await page.evaluate(() => document.querySelector('.paper').offsetHeight + 80);
  await page.setViewportSize({{ width: 860, height: bodyHeight }});
  await page.screenshot({{ path: '{png_path}', fullPage: true }});
  await browser.close();
  console.log('ok ' + bodyHeight + 'px');
}})();
"""
    js_path = os.path.join(OUTPUT_DIR, f"screenshot_{now}.js")
    with open(js_path, "w") as f:
        f.write(js)

    env = os.environ.copy()
    env["NODE_PATH"] = PLAYWRIGHT_NODE_PATH
    result = subprocess.run(
        ["node", js_path],
        cwd=PLAYWRIGHT_CWD, env=env,
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Clean up temp files
    os.unlink(js_path)
    return png_path


# ── main ──────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="摸金虾 · 报告图片生成器")
    ap.add_argument("input", nargs="?", help="Markdown 文件路径（不传则从 stdin 读取）")
    ap.add_argument("--type", choices=["premarket","close","weekly"], default="premarket",
                    help="报告类型 (default: premarket)")
    ap.add_argument("--title", help="自定义标题（覆盖默认）")
    args = ap.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            md = f.read()
    else:
        md = sys.stdin.read()

    if not md.strip():
        print("ERROR: no input", file=sys.stderr)
        sys.exit(1)

    html = md_to_html(md, report_type=args.type, custom_title=args.title)
    png = screenshot(html)
    print(png)
