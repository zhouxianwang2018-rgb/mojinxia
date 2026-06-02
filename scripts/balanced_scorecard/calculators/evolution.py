"""进化维度计算器。权重 15%。"""
import re
import hashlib
from datetime import date, timedelta
from balanced_scorecard.types import DimensionScore, SubScore


ERROR_PATTERNS = {
    "process":    [r"未加载", r"策略不流通", r"文件缺失", r"状态", r"索引"],
    "discipline": [r"超限", r"突破上限", r"未查avail", r"仓位", r"cap"],
    "risk":       [r"止损未执行", r"未止损", r"扛单", r"stop_loss"],
    "judgment":   [r"override", r"偏离", r"自行判断", r"自由发挥"],
    "data":       [r"API空", r"数据异常", r"null", r"返回空", r"数据流"],
}
RECIDIVISM_WINDOW = 20


def compute(
    strategy_files: list[dict],
    patterns: dict | None,
    defects: dict | None,
    predictions: dict | None,
) -> DimensionScore:
    sub_scores = []
    flags = []

    # 1. 重复错误率 (权重 0.20)
    rs, rd, rr = _recidivism_rate(strategy_files)
    sub_scores.append(SubScore(name="重复错误率", score=rs, weight=0.20, detail=rd, raw_value=rr))

    # 2. 缺陷修复进度 (权重 0.20)
    ds, dd, dr, df = _defect_progress(defects)
    sub_scores.append(SubScore(name="缺陷修复进度", score=ds, weight=0.20, detail=dd, raw_value=dr))
    flags.extend(df)

    # 3. 策略迭代速度 (权重 0.20)
    ivs, ivd, ivr = _iteration_velocity(strategy_files)
    sub_scores.append(SubScore(name="策略迭代速度", score=ivs, weight=0.20, detail=ivd, raw_value=ivr))

    # 4. 信号准确率 (权重 0.20)
    sas, sad, sar = _signal_accuracy(patterns, predictions)
    sub_scores.append(SubScore(name="信号准确率", score=sas, weight=0.20, detail=sad, raw_value=sar))

    # 5. Scenario 质量 (权重 0.20) — 触达率 + 重复检测
    sqs, sqd, sqr = _scenario_quality(strategy_files)
    sub_scores.append(SubScore(name="Scenario质量", score=sqs, weight=0.20, detail=sqd, raw_value=sqr))
    if sqs < 30:
        flags.append(f"Scenario触达率仅{sqr:.0%}，大量死条件 → 需审计")

    total = sum(ss.score * ss.weight for ss in sub_scores)

    # P0 锁上限
    p0_open = _count_p0_open(defects)
    if p0_open > 0:
        total = min(total, 50.0)
        flags.append(f"P0缺陷{p0_open}个未清零 → 进化维度上限锁50")

    return DimensionScore(
        name="evolution", label="进化", weight=0.15,
        score=round(total, 1), sub_scores=sub_scores, flags=flags,
    )


def _classify_deviation(dev_text: str) -> str:
    if not dev_text or dev_text == "null":
        return "unknown"
    for error_type, patterns in ERROR_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, dev_text):
                return error_type
    return "unknown"


def _context_hash(log_entry: dict) -> str:
    action = log_entry.get("action", "")
    code = log_entry.get("code", "")
    key = f"{code}|{action[:50]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def _recidivism_rate(files: list[dict]) -> tuple[float, str, float]:
    all_devs = []
    for f in files:
        for log in f.get("execution_log", []):
            dev = log.get("deviation", "null")
            if dev and dev != "null":
                all_devs.append({
                    "date": f.get("trading_day", ""),
                    "type": _classify_deviation(dev),
                    "hash": _context_hash(log),
                })

    if not all_devs:
        return 100.0, "无偏离记录", 0.0

    recidivisms = 0
    for i, dev in enumerate(all_devs):
        if not dev["date"]:
            continue
        try:
            dev_date = date.fromisoformat(dev["date"])
        except ValueError:
            continue
        for j in range(i):
            prev = all_devs[j]
            if not prev["date"]:
                continue
            try:
                prev_date = date.fromisoformat(prev["date"])
            except ValueError:
                continue
            if (dev_date - prev_date).days > RECIDIVISM_WINDOW:
                continue
            if prev["type"] == dev["type"] and prev["hash"] == dev["hash"]:
                recidivisms += 1
                break

    rate = recidivisms / len(all_devs)
    score = max(0.0, (1.0 - rate) * 100)
    detail = f"复发{recidivisms}次 / {len(all_devs)}次偏离"
    return score, detail, rate


def _defect_progress(defects: dict | None) -> tuple[float, str, float, list[str]]:
    flags = []
    if not defects or not defects.get("defects"):
        return 50.0, "缺陷表未初始化", 0.0, ["缺陷表未初始化"]

    all_defects = defects["defects"]
    resolved = sum(1 for d in all_defects if d.get("status") == "resolved")
    total = len(all_defects)
    progress = resolved / total

    score = progress * 100
    detail = f"修复{resolved}/{total}"

    p0_open = sum(1 for d in all_defects
                  if d.get("severity") == "P0" and d.get("status") != "resolved")
    if p0_open > 0:
        flags.append(f"P0缺陷{p0_open}个未清零 → 进化维度上限锁50")

    return score, detail, progress, flags


def _count_p0_open(defects: dict | None) -> int:
    if not defects:
        return 1
    return sum(1 for d in defects.get("defects", [])
               if d.get("severity") == "P0" and d.get("status") != "resolved")


def _iteration_velocity(files: list[dict]) -> tuple[float, str, float]:
    if not files:
        return 50.0, "无数据", 0.0

    recent = files[-10:] if len(files) >= 10 else files
    scenario_counts = [len(f.get("current_strategy", {}).get("scenarios", [])) for f in recent]
    avg_scenarios = sum(scenario_counts) / len(scenario_counts) if scenario_counts else 0
    density_score = min(100.0, max(0.0, (avg_scenarios - 2) / 6 * 100))

    all_overrides = []
    for f in files:
        all_overrides.extend(f.get("overrides", []))
    override_score = max(0.0, 100.0 - len(all_overrides) * 25.0)

    score = (density_score * 0.5 + override_score * 0.5)
    detail = f"场景密度{avg_scenarios:.1f}个 | override{len(all_overrides)}次"
    return score, detail, avg_scenarios


def _signal_accuracy(patterns: dict | None, predictions: dict | None) -> tuple[float, str, float]:
    acc1 = 0.0
    acc2 = 0.0
    has_e1 = False
    has_e2 = False

    if patterns:
        cross = patterns.get("cross_analysis", {})
        da = cross.get("direction_accuracy")
        if da is not None:
            acc1 = da
            has_e1 = True

    if predictions:
        preds = predictions.get("predictions", [])
        verified = [p for p in preds if p.get("verifications", {}).get("t5") is not None]
        if verified:
            correct = sum(1 for p in verified
                         if (p.get("signal_direction") == "buy"
                             and p["verifications"]["t5"] > p.get("signal_price", 0))
                         or (p.get("signal_direction") == "sell"
                             and p["verifications"]["t5"] < p.get("signal_price", 0)))
            acc2 = correct / len(verified)
            has_e2 = True

    if not has_e1 and not has_e2:
        return 50.0, "无验证数据，默认50分", 0.5

    if has_e1 and has_e2:
        accuracy = acc1 * 0.6 + acc2 * 0.4
    elif has_e1:
        accuracy = acc1
    else:
        accuracy = acc2

    score = accuracy * 100
    detail = f"引擎1: {acc1:.0%} | 引擎2: {acc2:.0%}"
    return score, detail, accuracy


def _scenario_quality(files: list[dict]) -> tuple[float, str, float]:
    """Scenario 质量：触达率（3日以上）+ 重复检测惩罚。

    只评估 ≥3 天前的 scenario（给触发留时间窗口）。
    重复 scenario 跨文件出现 → 扣分（说明策略继承时未调整条件）。
    """
    from datetime import date as dt_date

    today = dt_date.today()
    total = 0
    triggered = 0
    duplicates = 0
    seen_conditions: set[tuple[str, str]] = set()

    for f in files:
        day_str = f.get("trading_day", "")
        try:
            file_date = dt_date.fromisoformat(day_str)
        except ValueError:
            continue

        # 只评估 ≥3 天前的文件
        age = (today - file_date).days
        if age < 3:
            continue

        scenarios = f.get("current_strategy", {}).get("scenarios", [])
        exec_logs = f.get("execution_log", [])

        # Build matched set
        matched_texts = set()
        for log in exec_logs:
            sm = log.get("scenario_matched", "null")
            if sm and sm != "null":
                matched_texts.add(sm)

        for s in scenarios:
            total += 1
            stype = s.get("type", "?")
            sif = s.get("if", "?")

            # Detect duplicates
            condition_key = (stype, sif[:60])
            if condition_key in seen_conditions:
                duplicates += 1
            seen_conditions.add(condition_key)

            # Check if triggered: type keyword in matched texts
            matched = False
            for mt in matched_texts:
                if stype in mt.lower():
                    matched = True
                    break
                if sif and len(sif) > 10 and (sif[:30] in mt or mt[:30] in sif):
                    matched = True
                    break
            if matched:
                triggered += 1

    if total == 0:
        return 50.0, "无≥3日scenario可评估", 0.0

    hit_rate = triggered / total
    # 重复率惩罚：>30%重复 → 扣分
    dup_rate = duplicates / total if total > 0 else 0
    dup_penalty = max(0.0, (dup_rate - 0.3) * 50)  # >30%重复开始扣，最多扣35分

    base_score = hit_rate * 100
    # 触达率>50%=满分，<10%=零分
    score = max(0.0, min(100.0, (hit_rate - 0.10) / 0.40 * 100))
    score = max(0.0, score - dup_penalty)

    detail = f"触达{triggered}/{total}({hit_rate:.0%})"
    if dup_rate > 0.3:
        detail += f" | 重复率{dup_rate:.0%}⚠️"
    return score, detail, hit_rate
