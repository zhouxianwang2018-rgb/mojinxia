#!/usr/bin/env python3
"""
鲁棒交易检测器。解决 orders API 不可靠的问题。

问题场景：
  5/28 orders API 返回 0 条记录，但持仓从 875→4875 股，资金减少 33.9 万。
  CRON 误判为"今日无交易"，导致去重失效。

方案：
  双重验证：orders API + balance/positions 对比。
  任一方法检测到交易 → 确认有交易。
"""

import sys
import json
import os
import hashlib
from datetime import date

STATE_FILE = os.path.expanduser("~/.hermes/cron/state/moni/.trade_snapshot.json")


def snapshot_path() -> str:
    return STATE_FILE


def take_snapshot(balance: dict, positions: dict) -> str:
    """
    保存账户快照，返回快照指纹。
    CRON 首次运行时调用此函数保存状态，
    后续调用 check_trades() 对比差异。
    """
    today = date.today().isoformat()
    positions_sorted = sorted(
        [(p.get("stockCode", ""), p.get("currentAmount", 0), p.get("marketValue", 0))
         for p in positions.get("data", {}).get("records", [])]
    )
    
    snapshot = {
        "date": today,
        "total_assets": balance.get("data", {}).get("totalAssets", 0),
        "available": balance.get("data", {}).get("availableMoney", 0),
        "market_value": balance.get("data", {}).get("marketValue", 0),
        "positions": positions_sorted,
    }
    
    with open(snapshot_path(), "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    
    fingerprint = hashlib.md5(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:8]
    return fingerprint


def check_trades(current_balance: dict, current_positions: dict, orders_result: dict) -> dict:
    """
    三种方式检测今日是否有交易：
    1. orders API 有记录 → 有交易
    2. 快照对比 balance 变化 → 有交易
    3. 快照对比 positions 变化 → 有交易
    
    返回：{"has_trades": bool, "method": str, "details": str}
    """
    today = date.today().isoformat()
    methods = []
    details = []
    
    # Method 1: orders API
    orders = orders_result.get("data", {}).get("records", [])
    if orders:
        order_dates = set()
        for o in orders:
            ct = o.get("createTime", "")
            if ct:
                order_dates.add(ct[:10])
        if today in order_dates or not order_dates:
            methods.append("orders_api")
            actions = []
            for o in orders[:5]:
                bs = "买" if o.get("entrustBs") == 1 else "卖"
                price = o.get("entrustPrice", 0) / (10 ** o.get("priceDec", 1))
                qty = o.get("entrustAmount", 0)
                name = o.get("stockName", "")
                actions.append(f"{bs}{name}{qty}股@{price:.2f}")
            details.append(f"orders API: {len(orders)}条记录 ({'; '.join(actions)})")
    
    # Method 2+3: snapshot comparison
    if os.path.exists(snapshot_path()):
        with open(snapshot_path()) as f:
            snap = json.load(f)
        
        if snap.get("date") == today:
            curr_total = current_balance.get("data", {}).get("totalAssets", 0)
            curr_avail = current_balance.get("data", {}).get("availableMoney", 0)
            curr_mv = current_balance.get("data", {}).get("marketValue", 0)
            
            snap_total = snap.get("total_assets", 0)
            snap_avail = snap.get("available", 0)
            snap_mv = snap.get("market_value", 0)
            
            balance_changed = abs(curr_total - snap_total) > 1  # 允许1元误差
            
            if balance_changed:
                methods.append("balance_diff")
                diff = curr_total - snap_total
                details.append(
                    f"balance变化: {snap_total:,.0f}→{curr_total:,.0f} "
                    f"({diff:+,.0f}), avail {snap_avail:,.0f}→{curr_avail:,.0f}"
                )
            
            # Compare positions
            # Compare only code+amount, ignore marketValue
            curr_pos = sorted([
                (p.get("stockCode", ""), p.get("currentAmount", 0))
                for p in current_positions.get("data", {}).get("records", [])
            ])
            # Strip marketValue from snapshot tuples for comparison
            snap_pos_clean = [(s[0], s[1]) for s in snap.get("positions", [])]
            snap_pos = snap.get("positions", [])
            
            if curr_pos != snap_pos_clean:
                methods.append("positions_diff")
                # Find what changed
                curr_map = {c[0]: c[1] for c in curr_pos}
                snap_map = {s[0]: s[1] for s in snap_pos}
                changes = []
                for code in set(list(curr_map.keys()) + list(snap_map.keys())):
                    old_qty = snap_map.get(code, 0)
                    new_qty = curr_map.get(code, 0)
                    if old_qty != new_qty:
                        changes.append(f"{code}: {old_qty}→{new_qty} ({new_qty-old_qty:+d})")
                details.append(f"持仓变化: {'; '.join(changes)}")
    
    if not methods and not orders:
        return {"has_trades": False, "method": "none", "details": "orders API空+快照无变化"}
    
    return {
        "has_trades": True,
        "method": "+".join(methods),
        "details": " | ".join(details),
    }


def get_traded_stocks(result: dict) -> set:
    """从检测结果中提取已交易的股票代码"""
    traded = set()
    details = result.get("details", "")
    # 从 "orders API: ..." 或 "持仓变化: ..." 中提取代码
    import re
    codes = re.findall(r'\b(\d{6})\b', details)
    return set(codes)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  snapshot  <balance_json> <positions_json>  -- 保存快照", file=sys.stderr)
        print("  check     <balance_json> <positions_json> <orders_json>  -- 检测交易", file=sys.stderr)
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "snapshot":
        balance = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        positions = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        fp = take_snapshot(balance, positions)
        print(json.dumps({"fingerprint": fp, "message": "snapshot saved"}))
    
    elif action == "check":
        balance = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        positions = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        orders = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        result = check_trades(balance, positions, orders)
        print(json.dumps(result, ensure_ascii=False))
