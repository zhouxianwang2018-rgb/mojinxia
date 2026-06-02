"""平衡计分卡引擎。编排采集→计算→聚合→输出。"""
from datetime import date, timedelta
from balanced_scorecard.types import (
    ScorecardResult, Trend, DIMENSION_WEIGHTS, grade_from_score,
)
from balanced_scorecard.collectors.strategy_reader import load_last_n
from balanced_scorecard.collectors.trading_reader import load_trade_log
from balanced_scorecard.collectors.pattern_reader import load_patterns
from balanced_scorecard.calculators.returns import compute as compute_returns
from balanced_scorecard.calculators.risk import compute as compute_risk
from balanced_scorecard.calculators.execution import compute as compute_execution
from balanced_scorecard.calculators.evolution import compute as compute_evolution
from balanced_scorecard.registry.defects import init_from_skill_md
from balanced_scorecard.registry.predictions import load as load_predictions


def run(date_str: str = "today", window_days: int = 30) -> ScorecardResult:
    if date_str == "today":
        target_date = date.today().isoformat()
    elif date_str == "last":
        recent = load_last_n(1)
        target_date = recent[0]["trading_day"] if recent else date.today().isoformat()
    else:
        target_date = date_str

    # 1. 数据采集
    strategy_files = load_last_n(window_days, before_date=target_date)
    if not strategy_files:
        raise ValueError(f"No strategy files within {window_days} days before {target_date}")

    trades = load_trade_log()
    patterns = load_patterns()
    defects = init_from_skill_md()
    predictions = load_predictions()

    # 2. 四维计算
    dim_returns = compute_returns(strategy_files)
    dim_risk = compute_risk(strategy_files)
    dim_execution = compute_execution(strategy_files, trades)
    dim_evolution = compute_evolution(strategy_files, patterns, defects, predictions)

    # 3. 加权聚合
    total = (
        dim_returns.score * dim_returns.weight
        + dim_risk.score * dim_risk.weight
        + dim_execution.score * dim_execution.weight
        + dim_evolution.score * dim_evolution.weight
    )

    # 4. 趋势对比
    trend = _compute_trend(target_date, total)

    # 5. 异常收集
    anomalies = []
    for d in [dim_returns, dim_risk, dim_execution, dim_evolution]:
        anomalies.extend(d.flags)
    if total < 50:
        anomalies.append(f"总分{total:.1f}低于50 → D级，系统存在严重问题")

    grade = grade_from_score(total)

    return ScorecardResult(
        date=target_date,
        total=round(total, 1),
        grade=grade,
        dimensions={
            "returns": dim_returns,
            "risk": dim_risk,
            "execution": dim_execution,
            "evolution": dim_evolution,
        },
        trend=trend,
        anomalies=anomalies,
        generated_at=date.today().isoformat(),
    )

def _compute_trend(target_date: str, current_score: float) -> Trend:
    import json, os
    from balanced_scorecard.presentation.json_writer import load_scorecard

    trend = Trend()

    # 从 index 中找真实交易日（跳过周末/假期）
    INDEX_PATH = os.path.expanduser("~/.hermes/cron/state/moni/scorecard/index.json")
    entries = []
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH) as f:
            try:
                entries = json.load(f).get("entries", [])
            except (json.JSONDecodeError, TypeError):
                pass
    dates_with_data = sorted(set(e["date"] for e in entries))

    if not dates_with_data:
        return trend

    try:
        td = date.fromisoformat(target_date)
    except ValueError:
        return trend

    # vs yesterday: 最近一个 < target_date 的交易日
    for d in reversed(dates_with_data):
        if d < target_date:
            prev = load_scorecard(d)
            if prev and prev.get("total"):
                trend.vs_yesterday = round(current_score - prev["total"], 1)
            break

    # vs 7 trading days ago (或最接近的)
    target_idx = None
    for i, d in enumerate(dates_with_data):
        if d >= target_date:
            target_idx = i
            break
    if target_idx is not None and target_idx >= 7:
        prev_date = dates_with_data[target_idx - 7]
        prev = load_scorecard(prev_date)
        if prev and prev.get("total"):
            trend.vs_7d_ago = round(current_score - prev["total"], 1)
    elif target_idx is not None and target_idx > 0:
        # < 7 trading days of data, use earliest
        prev = load_scorecard(dates_with_data[0])
        if prev and prev.get("total"):
            trend.vs_7d_ago = round(current_score - prev["total"], 1)

    # vs 30 trading days ago
    if target_idx is not None and target_idx >= 30:
        prev_date = dates_with_data[target_idx - 30]
        prev = load_scorecard(prev_date)
        if prev and prev.get("total"):
            trend.vs_30d_ago = round(current_score - prev["total"], 1)
    elif target_idx is not None and target_idx > 0:
        prev = load_scorecard(dates_with_data[0])
        if prev and prev.get("total"):
            trend.vs_30d_ago = round(current_score - prev["total"], 1)

    return trend
