#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lightvela-摸金虾 自主交易引擎
================================
被cron定时任务调用，实现全自动交易管理。

职责分配：
  - 时点任务（09:25/10:00/14:30/15:05）→ 由cron调度，本脚本只做数据+交易
  - 分析/决策/通知 → 由cron的prompt（LLM）负责
  - 本脚本提供所有原始数据和交易能力

模式：action=...
  check      — 查持仓+资金（输出JSON给LLM分析）
  xuangai    — 动态选股找今日机会（输出JSON）
  trade      — 执行交易（买入/卖出），参数通过环境变量传递
  news       — 查指定股票的近期新闻
  macro      — 查大盘/外围数据
  balance    — 简单查资金
  daily-log  — 写入操作日志
"""

import os
import sys
import json
import subprocess
import re
import urllib.request
import urllib.error
from datetime import datetime, date

# ===== 全局配置 =====
MX_APIKEY = os.environ.get('MX_APIKEY', 'mkt_MmunPaTizngjVQrh-BGPzU0V0aNEdVtVqJAbImn-XWg')
MX_BASE = 'https://mkapi2.dfcfs.com/finskillshub/api/claw'
MONI_SCRIPT = '/tmp/mx_moni_tmp.py'
OUTPUT_DIR = '/home/agentuser/.hermes/scripts/output'
TRADE_LOG = os.path.join(OUTPUT_DIR, 'trade_log.json')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 配置：止损止盈 =====
STOP_LOSS_PCT = -7.0          # 单只止损线 -7%
POSITION_MAX = 3               # 最大持仓数
SINGLE_MAX_RATIO = 0.40        # 单只最大仓位比例
DRAWDOWN_LIMIT = -8.0          # 总资产回撤上限
DRAWDOWN_REDUCE_TO = 300000    # 触发回撤后减仓到30万

# ===== 工具函数 =====

def ts():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def today_str():
    return date.today().isoformat()

def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default

def run_moni(query: str) -> str:
    """调用模拟盘脚本"""
    env = os.environ.copy()
    env['MX_APIKEY'] = MX_APIKEY
    r = subprocess.run(['python3', MONI_SCRIPT, query],
                       capture_output=True, text=True, timeout=30, env=env)
    return r.stdout

def moni_api(endpoint: str, payload: dict) -> dict:
    """直调模拟盘API"""
    url = f"{MX_BASE}{endpoint}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'apikey': MX_APIKEY
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {'error': str(e)}

def mx_query(toolQuery: str) -> dict:
    """妙想query接口"""
    return moni_api('/query', {'toolQuery': toolQuery})

def mx_news(query: str) -> dict:
    """妙想新闻搜索"""
    return moni_api('/news-search', {'query': query})

def mx_xuangai(keyword: str) -> dict:
    """妙想选股 — 用 stock-screen 端点"""
    return moni_api('/stock-screen', {'keyword': keyword})

def save_json(key: str, data):
    """保存数据到JSON"""
    path = os.path.join(OUTPUT_DIR, f"{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path

# ===== 数据层 =====

def get_balance() -> dict:
    """获取账户资金信息"""
    raw = moni_api('/mockTrading/balance', {'moneyUnit': 1})
    data = raw.get('data', {})
    if data is None:
        return {'error': 'balance API返回空', 'total_assets': 0, 'avail_balance': 0,
                'init_money': 1000000}
    return {
        'total_assets': data.get('totalAssets', 0),
        'avail_balance': data.get('availBalance', 0),
        'frozen_money': data.get('frozenMoney', 0),
        'total_pos_value': data.get('totalPosValue', 0),
        'total_pos_pct': data.get('totalPosPct', 0),
        'nav': data.get('nav', 0),
        'init_money': data.get('initMoney', 1000000),
        'opr_days': data.get('oprDays', 0),
    }

def get_positions() -> list:
    """获取持仓列表"""
    raw = moni_api('/mockTrading/positions', {'moneyUnit': 1})
    data = raw.get('data', {})
    if data is None:
        return []
    pos_list = data.get('posList', [])
    positions = []
    for p in pos_list:
        price_dec = p.get('priceDec', 2)
        cost_dec = p.get('costPriceDec', 2)
        positions.append({
            'name': p.get('secName', ''),
            'code': p.get('secCode', ''),
            'qty': p.get('count', 0),
            'avail': p.get('availCount', 0),
            'cost': p.get('costPrice', 0) / (10 ** cost_dec),
            'current_price': p.get('price', 0) / (10 ** price_dec),
            'market_value': p.get('value', 0),
            'pos_pct': p.get('posPct', 0),
            'profit': p.get('profit', 0),
            'profit_pct': p.get('profitPct', 0),
        })
    return positions

def get_orders(fltOrderDrt=0, fltOrderStatus=0) -> list:
    """获取委托列表"""
    raw = moni_api('/mockTrading/orders', {
        'fltOrderDrt': fltOrderDrt,
        'fltOrderStatus': fltOrderStatus
    })
    return raw.get('data', {}).get('orders', [])

def get_stock_price(code: str) -> dict:
    """查个股实时行情"""
    try:
        d = mx_query(f"{code} 最新价 涨跌幅 成交额 成交量 换手率 今日最高 今日最低 今开 昨收 60日涨跌幅")
        # 从table中提取
        result = {'code': code, 'price': None, 'pct': None,
                  'volume': None, 'turnover': None, 'amount': None,
                  'high': None, 'low': None, 'open': None, 'pre_close': None}
        tables = d.get('data', {}).get('data', {}).get('searchDataResultDTO', {}).get('dataTableDTOList', [])
        for t in tables:
            tb = t.get('table', {})
            nm = t.get('nameMap', {})
            for k, v in tb.items():
                name = nm.get(k, k)
                vals = v or []
                val = vals[0] if vals else None
                if '最新价' in name: result['price'] = safe_float(val)
                elif '涨跌幅' in name: result['pct'] = safe_float(val)
                elif '成交额' in name: result['amount'] = safe_float(val)
                elif '成交量' in name: result['volume'] = safe_float(val)
                elif '换手率' in name: result['turnover'] = safe_float(val)
                elif '最高' in name: result['high'] = safe_float(val)
                elif '最低' in name: result['low'] = safe_float(val)
                elif '今开' in name: result['open'] = safe_float(val)
                elif '昨收' in name: result['pre_close'] = safe_float(val)
        return result
    except Exception as e:
        return {'code': code, 'error': str(e)}

def get_multi_prices(codes: list) -> dict:
    """批量查行情（逐个查）"""
    return {c: get_stock_price(c) for c in codes}

def get_market_overview() -> dict:
    """查大盘状态"""
    try:
        indices = ['上证指数', '深证成指', '创业板指', '科创50']
        result = {}
        for name in indices:
            d = mx_query(f"{name} 最新价 涨跌幅 成交额")
            tables = d.get('data', {}).get('data', {}).get('searchDataResultDTO', {}).get('dataTableDTOList', [])
            vals = {}
            for t in tables:
                tb = t.get('table', {})
                nm = t.get('nameMap', {})
                for k, v in tb.items():
                    label = nm.get(k, k)
                    arr = v or []
                    vals[label] = arr[0] if arr else None
            result[name] = vals
        return result
    except Exception as e:
        return {'error': str(e)}

def get_news(code: str, days: int = 3) -> list:
    """查个股近期新闻"""
    try:
        d = mx_news(f"{code} 公告 新闻 最近{days}天")
        items = []
        data = d.get('data', {})
        for item in data.get('datas', []):
            items.append({
                'title': item.get('title', ''),
                'date': item.get('date', ''),
                'source': item.get('source', ''),
                'summary': item.get('summary', '')[:200]
            })
        return items[:10]
    except Exception as e:
        return [{'error': str(e)}]

# ===== 交易执行层 =====

def execute_trade(action: str, code: str, qty: int = 0, use_market: bool = True,
                  price: float = None, amount: float = 0) -> dict:
    """
    执行交易
    action: 'buy' or 'sell'
    code: 股票代码
    qty: 股数（0=自动计算）
    use_market: 是否市价
    price: 限价
    amount: 金额（仅买入时，当qty=0时按金额算股数）
    """
    # 先查现价
    if use_market or qty == 0:
        info = get_stock_price(code)
        cur_price = info.get('price', 0)
        if not cur_price or cur_price == 0:
            return {'success': False, 'error': f'无法获取{code}现价'}
    else:
        cur_price = price or 0

    # 计算股数
    if qty == 0 and amount > 0 and cur_price > 0:
        qty = int(amount / cur_price / 100) * 100  # 取整手
        if qty == 0:
            return {'success': False, 'error': f'金额{amount}不够买1手（{cur_price*100}元）'}

    if qty == 0:
        return {'success': False, 'error': '未指定股数或金额'}

    # 构建交易参数
    decimal_places = 2 if code[0] in ['6', '9'] else 3
    payload = {
        'type': action,
        'stockCode': code,
        'quantity': qty,
        'useMarketPrice': use_market,
    }
    if not use_market and price:
        payload['price'] = int(round(price * (10 ** decimal_places)))

    # 执行
    result = moni_api('/mockTrading/trade', payload)
    code_r = result.get('code')
    success = code_r in ['0', 0, '200', '200']
    msg = result.get('message', '')
    order_id = result.get('data', {}).get('orderId', '')

    out = {
        'success': success,
        'action': action,
        'code': code,
        'qty': qty,
        'price': cur_price,
        'use_market': use_market,
        'message': msg,
        'order_id': order_id,
        'timestamp': ts(),
    }

    # 写入操作日志
    log_trade(out)
    return out

def log_trade(trade: dict):
    """记录交易到本地日志"""
    logs = []
    if os.path.exists(TRADE_LOG):
        try:
            with open(TRADE_LOG, 'r') as f:
                logs = json.load(f)
        except:
            logs = []
    logs.append(trade)
    with open(TRADE_LOG, 'w') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def get_trade_logs(days: int = 30) -> list:
    """读取交易日志"""
    if not os.path.exists(TRADE_LOG):
        return []
    try:
        with open(TRADE_LOG, 'r') as f:
            logs = json.load(f)
        today = date.today()
        recent = [l for l in logs if l.get('timestamp', '')[:10] == today_str()]
        return recent
    except:
        return []

# ===== 选股层 =====

def select_stocks(mode: str = 'intraday') -> dict:
    """
    获取板块热点数据（供LLM在prompt中自行选股参考）
    注意：选股逻辑本身在cron的LLM prompt中通过妙想工具实现。
    这里只提供辅助数据：今日热点板块、板块龙头等。
    """
    try:
        # 查询今日热点板块
        d = mx_query("今日热门板块 涨幅排名 前10 主力净流入")
        tables = d.get('data', {}).get('data', {}).get('searchDataResultDTO', {}).get('dataTableDTOList', [])
        result = {'mode': mode, 'hot_sectors': [], 'time': ts()}
        for t in tables:
            nm = t.get('nameMap', {})
            tb = t.get('table', {})
            sector = {}
            for k, v in tb.items():
                label = nm.get(k, k)
                arr = v or []
                sector[label] = arr
            if sector:
                result['hot_sectors'].append(sector)
        return result
    except Exception as e:
        return {'mode': mode, 'error': str(e), 'time': ts()}

# ===== 检查引擎 =====

def full_check() -> dict:
    """
    完整状态检查 — 供cron调用
    返回当前账户状态+持仓触发信号
    """
    out = {'time': ts(), 'date': today_str()}

    # 1. 资金
    out['balance'] = get_balance()

    # 2. 持仓
    positions = get_positions()
    out['positions'] = positions

    # 3. 检查触发条件
    signals = []
    for p in positions:
        # 查实时行情
        price_info = get_stock_price(p['code'])
        cur_price = price_info.get('price', p.get('cost', 0))
        cost = p.get('cost', 0)

        if cost and cost > 0:
            pct = round((cur_price - cost) / cost * 100, 2)
            p['current_price'] = cur_price
            p['pct_from_cost'] = pct
            p['real_pct'] = price_info.get('pct', 0)
            p['real_turnover'] = price_info.get('turnover', 0)
            p['real_amount'] = price_info.get('amount', 0)
            p['real_high'] = price_info.get('high', 0)
            p['real_low'] = price_info.get('low', 0)

            # 止损
            if pct <= STOP_LOSS_PCT:
                signals.append({
                    'type': 'stop_loss',
                    'severity': 'critical',
                    'code': p['code'],
                    'name': p['name'],
                    'pct': pct,
                    'qty': p['qty'],
                    'msg': f"🚨 {p['name']}({p['code']}) 亏损{pct:.1f}%，达-7%止损线，强制卖出"
                })

            # 止盈信号（+15%后出现回调，卖一半）
            if pct >= 15:
                signals.append({
                    'type': 'take_profit_half',
                    'severity': 'info',
                    'code': p['code'],
                    'name': p['name'],
                    'pct': pct,
                    'qty': p['qty'],
                    'msg': f"💰 {p['name']}({p['code']}) 盈利{pct:.1f}%，考虑卖一半锁利"
                })

            # 趋势逆转（当日跌穿5日线？需要5日线数据判断，这里简单化）
            if pct >= 5 and price_info.get('pct', 0) and price_info['pct'] < -2:
                signals.append({
                    'type': 'trend_reversal',
                    'severity': 'warning',
                    'code': p['code'],
                    'name': p['name'],
                    'pct': pct,
                    'msg': f"⚠️ {p['name']}({p['code']}) 大幅回调{price_info['pct']:.1f}%，关注趋势反转"
                })
        else:
            p['current_price'] = cur_price

    out['signals'] = signals

    # 4. 总资产回撤检查
    init_money = out['balance'].get('init_money', 1000000)
    total = out['balance'].get('total_assets', 0)
    if init_money and init_money > 0:
        drawdown = round((total - init_money) / init_money * 100, 2)
        out['drawdown'] = drawdown
        if drawdown <= DRAWDOWN_LIMIT:
            signals.append({
                'type': 'portfolio_drawdown',
                'severity': 'critical',
                'msg': f"🚨 总资产回撤{drawdown:.1f}%，超-8%红线，需减仓到30万以下"
            })

    # 5. 可用资金情况
    avail = out['balance'].get('avail_balance', 0)
    out['cash_position'] = {
        'available': avail,
        'ratio': round(avail / total * 100, 2) if total > 0 else 0,
        'can_open_new': len(positions) < POSITION_MAX and avail > 10000,
        'max_new_position': min(avail * 0.5, 400000) if avail > 10000 else 0,
    }

    out['signal_count'] = len(signals)
    return out

# ===== 大盘/外围 =====

def get_macro_check() -> dict:
    """获取大盘及外围状态"""
    out = {'time': ts()}
    out['market'] = get_market_overview()
    return out

def get_holdings_news() -> dict:
    """查所有持仓的新闻"""
    positions = get_positions()
    out = {}
    for p in positions:
        out[p['code']] = {
            'name': p['name'],
            'news': get_news(p['code'], 3)
        }
    return out

# ===== 主入口 =====

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'check'

    if action == 'check':
        result = full_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'balance':
        bal = get_balance()
        print(json.dumps(bal, ensure_ascii=False, indent=2))

    elif action == 'positions':
        pos = get_positions()
        print(json.dumps(pos, ensure_ascii=False, indent=2))

    elif action == 'xuangai':
        mode = sys.argv[2] if len(sys.argv) > 2 else 'intraday'
        result = select_stocks(mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'macro':
        result = get_macro_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'price':
        codes = sys.argv[2:]
        for c in codes:
            info = get_stock_price(c)
            print(f"{c}: {json.dumps(info, ensure_ascii=False)}")

    elif action == 'news':
        code = sys.argv[2] if len(sys.argv) > 2 else ''
        if code:
            result = get_news(code)
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'trade':
        # 从环境变量读取交易参数
        trade_action = os.environ.get('TRADE_ACTION', '')
        trade_code = os.environ.get('TRADE_CODE', '')
        trade_qty = int(os.environ.get('TRADE_QTY', '0'))
        trade_amount = float(os.environ.get('TRADE_AMOUNT', '0'))
        use_market = os.environ.get('TRADE_MARKET', 'true').lower() == 'true'
        trade_price = float(os.environ.get('TRADE_PRICE', '0')) or None

        if not trade_action or not trade_code:
            print(json.dumps({'success': False, 'error': '需要 TRADE_ACTION 和 TRADE_CODE'}))
            return

        result = execute_trade(trade_action, trade_code, trade_qty, use_market, trade_price, trade_amount)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'log':
        logs = get_trade_logs()
        print(json.dumps(logs, ensure_ascii=False, indent=2))

    elif action == 'holding-news':
        result = get_holdings_news()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print(json.dumps({'error': f'未知action: {action}', 'usage': [
            'check', 'balance', 'positions', 'xuangai [mode]',
            'macro', 'price CODE...', 'news CODE', 'trade (via env vars)',
            'log', 'holding-news'
        ]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
