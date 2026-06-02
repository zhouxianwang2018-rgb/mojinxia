#!/usr/bin/env python3
"""Scenario 审计脚本 — 分析策略文件中 scenario 的触达率、质量和设计缺陷。

Usage:
    python3 scenario_audit.py              # 审计所有交易日
    python3 scenario_audit.py --latest 5   # 最近5个交易日
    python3 scenario_audit.py --markdown   # 输出 markdown 报告
"""
import json
import os
import sys
from datetime import date, timedelta
from collections import defaultdict
from typing import Optional

STRATEGIES_DIR = os.path.expanduser("~/.hermes/cron/state/moni/strategies")

# 场景分类
CATEGORY = {
    "emergency":       "🛑 熔断",
    "emergency_clear": "🛑 熔断",
    "stop_loss":       "🛡️ 止损",
    "reduce":          "📉 减仓",
    "buy":             "📈 买入",
    "hold":            "⏸️ 持有",
    "hold_cash":       "⏸️ 持有",
    "retry_unfreeze":  "🔧 运维",
    "monitor_only":    "🔧 运维",
}

ATTACK_TYPES  = {"buy", "reduce"}
DEFENSE_TYPES = {"emergency", "emergency_clear", "stop_loss", "hard_constraint_rule2"}
PASSIVE_TYPES = {"hold", "hold_cash", "monitor_only", "retry_unfreeze"}


def load_strategy(date_str: str) -> Optional[dict]:
    path = os.path.join(STRATEGIES_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_all_strategies() -> list[dict]:
    results = []
    if not os.path.exists(STRATEGIES_DIR):
        return results
    for fname in sorted(os.listdir(STRATEGIES_DIR)):
        if fname.endswith(".json") and not fname.startswith("."):
            with open(os.path.join(STRATEGIES_DIR, fname)) as f:
                d = json.load(f)
            if d.get("status") in ("closed", "active"):
                results.append(d)
    return results


def classify(scenario_type: str) -> str:
    for prefix, label in CATEGORY.items():
        if scenario_type.startswith(prefix):
            return label
    return f"❓ {scenario_type}"


def is_attack(t: str) -> bool:
    return t in ATTACK_TYPES


def is_defense(t: str) -> bool:
    return t in DEFENSE_TYPES


def is_passive(t: str) -> bool:
    return t in PASSIVE_TYPES


def audit(strategies: list[dict]) -> dict:
    """主审计函数。返回结构化结果。"""
    all_scenarios = []
    files_with_data = 0

    for d in strategies:
        day = d["trading_day"]
        mode = d.get("current_strategy", {}).get("mode", "?")
        scenarios = d.get("current_strategy", {}).get("scenarios", [])
        exec_logs = d.get("execution_log", [])

        if not scenarios:
            continue
        files_with_data += 1

        # Build set of scenario types that were matched
        # scenario_matched can be type name OR partial if-condition text
        matched_types = set()
        matched_texts = set()
        for log in exec_logs:
            sm = log.get("scenario_matched", "null")
            if sm and sm != "null":
                matched_texts.add(sm)
                # Also try to match by type keyword
                for prefix in CATEGORY:
                    if prefix in sm.lower() or sm.startswith(prefix):
                        matched_types.add(prefix)

        for s in scenarios:
            stype = s.get("type", "?")
            sif = s.get("if", "?")
            sthen = s.get("then", "?")

            # Check if triggered: type match OR if-condition substring match
            triggered = stype in matched_types
            if not triggered:
                # Fuzzy: check if any matched text is a substring of if/then
                for mt in matched_texts:
                    if (sif and len(sif) > 10 and (sif[:30] in mt or mt[:30] in sif)) or \
                       (sthen and len(sthen) > 10 and (sthen[:30] in mt or mt[:30] in sthen)):
                        triggered = True
                        break

            all_scenarios.append({
                "day": day,
                "mode": mode,
                "type": stype,
                "if": sif,
                "then": sthen,
                "triggered": triggered,
            })

    if not all_scenarios:
        return {"error": "no scenarios found", "total": 0, "triggered": [], "untouched": []}

    triggered = [s for s in all_scenarios if s["triggered"]]
    untouched = [s for s in all_scenarios if not s["triggered"]]

    # Hit rate
    total = len(all_scenarios)
    hit_rate = len(triggered) / total

    # By category
    attack_count = sum(1 for s in all_scenarios if is_attack(s["type"]))
    defense_count = sum(1 for s in all_scenarios if is_defense(s["type"]))
    passive_count = sum(1 for s in all_scenarios if is_passive(s["type"]))

    attack_hit = sum(1 for s in triggered if is_attack(s["type"]))
    defense_hit = sum(1 for s in triggered if is_defense(s["type"]))

    # Dead conditions: attack scenarios that never triggered
    dead_attacks = [s for s in untouched if is_attack(s["type"])]

    # Duplicate detection: same if/then across days
    seen = {}
    duplicates = []
    for s in all_scenarios:
        key = (s["type"], s["if"][:80])
        if key in seen:
            duplicates.append((seen[key]["day"], s["day"], s["type"], s["if"][:80]))
        else:
            seen[key] = s

    # Recommendations
    recommendations = []
    if attack_hit == 0 and attack_count > 0:
        recommendations.append({
            "severity": "P0",
            "finding": f"进攻型scenario零触达 ({attack_count}个全部未触发)",
            "action": "将绝对价格触发（'反弹至X元'）改为相对指标（'连续2日未创新低'/'站上5日线'）",
        })
    if duplicates:
        recommendations.append({
            "severity": "P1",
            "finding": f"{len(duplicates)}组重复scenario跨文件复制",
            "action": "复盘创建次日策略时，继承前日scenario应做条件调整而非原文复制",
        })
    if passive_count > total * 0.4:
        recommendations.append({
            "severity": "P1",
            "finding": f"被动型scenario占比{passive_count/total:.0%}，过高",
            "action": "将'hold_cash'和'monitor_only'合并为每日固定观察项，释放scenario名额给进攻型",
        })

    return {
        "total": total,
        "hit_rate": hit_rate,
        "triggered_count": len(triggered),
        "untouched_count": len(untouched),
        "attack_count": attack_count,
        "defense_count": defense_count,
        "passive_count": passive_count,
        "attack_hit": attack_hit,
        "defense_hit": defense_hit,
        "dead_attacks": dead_attacks,
        "duplicates": duplicates,
        "recommendations": recommendations,
        "triggered": triggered,
        "untouched": untouched,
        "files_analyzed": files_with_data,
    }


def format_markdown(result: dict) -> str:
    if "error" in result:
        return f"⚠️ 审计失败: {result['error']}"

    lines = []
    lines.append("## 🔍 Scenario 审计报告")
    lines.append(f"**{date.today().isoformat()} | {result['files_analyzed']}个交易日 | {result['total']}个scenario**")
    lines.append("")

    # Summary table
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 总 scenarios | {result['total']} |")
    lines.append(f"| 触达数 | {result['triggered_count']} ({result['hit_rate']:.0%}) |")
    lines.append(f"| 攻防比 | {result['attack_count']}进攻 : {result['defense_count']}防御 : {result['passive_count']}被动 |")
    lines.append(f"| 进攻型触达 | {result['attack_hit']}/{result['attack_count']} |")
    lines.append(f"| 防御型触达 | {result['defense_hit']}/{result['defense_count']} |")
    lines.append("")

    # Recommendations
    if result["recommendations"]:
        lines.append("### ⚠️ 建议")
        for r in result["recommendations"]:
            lines.append(f"- **{r['severity']}** {r['finding']} → {r['action']}")
        lines.append("")

    # Dead attacks
    if result["dead_attacks"]:
        lines.append("### 💀 死亡条件（进攻型从未触发）")
        lines.append("| 日期 | 类型 | 条件 |")
        lines.append("|------|------|------|")
        for s in result["dead_attacks"][:10]:
            lines.append(f"| {s['day']} | {s['type']} | {s['if'][:80]} |")
        lines.append("")

    # Duplicates
    if result["duplicates"]:
        lines.append("### 📋 重复 scenario")
        for first_day, dup_day, stype, condition in result["duplicates"][:5]:
            lines.append(f"- `{condition}` → {first_day} 和 {dup_day} 完全相同")

    # Per-category breakdown
    lines.append("")
    lines.append("### 按类型触达率")
    lines.append("| 类型 | 总数 | 触达 | 触达率 |")
    lines.append("|------|:----:|:----:|:------:|")

    by_type = defaultdict(lambda: {"total": 0, "hit": 0})
    all_s = result["triggered"] + result["untouched"]
    for s in all_s:
        cat = classify(s["type"])
        by_type[cat]["total"] += 1
        if s["triggered"]:
            by_type[cat]["hit"] += 1

    for cat in sorted(by_type.keys()):
        d = by_type[cat]
        rate = d["hit"] / d["total"] if d["total"] > 0 else 0
        lines.append(f"| {cat} | {d['total']} | {d['hit']} | {rate:.0%} |")

    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    latest_n = None
    fmt = "markdown"

    i = 0
    while i < len(args):
        if args[i] == "--latest" and i + 1 < len(args):
            latest_n = int(args[i + 1])
            i += 2
        elif args[i] == "--markdown":
            fmt = "markdown"
            i += 1
        elif args[i] == "--json":
            fmt = "json"
            i += 1
        else:
            i += 1

    all_strategies = load_all_strategies()
    if latest_n and latest_n < len(all_strategies):
        all_strategies = all_strategies[-latest_n:]

    result = audit(all_strategies)

    if fmt == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(result))
