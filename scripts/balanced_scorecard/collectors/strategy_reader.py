"""策略链文件读取器。只读，不修改。"""
import json
import os
from datetime import date, timedelta
from typing import Optional


STRATEGIES_DIR = os.path.expanduser("~/.hermes/cron/state/moni/strategies")
INDEX_PATH = os.path.expanduser("~/.hermes/cron/state/moni/strategy_index.json")


def load_strategy(date_str: str) -> Optional[dict]:
    """加载单日策略文件"""
    path = os.path.join(STRATEGIES_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def load_index() -> Optional[dict]:
    """加载策略索引"""
    if not os.path.exists(INDEX_PATH):
        return None
    with open(INDEX_PATH, "r") as f:
        return json.load(f)


def load_range(start_date: str, end_date: str) -> list[dict]:
    """加载日期范围内的所有策略文件，按日期排序"""
    results = []
    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    while current <= end:
        s = load_strategy(current.isoformat())
        if s:
            results.append(s)
        current += timedelta(days=1)
    return results


def load_last_n(n: int, before_date: Optional[str] = None) -> list[dict]:
    """加载最近 n 个有策略文件的交易日（跳过周末/假期）"""
    if before_date is None:
        end = date.today()
    else:
        end = date.fromisoformat(before_date)

    results = []
    for _ in range(n * 3):  # 往前回溯 n*3 天
        s = load_strategy(end.isoformat())
        if s and s.get("status") in ("closed", "active"):
            results.append(s)
            if len(results) >= n:
                break
        end -= timedelta(days=1)

    results.reverse()  # 按时间升序
    return results


def get_execution_logs(date_str: str) -> list[dict]:
    """提取某日的 execution_log"""
    s = load_strategy(date_str)
    if not s:
        return []
    return s.get("execution_log", [])


def get_overrides(date_str: str) -> list[dict]:
    """提取某日的 overrides"""
    s = load_strategy(date_str)
    if not s:
        return []
    return s.get("overrides", [])


def get_risk_state(date_str: str) -> Optional[dict]:
    """提取某日的 risk_state"""
    s = load_strategy(date_str)
    if not s:
        return None
    return s.get("risk_state")
