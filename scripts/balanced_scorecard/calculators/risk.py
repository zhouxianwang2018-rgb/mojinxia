"""风控维度计算器。权重 25%。"""
from balanced_scorecard.types import DimensionScore, SubScore


def compute(strategy_files: list[dict]) -> DimensionScore:
    sub_scores = []

    # 1. 硬约束遵守率 (权重 0.35)
    cs, cd, cr = _constraint_compliance(strategy_files)
    sub_scores.append(SubScore(name="硬约束遵守率", score=cs, weight=0.35, detail=cd, raw_value=cr))

    # 2. 止损执行率 (权重 0.25)
    ss, sd, sr = _stop_loss_execution(strategy_files)
    sub_scores.append(SubScore(name="止损执行率", score=ss, weight=0.25, detail=sd, raw_value=sr))

    # 3. 最大回撤 (权重 0.25)
    ds, dd, dr = _max_drawdown(strategy_files)
    sub_scores.append(SubScore(name="最大回撤", score=ds, weight=0.25, detail=dd, raw_value=dr))

    # 4. 熔断天数 (权重 0.15)
    es, ed, er = _emergency_days(strategy_files)
    sub_scores.append(SubScore(name="熔断天数", score=es, weight=0.15, detail=ed, raw_value=er))

    total = sum(ss.score * ss.weight for ss in sub_scores)

    return DimensionScore(
        name="risk", label="风控", weight=0.25,
        score=round(total, 1), sub_scores=sub_scores,
    )


def _constraint_compliance(files: list[dict]) -> tuple[float, str, float]:
    violations = 0
    total_decisions = 0
    for f in files:
        for log in f.get("execution_log", []):
            total_decisions += 1
            dev = log.get("deviation", "null")
            if dev and dev != "null":
                violations += 1

    if total_decisions == 0:
        compliance = 1.0
    else:
        compliance = 1.0 - (violations / total_decisions)

    score = compliance * 100
    detail = f"{violations}次偏离 / {total_decisions}次决策"
    return score, detail, compliance


def _stop_loss_execution(files: list[dict]) -> tuple[float, str, float]:
    triggered = 0
    executed = 0
    for f in files:
        risk = f.get("risk_state", {})
        if risk.get("stop_loss_triggered"):
            triggered += 1
            for log in f.get("execution_log", []):
                action = log.get("action", "")
                scenario = log.get("scenario_matched", "")
                if "止损" in action or "stop_loss" in scenario:
                    executed += 1
                    break

    if triggered == 0:
        rate = 1.0
    else:
        rate = executed / triggered

    score = rate * 100
    detail = f"触发{triggered}次，执行{executed}次"
    return score, detail, rate


def _max_drawdown(files: list[dict]) -> tuple[float, str, float]:
    if not files:
        return 100.0, "无数据", 0.0

    latest = files[-1]
    risk = latest.get("risk_state", {})
    dd = risk.get("drawdown_from_peak", 0.0)

    # <3%=100, >8%=0, linear
    score = max(0.0, (1.0 - dd / 0.08) * 100)
    score = min(100.0, score)

    detail = f"从高点回撤{dd:.1%}"
    return score, detail, dd


def _emergency_days(files: list[dict]) -> tuple[float, str, float]:
    emergency_count = 0
    total_days = len(files)
    for f in files:
        risk = f.get("risk_state", {})
        if risk.get("level") == "emergency":
            emergency_count += 1

    score = max(0.0, 100.0 - emergency_count * 25.0)
    detail = f"{emergency_count}天熔断 / {total_days}个交易日"
    return score, detail, emergency_count
