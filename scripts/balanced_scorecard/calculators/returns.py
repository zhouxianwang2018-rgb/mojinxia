"""收益维度计算器。权重 40%。"""
from balanced_scorecard.types import DimensionScore, SubScore

MONTHLY_TARGET = 0.15


def compute(strategy_files: list[dict]) -> DimensionScore:
    sub_scores = []

    # 1. 月收益达成率 (权重 0.50)
    ms, md, mr = _monthly_return_rate(strategy_files)
    sub_scores.append(SubScore(name="月收益达成率", score=ms, weight=0.50, detail=md, raw_value=mr))

    # 2. 盈亏比 (权重 0.20)
    rs, rd, rr = _profit_loss_ratio(strategy_files)
    sub_scores.append(SubScore(name="盈亏比", score=rs, weight=0.20, detail=rd, raw_value=rr))

    # 3. 胜率 (权重 0.15)
    ws, wd, wr = _win_rate(strategy_files)
    sub_scores.append(SubScore(name="胜率", score=ws, weight=0.15, detail=wd, raw_value=wr))

    # 4. 年化进度 (权重 0.15)
    aps, apd, apr = _annual_progress(strategy_files)
    sub_scores.append(SubScore(name="年化进度", score=aps, weight=0.15, detail=apd, raw_value=apr))

    total = sum(ss.score * ss.weight for ss in sub_scores)

    return DimensionScore(
        name="returns", label="收益", weight=0.40,
        score=round(total, 1), sub_scores=sub_scores,
    )


def _monthly_return_rate(files: list[dict]) -> tuple[float, str, float]:
    if not files:
        return 0.0, "无数据", 0.0

    # 从策略文件中提取首尾总资产
    first = files[0]
    latest = files[-1]
    start_total = _extract_total(first)
    end_total = _extract_total(latest)

    if start_total <= 0:
        return 0.0, "无法获取月初资产", 0.0

    monthly_return = (end_total - start_total) / start_total
    achievement = monthly_return / MONTHLY_TARGET if MONTHLY_TARGET > 0 else 0.0
    score = max(0.0, min(100.0, achievement * 100))

    detail = f"月收益{monthly_return:.1%} vs 目标15%，达成率{achievement:.0%}"
    return score, detail, monthly_return


def _profit_loss_ratio(files: list[dict]) -> tuple[float, str, float]:
    wins, losses = [], []
    for f in files:
        for log in f.get("execution_log", []):
            details = log.get("details", {})
            profit = details.get("profit_realized")
            if profit is None:
                continue
            if profit > 0:
                wins.append(profit)
            elif profit < 0:
                losses.append(abs(profit))

    if not losses:
        ratio = 2.0
    elif not wins:
        ratio = 0.0
    else:
        win_avg = sum(wins) / len(wins)
        loss_avg = sum(losses) / len(losses)
        ratio = win_avg / loss_avg if loss_avg > 0 else 2.0

    score = min(100.0, ratio / 2.0 * 100)
    detail = f"盈利{len(wins)}笔 亏损{len(losses)}笔 盈亏比{ratio:.1f}"
    return score, detail, ratio


def _win_rate(files: list[dict]) -> tuple[float, str, float]:
    total_trades = 0
    winning_trades = 0
    for f in files:
        for log in f.get("execution_log", []):
            details = log.get("details", {})
            profit = details.get("profit_realized")
            if profit is not None:
                total_trades += 1
                if profit > 0:
                    winning_trades += 1

    if total_trades == 0:
        wr = 0.5
    else:
        wr = winning_trades / total_trades

    score = max(0.0, min(100.0, (wr - 0.40) / 0.15 * 100))
    detail = f"胜率{wr:.0%}（{winning_trades}/{total_trades}）"
    return score, detail, wr


def _annual_progress(files: list[dict]) -> tuple[float, str, float]:
    if not files:
        return 0.0, "无数据", 0.0

    latest = files[-1]
    current_total = _extract_total(latest)
    init_money = 1_000_000

    # Month number: assume start April (month 4)
    for f in files:
        for log in f.get("execution_log", []):
            d = log.get("details", {})
            if d.get("init_money"):
                init_money = d["init_money"]
                break

    month = 6  # June
    target_path = init_money * (1 + MONTHLY_TARGET) ** (month - 4)
    progress = current_total / target_path if target_path > 0 else 0.0
    score = min(100.0, progress * 100)

    detail = f"¥{current_total:,.0f} / 目标路径¥{target_path:,.0f}（{progress:.0%}）"
    return score, detail, progress


def _extract_total(file: dict) -> float:
    """从策略文件中提取当日总资产。

    优先级:
    1. execution_log details.total_assets（最准确）
    2. risk_state.peak_total × (1 - drawdown_from_peak)（反推）
    """
    # 1. 从 execution_log details 中提取
    for log in file.get("execution_log", []):
        d = log.get("details", {})
        if d.get("total_assets", 0) > 0:
            return d["total_assets"]

    # 2. 从 risk_state 反推
    risk = file.get("risk_state", {})
    peak = risk.get("peak_total", 0)
    dd = risk.get("drawdown_from_peak", 0.0)
    if peak > 0:
        return peak * (1.0 - dd)

    return 0.0
