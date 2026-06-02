"""缺陷状态机。管理 known_defects.json。"""
import json
import os
from datetime import date
from typing import Optional


DEFECTS_PATH = os.path.expanduser("~/.hermes/cron/state/moni/scorecard/known_defects.json")


def load() -> dict:
    if not os.path.exists(DEFECTS_PATH):
        return {"defects": [], "last_sync": ""}
    with open(DEFECTS_PATH, "r") as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return {"defects": [], "last_sync": ""}


def save(data: dict):
    os.makedirs(os.path.dirname(DEFECTS_PATH), exist_ok=True)
    data["last_sync"] = date.today().isoformat()
    with open(DEFECTS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def init_from_skill_md() -> dict:
    if os.path.exists(DEFECTS_PATH):
        return load()

    defaults = {
        "defects": [
            {"id": "D-001", "title": "策略不流通（盘后策略盘中看不到）",
             "severity": "P0", "category": "process", "status": "resolved",
             "opened_at": "2026-05-27", "resolved_at": "2026-05-28",
             "resolution": "策略链+Step0加载"},
            {"id": "D-002", "title": "orders API不可靠（空返回但交易已发生）",
             "severity": "P0", "category": "data", "status": "resolved",
             "opened_at": "2026-05-28", "resolved_at": "2026-05-28",
             "resolution": "moni_check_trades.py双重验证"},
            {"id": "D-003", "title": "锁仓未校验（不查avail就下单）",
             "severity": "P0", "category": "discipline", "status": "resolved",
             "opened_at": "2026-05-28", "resolved_at": "2026-05-28",
             "resolution": "交易前强制查avail"},
            {"id": "D-004", "title": "单次仓位跳变过大",
             "severity": "P1", "category": "discipline", "status": "resolved",
             "opened_at": "2026-05-28", "resolved_at": "2026-05-29",
             "resolution": "硬约束仓位上限检查"},
            {"id": "D-005", "title": "10:00→14:20真空4小时",
             "severity": "P1", "category": "process", "status": "resolved",
             "opened_at": "2026-05-28", "resolved_at": "2026-05-29",
             "resolution": "新增13:00午后检查"},
            {"id": "D-006", "title": "连续回撤无自动熔断",
             "severity": "P1", "category": "risk", "status": "resolved",
             "opened_at": "2026-05-28", "resolved_at": "2026-05-29",
             "resolution": "calc_risk_state.py硬编码规则"},
            {"id": "D-007", "title": "盘后策略与盘中执行脱节",
             "severity": "P1", "category": "process", "status": "resolved",
             "opened_at": "2026-05-27", "resolved_at": "2026-05-29",
             "resolution": "策略链流通+硬约束"},
            {"id": "D-008", "title": "CRON重复触发无防护",
             "severity": "P1", "category": "process", "status": "resolved",
             "opened_at": "2026-05-29", "resolved_at": "2026-05-29",
             "resolution": "Step-1安全检查"},
            {"id": "D-009", "title": "模型降级（盘中交易用deepseek-chat）",
             "severity": "P2", "category": "process", "status": "resolved",
             "opened_at": "2026-05-29", "resolved_at": "2026-05-29",
             "resolution": "午盘/尾盘/复盘升级deepseek-v4-pro"},
            {"id": "D-010", "title": "15:00多CRON并发抢API",
             "severity": "P2", "category": "process", "status": "resolved",
             "opened_at": "2026-05-29", "resolved_at": "2026-05-29",
             "resolution": "错峰排布15:02~15:15"},
            {"id": "D-011", "title": "API失败无降级方案",
             "severity": "P3", "category": "data", "status": "resolved",
             "opened_at": "2026-05-29", "resolved_at": "2026-05-29",
             "resolution": "重试一次+跳过+记录api_error"},
        ],
        "last_sync": date.today().isoformat(),
    }
    save(defaults)
    return defaults


def summary() -> dict:
    data = load()
    all_d = data["defects"]
    return {
        "total": len(all_d),
        "resolved": sum(1 for d in all_d if d["status"] == "resolved"),
        "open": sum(1 for d in all_d if d["status"] == "open"),
        "p0_open": sum(1 for d in all_d if d["severity"] == "P0" and d["status"] == "open"),
        "p1_open": sum(1 for d in all_d if d["severity"] == "P1" and d["status"] == "open"),
    }
