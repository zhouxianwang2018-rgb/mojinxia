"""执行维度计算器。权重 20%。"""
import re
import statistics
from balanced_scorecard.types import DimensionScore, SubScore


def compute(strategy_files: list[dict], trade_logs: list[dict]) -> DimensionScore:
    sub_scores = []

    # 1. 策略偏离率 (权重 0.35)
    ds, dd, dr = _deviation_rate(strategy_files)
    sub_scores.append(SubScore(name="策略偏离率", score=ds, weight=0.35, detail=dd, raw_value=dr))

    # 2. Override 质量 (权重 0.20)
    os, od, or_ = _override_quality(strategy_files)
    sub_scores.append(SubScore(name="Override质量", score=os, weight=0.20, detail=od, raw_value=or_))

    # 3. Cron 可靠性 (权重 0.25)
    cs, cd, cr = _cron_reliability(strategy_files)
    sub_scores.append(SubScore(name="Cron可靠性", score=cs, weight=0.25, detail=cd, raw_value=cr))

    # 4. 滑点控制 (权重 0.20)
    ss, sd, sr = _slippage_control(strategy_files)
    sub_scores.append(SubScore(name="滑点控制", score=ss, weight=0.20, detail=sd, raw_value=sr))

    total = sum(ss.score * ss.weight for ss in sub_scores)

    return DimensionScore(
        name="execution", label="执行", weight=0.20,
        score=round(total, 1), sub_scores=sub_scores,
    )


def _deviation_rate(files: list[dict]) -> tuple[float, str, float]:
    deviations = 0
    total = 0
    for f in files:
        for log in f.get("execution_log", []):
            total += 1
            dev = log.get("deviation", "null")
            if dev and dev != "null":
                deviations += 1

    if total == 0:
        rate = 0.0
    else:
        rate = deviations / total

    score = max(0.0, (1.0 - rate / 0.20) * 100)
    detail = f"{deviations}次偏离 / {total}次决策"
    return score, detail, rate


def _override_quality(files: list[dict]) -> tuple[float, str, float]:
    total_overrides = 0
    positive_overrides = 0
    for f in files:
        overrides = f.get("overrides", [])
        for ov in overrides:
            total_overrides += 1
            if ov.get("status") in ("active", "reviewed"):
                positive_overrides += 1

    if total_overrides == 0:
        quality = 1.0
    else:
        quality = positive_overrides / total_overrides

    score = quality * 100
    detail = f"{positive_overrides}/{total_overrides}次有效"
    return score, detail, quality


def _cron_reliability(files: list[dict]) -> tuple[float, str, float]:
    expected_per_day = 3  # 午盘、午后、尾盘
    total_expected = 0
    total_actual = 0

    for f in files:
        total_expected += expected_per_day
        crons_seen = set()
        for log in f.get("execution_log", []):
            c = log.get("cron", "")
            if c:
                crons_seen.add(c)
        total_actual += len(crons_seen)

    if total_expected == 0:
        reliability = 1.0
    else:
        reliability = min(1.0, total_actual / total_expected)

    score = reliability * 100
    detail = f"{total_actual}/{total_expected}次执行"
    return score, detail, reliability


def _slippage_control(files: list[dict]) -> tuple[float, str, float]:
    slippages = []
    for f in files:
        for log in f.get("execution_log", []):
            details = log.get("details", {})
            fill_price = details.get("fill_price")
            if not fill_price:
                continue
            action = log.get("action", "")
            prices = re.findall(r'@(\d+\.?\d*)', action)
            if prices:
                signal_price = float(prices[0])
                if signal_price > 0 and fill_price > 0:
                    slip = abs(fill_price - signal_price) / signal_price
                    slippages.append(slip)

    if not slippages:
        avg_slip = 0.0
    else:
        avg_slip = statistics.mean(slippages)

    score = max(0.0, (1.0 - avg_slip / 0.01) * 100)
    detail = f"平均滑点{avg_slip:.2%}"
    return score, detail, avg_slip
