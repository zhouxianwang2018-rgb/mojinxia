"""模式数据读取器。读取大海牛车牌跟踪和引擎1模式数据。"""
import json
import os
from typing import Optional


PATTERNS_PATH = os.path.expanduser("~/.hermes/scripts/output/dahainiu_patterns.json")


def load_patterns() -> Optional[dict]:
    """加载大海牛模式数据"""
    if not os.path.exists(PATTERNS_PATH):
        return None
    with open(PATTERNS_PATH, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return None


def get_engine1_accuracy(patterns: Optional[dict]) -> dict:
    """从模式数据中提取引擎1的准确率指标"""
    if not patterns:
        return {
            "direction_accuracy": 0.0,
            "extreme_hit_rate": 0.0,
            "concept_consistency": 0.0,
            "total_batches": 0,
            "scored_batches": 0,
        }

    batches = patterns.get("batches", [])
    cross = patterns.get("cross_analysis", {})

    total = len(batches)
    scored = sum(1 for b in batches if b.get("status") == "completed")

    direction_acc = cross.get("direction_accuracy", 0.0)
    extreme_hit = cross.get("extreme_hit_rate", 0.0)
    concept_cons = cross.get("concept_consistency", 0.0)

    return {
        "direction_accuracy": direction_acc,
        "extreme_hit_rate": extreme_hit,
        "concept_consistency": concept_cons,
        "total_batches": total,
        "scored_batches": scored,
    }
