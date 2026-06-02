"""信号注册表。管理 predictions.json。"""
import json
import os
from datetime import date, timedelta


PREDICTIONS_PATH = os.path.expanduser("~/.hermes/cron/state/moni/scorecard/predictions.json")


def load() -> dict:
    if not os.path.exists(PREDICTIONS_PATH):
        return {"predictions": [], "last_updated": ""}
    with open(PREDICTIONS_PATH, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return {"predictions": [], "last_updated": ""}


def save(data: dict):
    os.makedirs(os.path.dirname(PREDICTIONS_PATH), exist_ok=True)
    data["last_updated"] = date.today().isoformat()
    with open(PREDICTIONS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register(ticker: str, name: str, engine: str, concept: str,
             signal_price: float, direction: str = "buy",
             confidence: str = "medium") -> str:
    data = load()
    pred_id = f"pred-{date.today().isoformat()}-{len(data['predictions']) + 1:03d}"
    prediction = {
        "id": pred_id,
        "date": date.today().isoformat(),
        "ticker": ticker,
        "name": name,
        "engine": engine,
        "concept": concept,
        "signal_price": signal_price,
        "signal_direction": direction,
        "confidence": confidence,
        "verifications": {"t1": None, "t3": None, "t5": None, "t10": None},
    }
    data["predictions"].append(prediction)
    save(data)
    return pred_id


def get_pending_backfills() -> list[dict]:
    today = date.today()
    pending = []
    data = load()
    for p in data["predictions"]:
        try:
            signal_date = date.fromisoformat(p["date"])
        except ValueError:
            continue
        for window, days in [("t1", 1), ("t3", 3), ("t5", 5), ("t10", 10)]:
            target_date = signal_date + timedelta(days=days)
            if target_date <= today and p["verifications"].get(window) is None:
                pending.append({
                    "pred_id": p["id"],
                    "ticker": p["ticker"],
                    "window": window,
                    "target_date": target_date.isoformat(),
                })
    return pending
