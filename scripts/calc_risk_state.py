#!/usr/bin/env python3
"""
确定性风险状态计算器。输入今日盈亏和昨日状态，输出新的 risk_state。
复盘 CRON 必须调用此脚本，禁止由 LLM 自行判断 risk_state.level。
"""

import json
import sys
import os
from datetime import date


def load_yesterday_risk(date_str: str) -> dict:
    """从昨日策略文件加载 risk_state"""
    path = os.path.expanduser(f"~/.hermes/cron/state/moni/strategies/{date_str}.json")
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
        return d.get("risk_state", {})
    return {}


def calc(
    today_pnl: float,           # 今日盈亏金额（正=盈利，负=亏损）
    current_total: float,       # 当前总资产
    yesterday: str,             # 昨日日期 YYYY-MM-DD
    peak_total: float = None,   # 历史最高点（默认从策略文件读取）
    parent_consecutive: int = None,  # 昨日收盘后的 consecutive_loss_days（显式传入，绕过策略文件是 start-of-day 值的问题）
) -> dict:
    """返回新的 risk_state"""
    
    yesterday_risk = load_yesterday_risk(yesterday)
    
    # 1. 连续亏损天数
    # 策略文件中的 consecutive_loss_days 是当日起始值（start-of-day），不含当日盈亏
    # 如果调用方传入了 parent_consecutive（收盘后的真实值），优先使用
    if parent_consecutive is not None:
        base = parent_consecutive
    else:
        base = yesterday_risk.get("consecutive_loss_days", 0)
    
    if today_pnl < 0:
        consecutive_loss_days = base + 1
    else:
        consecutive_loss_days = 0
    
    # 2. 回撤计算
    if peak_total is None:
        peak_total = yesterday_risk.get("peak_total", current_total)
    else:
        peak_total = max(peak_total, yesterday_risk.get("peak_total", current_total))
    
    # 更新历史最高点
    if current_total > peak_total:
        peak_total = current_total
    
    drawdown = (peak_total - current_total) / peak_total if peak_total > 0 else 0.0
    
    # 3. 止损触发检测
    stop_loss_triggered = yesterday_risk.get("stop_loss_triggered", False)
    
    # 4. 等级判定（硬编码规则，不做 LLM 判断）
    if consecutive_loss_days >= 3 or drawdown >= 0.08 or stop_loss_triggered:
        level = "emergency"
        hard_position_cap = 0.0
        hard_single_stock_cap = 0.0
        new_position_ban = True
        reason = f"触发熔断: consecutive_loss={consecutive_loss_days}d, drawdown={drawdown:.1%}"
        if stop_loss_triggered:
            reason += ", stop_loss_triggered=true"
    elif consecutive_loss_days >= 2 or drawdown >= 0.05:
        level = "defensive"
        hard_position_cap = 0.30
        hard_single_stock_cap = 0.15
        new_position_ban = True
        reason = f"连续亏损{consecutive_loss_days}天" if consecutive_loss_days >= 2 else f"回撤{drawdown:.1%}触发"
    elif consecutive_loss_days >= 1:
        level = "cautious"
        hard_position_cap = 0.50
        hard_single_stock_cap = 0.25
        new_position_ban = True
        reason = f"昨日亏损，进入谨慎模式"
    elif drawdown >= 0.03:
        level = "cautious"
        hard_position_cap = 0.50
        hard_single_stock_cap = 0.30
        new_position_ban = False
        reason = f"回撤{drawdown:.1%}超过3%警戒线"
    else:
        level = "normal"
        hard_position_cap = 0.80
        hard_single_stock_cap = 0.40
        new_position_ban = False
        reason = "连续盈利，风险正常"
    
    return {
        "level": level,
        "level_reason": reason,
        "consecutive_loss_days": consecutive_loss_days,
        "drawdown_from_peak": round(drawdown, 4),
        "peak_total": peak_total,
        "hard_position_cap": hard_position_cap,
        "hard_single_stock_cap": hard_single_stock_cap,
        "new_position_ban": new_position_ban,
        "stop_loss_triggered": stop_loss_triggered,
    }


if __name__ == "__main__":
    # 命令行调用: python3 calc_risk_state.py <today_pnl> <current_total> <yesterday_date> [peak_total] [parent_consecutive]
    if len(sys.argv) < 4:
        print("Usage: calc_risk_state.py <today_pnl> <current_total> <yesterday_date> [peak_total] [parent_consecutive]", file=sys.stderr)
        print("Output: JSON risk_state to stdout", file=sys.stderr)
        print("  parent_consecutive: 昨日收盘后的 consecutive_loss_days（绕过策略文件 start-of-day 偏移）", file=sys.stderr)
        sys.exit(1)
    
    today_pnl = float(sys.argv[1])
    current_total = float(sys.argv[2])
    yesterday = sys.argv[3]
    peak_total = float(sys.argv[4]) if len(sys.argv) > 4 else None
    parent_consecutive = int(sys.argv[5]) if len(sys.argv) > 5 else None
    
    result = calc(today_pnl, current_total, yesterday, peak_total, parent_consecutive)
    print(json.dumps(result, indent=2, ensure_ascii=False))
