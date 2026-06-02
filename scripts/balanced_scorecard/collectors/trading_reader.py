"""交易日志读取器。读取 trade_log.json 并解析交易记录。"""
import json
import os
from datetime import date, timedelta


TRADE_LOG_PATH = os.path.expanduser("~/.hermes/scripts/output/trade_log.json")


def load_trade_log() -> list[dict]:
    """加载完整交易日志"""
    if not os.path.exists(TRADE_LOG_PATH):
        return []
    with open(TRADE_LOG_PATH, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return []


def get_trades_for_date(date_str: str) -> list[dict]:
    """获取某日的所有交易"""
    logs = load_trade_log()
    return [
        t for t in logs
        if t.get("timestamp", "").startswith(date_str)
    ]


def get_trades_for_range(start_date: str, end_date: str) -> list[dict]:
    """获取日期范围内的所有交易"""
    logs = load_trade_log()
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    results = []
    for t in logs:
        ts = t.get("timestamp", "")[:10]
        if not ts:
            continue
        try:
            d = date.fromisoformat(ts)
            if start <= d <= end:
                results.append(t)
        except ValueError:
            continue
    return results
