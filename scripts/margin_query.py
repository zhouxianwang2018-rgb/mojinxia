#!/usr/bin/env python3
"""两融数据查询 — 输出 JSON 到 stdout。

用法:
  python3 margin_query.py
  → {"total_margin_balance": 27623.41, "daily_change": 8.66, ...}

输出格式与 market_context.margin_trading 一致。
若 API 失败返回 {"error": "..."}，exit code != 0。
"""

import sys, json
sys.path.insert(0, '/home/agentuser/.hermes/scripts')
from moni_engine import mx_query

def query():
    d = mx_query("沪深A股 融资余额 融券余额 融资买入额")
    if not d.get('success') and not d.get('ok'):
        return {"error": f"mx_query failed: {d.get('message', 'unknown')}"}

    try:
        tables = d['data']['data']['searchDataResultDTO']['dataTableDTOList']
    except (KeyError, TypeError):
        return {"error": "unexpected API response structure"}

    if not tables:
        return {"error": "no tables returned"}

    t = tables[0]
    tb = t.get('table', {})
    rtb = t.get('rawTable', {})
    head = tb.get('headName', [])

    if not head or '325566' not in rtb:
        return {"error": "required fields (325566=融资余额) not found"}

    dates_raw = [h.split('(')[0] for h in head]

    # 融资余额 (元)
    margin_series = [float(rtb['325566'][i]) for i in range(len(rtb['325566']))]
    # 融资买入额 (元)
    buy_series = [float(rtb['335816'][i]) for i in range(len(rtb['335816']))] if '335816' in rtb else []
    # 融券余额 (元)
    seclending = float(rtb['331886'][0]) if '331886' in rtb else None

    n = len(margin_series)
    today_balance = margin_series[0] / 1e8  # 亿元
    yesterday_balance = margin_series[1] / 1e8 if n > 1 else today_balance
    daily_change = today_balance - yesterday_balance
    daily_change_pct = (daily_change / yesterday_balance * 100) if yesterday_balance else 0

    # 5日趋势
    trend_5d = []
    for i in range(min(5, n)):
        bal = round(margin_series[i] / 1e8, 2)
        net = None
        if i + 1 < n:
            net = round((margin_series[i] - margin_series[i+1]) / 1e8, 2)
        trend_5d.append({
            "date": dates_raw[i],
            "balance": bal,
            "net_buy": net
        })

    # 趋势定性
    changes = [t['net_buy'] for t in trend_5d if t['net_buy'] is not None]
    if not changes:
        trend_signal = '数据不足'
    elif all(c > 0 for c in changes):
        trend_signal = '持续流入'
    elif all(c < 0 for c in changes):
        trend_signal = '持续流出'
    elif daily_change > 100:
        trend_signal = '大幅流入'
    elif daily_change < -100:
        trend_signal = '大幅流出'
    elif daily_change > 0:
        trend_signal = '震荡回升'
    elif daily_change < 0:
        trend_signal = '高位回落'
    else:
        trend_signal = '平稳'

    # 风险标记
    risk_flag = None
    if daily_change < -200:
        risk_flag = '融资骤降>200亿'
    elif abs(daily_change_pct) > 3:
        risk_flag = f'融资异常波动 {daily_change_pct:+.1f}%'

    result = {
        "as_of": dates_raw[0],
        "total_margin_balance": round(today_balance, 2),
        "unit": "亿元",
        "daily_change": round(daily_change, 2),
        "daily_change_pct": round(daily_change_pct, 2),
        "margin_buy_amount": round(buy_series[0] / 1e8, 2) if buy_series else None,
        "seclending_balance": round(seclending / 1e8, 2) if seclending else None,
        "trend_5d": trend_5d,
        "trend_signal": trend_signal,
        "top_sectors_buy": [],  # mx_query 不支持行业维度两融数据
        "risk_flag": risk_flag,
    }
    return result


if __name__ == "__main__":
    r = query()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    if 'error' in r:
        sys.exit(1)
