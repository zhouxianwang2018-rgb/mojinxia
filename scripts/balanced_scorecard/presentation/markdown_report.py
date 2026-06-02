"""Markdown 报告生成器。"""
from balanced_scorecard.types import ScorecardResult


def _trend_arrow(delta: float | None) -> str:
    if delta is None:
        return "—"
    if delta > 1:
        return f"📈 +{delta:.0f}"
    elif delta < -1:
        return f"📉 {delta:.0f}"
    else:
        return "➡️ ±0"


def _grade_emoji(grade: str) -> str:
    return {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(grade, "⬜")


def _dim_emoji(label: str) -> str:
    return {"收益": "💰", "风控": "🛡️", "执行": "⚙️", "进化": "🧬"}.get(label, "📊")


def format_markdown(result: ScorecardResult) -> str:
    lines = []

    # Header
    lines.append("## 📊 摸金虾 · 交易代理平衡计分卡")
    lines.append(f"**{result.date} | 总分 {result.total} · {_grade_emoji(result.grade)} {result.grade}级**")
    lines.append("")

    # Dimension table
    lines.append("| 维度 | 权重 | 得分 | 趋势 | 关键指标 |")
    lines.append("|------|:----:|:----:|:----:|---------|")

    for name, dim in result.dimensions.items():
        arrow = _trend_arrow(result.trend.vs_yesterday)
        key_metrics = " · ".join(
            f"{ss.name.split('（')[0]}{ss.score:.0f}"
            for ss in dim.sub_scores[:2]
        )
        lines.append(
            f"| {_dim_emoji(dim.label)} {dim.label} "
            f"| {dim.weight:.0%} "
            f"| **{dim.score:.0f}** "
            f"| {arrow} "
            f"| {key_metrics} |"
        )

    lines.append("")

    # Anomalies
    if result.anomalies:
        for a in result.anomalies:
            lines.append(f"> ⚠️ {a}")
        lines.append("")

    # Detail breakdown
    lines.append("### 详细分解")
    lines.append("")
    for name, dim in result.dimensions.items():
        lines.append(f"**{_dim_emoji(dim.label)} {dim.label} ({dim.weight:.0%})**")
        for ss in dim.sub_scores:
            bar = "█" * int(ss.score / 10) + "░" * (10 - int(ss.score / 10))
            lines.append(f"- {bar} {ss.name}: {ss.score:.0f}分 — {ss.detail}")
        if dim.flags:
            for f in dim.flags:
                lines.append(f"  - ⚠️ {f}")
        lines.append("")

    # Trend
    lines.append("### 趋势")
    lines.append("| vs昨日 | vs7日前 | vs30日前 |")
    lines.append("|:------:|:------:|:-------:|")
    lines.append(
        f"| {_trend_arrow(result.trend.vs_yesterday)} "
        f"| {_trend_arrow(result.trend.vs_7d_ago)} "
        f"| {_trend_arrow(result.trend.vs_30d_ago)} |"
    )

    return "\n".join(lines)
