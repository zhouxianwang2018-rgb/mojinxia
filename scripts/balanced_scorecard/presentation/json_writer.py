"""JSON 输出层。保存计分卡文件并维护索引。"""
import json
import os
from datetime import date
from typing import Optional


SCORECARD_DIR = os.path.expanduser("~/.hermes/cron/state/moni/scorecard/daily")
INDEX_PATH = os.path.expanduser("~/.hermes/cron/state/moni/scorecard/index.json")


def save_scorecard(result) -> str:
    os.makedirs(SCORECARD_DIR, exist_ok=True)

    data = {
        "date": result.date,
        "total": result.total,
        "grade": result.grade,
        "dimensions": {
            name: {
                "label": dim.label,
                "weight": dim.weight,
                "score": dim.score,
                "sub_scores": [
                    {"name": ss.name, "score": ss.score, "weight": ss.weight,
                     "detail": ss.detail, "raw_value": ss.raw_value}
                    for ss in dim.sub_scores
                ],
                "flags": dim.flags,
            }
            for name, dim in result.dimensions.items()
        },
        "trend": {
            "vs_yesterday": result.trend.vs_yesterday,
            "vs_7d_ago": result.trend.vs_7d_ago,
            "vs_30d_ago": result.trend.vs_30d_ago,
        },
        "anomalies": result.anomalies,
        "generated_at": result.generated_at,
    }

    filepath = os.path.join(SCORECARD_DIR, f"scorecard_{result.date}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    _update_index(result.date, result.total, result.grade)
    return filepath


def _update_index(date_str: str, total: float, grade: str):
    index = {"entries": [], "last_updated": date.today().isoformat()}

    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            try:
                existing = json.load(f)
                index["entries"] = existing.get("entries", [])
            except (json.JSONDecodeError, TypeError):
                pass

    found = False
    for entry in index["entries"]:
        if entry.get("date") == date_str:
            entry["total"] = total
            entry["grade"] = grade
            found = True
            break
    if not found:
        index["entries"].append({"date": date_str, "total": total, "grade": grade})

    index["entries"].sort(key=lambda e: e["date"])

    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def load_scorecard(date_str: str) -> Optional[dict]:
    filepath = os.path.join(SCORECARD_DIR, f"scorecard_{date_str}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return None
