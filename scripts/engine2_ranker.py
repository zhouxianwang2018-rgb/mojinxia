#!/usr/bin/env python3
"""
引擎二：条件选股 + 板块集中度 + 交叉排名。
被 14:25 CRON 调用，读策略文件中的引擎一结果，执行引擎二选股，
计算交叉排名，写回策略文件。

用法:
    python3 engine2_ranker.py [--strategy-file <path>]

默认读 ~/.hermes/cron/state/moni/strategies/{today}.json
"""

import sys, json, os, re, time, argparse
from datetime import datetime
from collections import Counter

sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from moni_engine import mx_xuangai, mx_query

STRATEGY_DIR = os.path.expanduser('~/.hermes/cron/state/moni/strategies')

# ── Step 1: 条件选股 ──

def run_xuangai(query: str) -> list[tuple]:
    """运行 mx_xuangai，返回 [(code, name, price, chg, turnover, mcap), ...]"""
    result = mx_xuangai(query)
    partial = result['data']['data'].get('partialResults', '')
    pattern = r'\|\s*(\d+)\s*\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
    stocks = []
    for m in re.finditer(pattern, partial):
        seq, code, name, price, chg, ma, turnover, mcap = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6), m.group(7), m.group(8)
        stocks.append((code, name.strip(), price.strip(), chg.strip(), turnover.strip(), mcap.strip()))
    return stocks


# ── Step 2: 查询行业 ──

def get_sector(code: str, name: str) -> str:
    """查询申万一级行业"""
    try:
        d = mx_query(f"{name} {code} 申万行业")
        tables = d.get('data',{}).get('data',{}).get('searchDataResultDTO',{}).get('dataTableDTOList', [])
        for t in tables:
            for k, v in t['table'].items():
                if '申万' in t['nameMap'].get(k, ''):
                    sw = v[0] if isinstance(v, list) and v else str(v)
                    return sw.split('-')[0] if '-' in sw else sw
    except:
        pass
    return '未知'


# ── Step 3: 交叉排名 ──

def compute_ranking(engine1_stocks: list[dict], engine2_stocks: list[tuple],
                    market_context: dict | None = None) -> list[dict]:
    """综合引擎一+引擎二+主线，输出排序后的候选池"""
    
    e1_codes = {s['code']: s for s in engine1_stocks}
    e2_codes = {s[0]: s for s in engine2_stocks}
    main_themes = market_context.get('main_themes', []) if market_context else []
    
    ranked = []
    
    # 先处理双命中
    all_codes = set(e1_codes.keys()) | set(e2_codes.keys())
    for code in all_codes:
        e1 = e1_codes.get(code)
        e2 = e2_codes.get(code)
        
        priority = 0
        reasons = []
        
        # 引擎一权重
        if e1 and e1.get('score', 0) >= 3:
            priority += 3
            reasons.append('引擎一满分STAGE3')
        elif e1 and e1.get('score', 0) >= 2:
            priority += 2
            reasons.append('引擎一STAGE3')
        elif e1:
            priority += 1
            reasons.append('引擎一STAGE2')
        
        # 引擎二权重
        if e2:
            try:
                gain = float(e2[3].replace('%','').replace('+',''))
            except:
                gain = 0
            if gain >= 10:
                priority += 2
                reasons.append(f'引擎二Top+{gain:.0f}%')
            elif gain >= 5:
                priority += 1
                reasons.append('引擎二Top15')
        
        # 主线匹配
        if market_context:
            sector = get_sector(code, e1.get('name','') if e1 else (e2[1] if e2 else ''))
            for theme in main_themes:
                if theme in sector or theme in (e1.get('name','') if e1 else (e2[1] if e2 else '')):
                    priority += 2
                    reasons.append(f'主线匹配({theme})')
                    break
        
        name = e1.get('name', '') if e1 else (e2[1] if e2 else '')
        ranked.append({
            'code': code,
            'name': name,
            'priority': priority,
            'reason': '+'.join(reasons) if reasons else '单引擎命中',
            'e1_score': e1.get('score', 0) if e1 else 0,
            'e2_gain': e2[3] if e2 else 'N/A',
        })
    
    ranked.sort(key=lambda x: -x['priority'])
    return ranked


# ── 主入口 ──

def main(strategy_file: str | None = None):
    today = datetime.now().strftime('%Y-%m-%d')
    if not strategy_file:
        strategy_file = os.path.join(STRATEGY_DIR, f'{today}.json')
    
    print(f"🔍 引擎二启动 — {today}")
    
    # 加载策略文件（读引擎一结果 + market_context）
    with open(strategy_file) as f:
        strategy = json.load(f)
    
    e1_pool = strategy.get('current_strategy', {}).get('candidate_pool', {}).get('engine1', {})
    e1_stage3 = e1_pool.get('stage3', [])
    e1_stage2 = e1_pool.get('stage2', [])
    e1_all = e1_stage3 + e1_stage2
    market_ctx = strategy.get('market_context')
    
    print(f"  引擎一: {len(e1_stage3)} STAGE3 + {len(e1_stage2)} STAGE2")
    if market_ctx:
        print(f"  主线: {market_ctx.get('main_themes', [])}")
    else:
        print(f"  ⚠️ 无 market_context（盘前分析尚未写入）")
    
    # Step 1: 条件选股
    print(f"\n  Step 1: 条件选股...")
    stocks = run_xuangai("均线多头排列 换手率大于5% 总市值大于50亿 今日涨跌幅排序")
    print(f"    命中: {len(stocks)} 只")
    
    # Step 2: 板块集中度
    print(f"\n  Step 2: 查询行业...")
    sectors = {}
    for code, name, price, chg, turnover, mcap in stocks[:15]:
        sw = get_sector(code, name)
        sectors[code] = sw
        time.sleep(0.1)
    
    sector_counts = Counter(sectors.values())
    print(f"    分布: {dict(sector_counts)}")
    
    # Step 3: 交叉排名
    print(f"\n  Step 3: 交叉排名...")
    ranked = compute_ranking(e1_all, stocks[:15], market_ctx)
    
    top = ranked[:8]
    for i, r in enumerate(top):
        print(f"    P{i+1}: {r['code']} {r['name']:<8} 权重{r['priority']} ({r['reason']})")
    
    # Step 4: 写回策略文件
    e2_data = []
    for code, name, price, chg, turnover, mcap in stocks[:15]:
        e2_data.append({
            'code': code, 'name': name, 'price': price,
            'chg': chg, 'turnover': turnover, 'mcap': mcap,
            'sector': sectors.get(code, '未知')
        })
    
    # 交叉验证列表
    e1_codes = {s['code'] for s in e1_all}
    e2_codes = {s[0] for s in stocks[:15]}
    cross = e1_codes & e2_codes
    
    strategy['current_strategy']['candidate_pool']['engine2'] = {
        'written_by': '引擎二',
        'written_at': datetime.now().isoformat(),
        'query': '均线多头排列 换手率>5% 市值>50亿',
        'total_hits': len(stocks),
        'top15': e2_data,
        'sector_distribution': dict(sector_counts),
        'cross_validated': [{'code': c} for c in cross],
        'ranked': ranked[:10],
    }
    
    with open(strategy_file, 'w') as f:
        json.dump(strategy, f, indent=2, ensure_ascii=False)
    
    print(f"\n  ✅ 已写入策略文件")
    print(f"\n  📊 最终候选池 Top 5:")
    for i, r in enumerate(ranked[:5]):
        m = '🎯' if r['priority'] >= 5 else ('🔥' if r['priority'] >= 3 else '⚡')
        print(f"    {m} {r['code']} {r['name']:<8} 权重{r['priority']} — {r['reason']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='引擎二：条件选股+排名')
    parser.add_argument('--strategy-file', type=str, help='策略文件路径')
    args = parser.parse_args()
    main(args.strategy_file)
