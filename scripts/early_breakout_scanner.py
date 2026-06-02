#!/usr/bin/env python3
"""
早期突破扫描器 — 商络电子模式三阶段检测

阶段1: 首次异动 — 单日+8%以上 + 量比>1.5 + 近60日相对低位
阶段2: 回踩确认 — 缩量不破异动日开盘价 + 振幅收敛
阶段3: 弹簧触发 — 量缩至异动日40%以下 + 反转阳线 + 站上5日线

用法:
  python3 early_breakout_scanner.py --codes 300975,600460,...  [扫描指定代码]
  python3 early_breakout_scanner.py --sector 半导体              [扫描板块成分股]
  python3 early_breakout_scanner.py --watchlist                  [扫描默认观察池]

输出: JSON — {stage1: [...], stage2: [...], stage3: [...], summary: "..."}
"""

import urllib.request
import json
import sys
import argparse
import time
from datetime import datetime

# ── 默认观察池（活跃板块龙头+活跃标的，定期更新） ──
DEFAULT_WATCHLIST = {
    "芯片/半导体": ["002371", "688012", "600584", "300394", "600460", "002617", "300604", 
                    "688981", "300655", "002409", "300576", "603501", "300236", "688126",
                    "002156", "600703", "300346", "688536", "688072", "688037"],
    "机器人/自动化": ["600563", "300221", "002782", "300124", "002527", "688017", "300660",
                     "002444", "300024", "300161"],
    "储能/新能源": ["002733", "300750", "300274", "002459", "688063", "300438", "600580"],
    "PCB/电子元件": ["002138", "002913", "300657", "300975", "600183", "002916", "002384"],
    "AI/CPO": ["300308", "300502", "300394", "688313", "002281", "688205"],
    "AIDC电源/超级电容": ["600673", "002484", "002028", "688676", "601126", "002851", "002518"],
}

# ── K线获取 ──
def get_kline(code, days=30):
    """获取个股日K线，返回 [{date, open, close, high, low, volume}, ...]"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    
    klines = data.get("data", {}).get(f"{prefix}{code}", {}).get("day", [])
    if not klines:
        klines = data.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", [])
    if not klines or len(klines) < 20:
        return None
    
    result = []
    for k in klines[-days:]:
        result.append({
            "date": k[0],
            "open": float(k[1]),
            "close": float(k[2]),
            "high": float(k[3]),
            "low": float(k[4]),
            "volume": float(k[5]) if len(k) > 5 else 0,
        })
    return result


# ── 三阶段检测 ──
def detect_stage1(klines):
    """
    阶段1: 首次异动检测
    - 单日涨幅 ≥ 8%
    - 当日量 > 20日均量的1.5倍
    - 价格处于60日相对低位（40%分位以下）
    返回: [{"date": "2026-05-06", "gain": 11.88, "vol_ratio": 1.6, "price": 22.89}, ...]
    """
    if len(klines) < 20:
        return []
    
    results = []
    # 计算20日均量
    vol_20 = sum(k["volume"] for k in klines[-25:-5]) / 20 if len(klines) >= 25 else \
             sum(k["volume"] for k in klines[:-5]) / max(1, len(klines) - 5)
    
    # 60日相对位置
    if len(klines) >= 30:
        high_60 = max(k["high"] for k in klines[-30:])
        low_60 = min(k["low"] for k in klines[-30:])
    else:
        high_60 = max(k["high"] for k in klines)
        low_60 = min(k["low"] for k in klines)
    
    for i in range(5, len(klines)):  # 从第5根开始(跳过初期)
        k = klines[i]
        prev = klines[i - 1]
        gain = (k["close"] - prev["close"]) / prev["close"] * 100
        
        if gain >= 8.0:
            vol_ratio = k["volume"] / vol_20 if vol_20 > 0 else 0
            position = (k["close"] - low_60) / (high_60 - low_60) if high_60 != low_60 else 0.5
            
            if vol_ratio >= 1.5 and position <= 0.6:  # 相对低位或中位
                results.append({
                    "date": k["date"],
                    "gain": round(gain, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "price": k["close"],
                    "open_price": k["open"],
                    "position_percentile": round(position * 100, 1),
                })
    
    return results


def detect_stage2(klines, anomaly):
    """
    阶段2: 回踩确认
    - 异动日之后，价格回踩但不破异动日开盘价
    - 量能萎缩（日均量 < 异动日量的70%）
    - 振幅收敛（最近3日平均振幅 < 5%）
    返回: {"confirmed": bool, "lowest": float, "vol_contraction": float, "days_since": int}
    """
    anomaly_idx = None
    for i, k in enumerate(klines):
        if k["date"] == anomaly["date"]:
            anomaly_idx = i
            break
    
    if anomaly_idx is None or anomaly_idx >= len(klines) - 2:
        return {"confirmed": False, "reason": "异动日距今不足2个交易日"}
    
    # 异动后数据
    post = klines[anomaly_idx + 1:]
    if len(post) < 2:
        return {"confirmed": False, "reason": "异动后数据不足"}
    
    anomaly_open = anomaly["open_price"]
    anomaly_vol = anomaly.get("anomaly_vol", klines[anomaly_idx]["volume"])
    
    # 检查是否破开盘价
    post_lows = [k["low"] for k in post]
    lowest = min(post_lows)
    if lowest < anomaly_open * 0.97:  # 跌穿异动日开盘3%以上 = 失败
        return {"confirmed": False, "reason": f"跌破异动开盘{anomaly_open}，最低{lowest:.2f}"}
    
    # 量能检查
    post_vols = [k["volume"] for k in post]
    avg_post_vol = sum(post_vols) / len(post_vols)
    vol_contraction = avg_post_vol / anomaly_vol if anomaly_vol > 0 else 1
    
    if vol_contraction > 0.9:
        return {"confirmed": False, "reason": f"量能未收缩(ratio={vol_contraction:.2f})"}
    
    # 振幅收敛
    recent_3 = post[-3:] if len(post) >= 3 else post
    amplitudes = [(k["high"] - k["low"]) / k["close"] * 100 for k in recent_3]
    avg_amplitude = sum(amplitudes) / len(amplitudes)
    
    return {
        "confirmed": True,
        "lowest": lowest,
        "lowest_vs_open": round((lowest - anomaly_open) / anomaly_open * 100, 2),
        "vol_contraction": round(vol_contraction, 2),
        "avg_amplitude": round(avg_amplitude, 2),
        "days_since": len(post),
    }


def detect_stage3(klines, anomaly):
    """
    阶段3: 弹簧触发
    - 最近1-2日量缩至异动日量的40%以下
    - 出现反转阳线（收盘>开盘 且 收盘>前日收盘）
    - 站上5日线
    返回: {"triggered": bool, "signal_date": str, "score": int}
    """
    anomaly_idx = None
    for i, k in enumerate(klines):
        if k["date"] == anomaly["date"]:
            anomaly_idx = i
            break
    
    if anomaly_idx is None:
        return {"triggered": False, "reason": "异动日未找到"}
    
    anomaly_vol = klines[anomaly_idx]["volume"]
    recent = klines[anomaly_idx:]
    
    if len(recent) < 5:
        return {"triggered": False, "reason": "异动后数据不足"}
    
    # 计算5日线
    ma5 = sum(k["close"] for k in klines[-5:]) / 5
    
    # 最近2天
    last = recent[-1]
    prev = recent[-2] if len(recent) >= 2 else last
    
    # 条件1: 量缩至异动日的60%以下
    vol_ratio = last["volume"] / anomaly_vol
    cond_vol = vol_ratio <= 0.65
    
    # 条件2: 反转阳线（收盘>开盘 且 收盘>前日收盘）或 前日洗盘（-5%以上）后今日反弹
    cond_reversal = (last["close"] > last["open"] and last["close"] > prev["close"]) or \
                    ((prev["close"] - klines[anomaly_idx-1]["close"]) / klines[anomaly_idx-1]["close"] * 100 <= -5 and last["close"] > prev["close"])
    
    # 条件3: 站上5日线 或 接近5日线（差距<2%）
    cond_ma5 = last["close"] > ma5 or (ma5 - last["close"]) / ma5 < 0.02
    
    score = sum([cond_vol, cond_reversal, cond_ma5])
    
    return {
        "triggered": score >= 2,
        "score": score,
        "vol_ratio": round(vol_ratio, 2),
        "reversal": cond_reversal,
        "above_ma5": cond_ma5,
        "signal_date": last["date"],
        "price": last["close"],
        "ma5": round(ma5, 2),
    }


# ── 个股完整扫描 ──
def scan_stock(code, name=""):
    """对单只股票执行完整三阶段扫描"""
    klines = get_kline(code, days=30)
    if not klines:
        return {"code": code, "name": name, "error": "K线获取失败"}
    
    today_close = klines[-1]["close"]
    prev_close = klines[-2]["close"]
    day_chg = round((today_close - prev_close) / prev_close * 100, 2)
    
    # 计算均线
    ma5 = round(sum(k["close"] for k in klines[-5:]) / 5, 2)
    ma10 = round(sum(k["close"] for k in klines[-10:]) / 10, 2) if len(klines) >= 10 else None
    ma20 = round(sum(k["close"] for k in klines[-20:]) / 20, 2) if len(klines) >= 20 else None
    
    # 计算20日均量
    vol_20 = sum(k["volume"] for k in klines[-25:-5]) / 20 if len(klines) >= 25 else \
             sum(k["volume"] for k in klines[:-5]) / max(1, len(klines) - 5)
    today_vol_ratio = round(klines[-1]["volume"] / vol_20, 2) if vol_20 > 0 else 0
    
    # 三阶段检测
    anomalies = detect_stage1(klines)
    
    result = {
        "code": code,
        "name": name,
        "price": today_close,
        "day_chg": day_chg,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "vol_ratio_vs_20d": today_vol_ratio,
        "stage": None,
        "anomalies": [],
        "signals": [],
    }
    
    for anomaly in anomalies:
        # 补全anomaly_vol
        for k in klines:
            if k["date"] == anomaly["date"]:
                anomaly["anomaly_vol"] = k["volume"]
                break
        
        s2 = detect_stage2(klines, anomaly)
        s3 = detect_stage3(klines, anomaly)
        
        signal = {
            "anomaly_date": anomaly["date"],
            "anomaly_gain": anomaly["gain"],
            "anomaly_price": anomaly["price"],
            "stage2": s2,
            "stage3": s3,
        }
        
        if s3["triggered"]:
            signal["stage"] = "STAGE3"
            signal["alert"] = f"🔥 弹簧触发 — {anomaly['date']}异动+{anomaly['gain']}%，现已缩量回踩确认，站上MA5={ma5}"
        elif s2["confirmed"]:
            signal["stage"] = "STAGE2"
            signal["alert"] = f"🟡 回踩确认 — {anomaly['date']}异动后缩量不破位，等待弹簧"
        else:
            signal["stage"] = "STAGE1"
            signal["alert"] = f"⚪ 首次异动 — {anomaly['date']}+{anomaly['gain']}%，未确认"
        
        result["signals"].append(signal)
    
    # 最高阶段
    stages = [s["stage"] for s in result["signals"]]
    if "STAGE3" in stages:
        result["stage"] = "STAGE3"
    elif "STAGE2" in stages:
        result["stage"] = "STAGE2"
    elif "STAGE1" in stages:
        result["stage"] = "STAGE1"
    
    return result


# ── 批量扫描 ──
def scan_batch(codes_dict, verbose=False):
    """批量扫描，codes_dict = {code: name}"""
    results = []
    for code, name in codes_dict.items():
        if verbose:
            print(f"  扫描 {code} {name}...", file=sys.stderr)
        r = scan_stock(code, name)
        results.append(r)
        time.sleep(0.05)  # 避免请求过快
    
    # 按阶段+信号强度排序
    stage_order = {"STAGE3": 0, "STAGE2": 1, "STAGE1": 2}
    results.sort(key=lambda r: (
        stage_order.get(r.get("stage"), 99),
        -(max((s.get("stage3", {}).get("score", 0) for s in r["signals"]), default=0)),
    ))
    
    return results


def format_output(results):
    """格式化输出"""
    stage3 = [r for r in results if r["stage"] == "STAGE3"]
    stage2 = [r for r in results if r["stage"] == "STAGE2"]
    stage1 = [r for r in results if r["stage"] == "STAGE1"]
    
    lines = []
    lines.append(f"## 🔭 早期突破扫描 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"扫描标的: {len(results)} | 🔥弹簧: {len(stage3)} | 🟡回踩: {len(stage2)} | ⚪异动: {len(stage1)}")
    lines.append("")
    
    if stage3:
        lines.append("### 🔥 阶段3 — 弹簧触发（建仓窗口）")
        lines.append("")
        for r in stage3:
            for s in r["signals"]:
                if s["stage"] == "STAGE3":
                    a = s
                    lines.append(f"**{r['name']}({r['code']})** 现价{r['price']} | 日涨跌{r['day_chg']}% | MA5={r['ma5']}")
                    lines.append(f"> 异动日: {a['anomaly_date']} +{a['anomaly_gain']}% @{a['anomaly_price']}")
                    s3 = a.get("stage3", {})
                    s2 = a.get("stage2", {})
                    lines.append(f"> 弹簧信号: 量缩至{s2.get('vol_contraction','?')}x | 量比异动日{s3.get('vol_ratio','?')}x | 评分{s3.get('score','?')}/3")
                    lines.append("")
    
    if stage2:
        lines.append("### 🟡 阶段2 — 回踩确认（观察升级）")
        lines.append("")
        for r in stage2:
            for s in r["signals"]:
                if s["stage"] == "STAGE2":
                    a = s
                    lines.append(f"**{r['name']}({r['code']})** 现价{r['price']} | MA5={r['ma5']}")
                    lines.append(f"> 异动日: {a['anomaly_date']} +{a['anomaly_gain']}% | 回踩最低{a['stage2']['lowest']} | 缩量{a['stage2']['vol_contraction']}x")
                    lines.append("")
    
    if stage1:
        lines.append("### ⚪ 阶段1 — 首次异动（加入观察）")
        lines.append("")
        for r in stage1[:8]:  # 最多显示8个
            for s in r["signals"][:1]:
                a = s
                lines.append(f"**{r['name']}({r['code']})** 现价{r['price']} | 异动{a['anomaly_date']}+{a['anomaly_gain']}%")
                lines.append(f"> 60日分位: {a['anomaly']['position_percentile'] if 'position_percentile' in a.get('anomaly',{}) else '?'}% | 量比: {a['anomaly']['vol_ratio'] if 'vol_ratio' in a.get('anomaly',{}) else '?'}x")
        lines.append("")
    
    if not any([stage3, stage2, stage1]):
        lines.append("⚠️ 当前无符合条件的异动标的。")
    
    return "\n".join(lines)


# ── CLI入口 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="早期突破扫描器")
    parser.add_argument("--codes", type=str, help="股票代码，逗号分隔")
    parser.add_argument("--sector", type=str, help="板块名称")
    parser.add_argument("--watchlist", action="store_true", help="扫描默认观察池")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()
    
    codes_dict = {}
    
    if args.codes:
        for c in args.codes.split(","):
            codes_dict[c.strip()] = ""
    elif args.sector:
        sector = args.sector
        for sec_name, codes in DEFAULT_WATCHLIST.items():
            if sector in sec_name:
                for c in codes:
                    codes_dict[c] = ""
    elif args.watchlist or not any([args.codes, args.sector]):
        for sec_name, codes in DEFAULT_WATCHLIST.items():
            for c in codes:
                if c not in codes_dict:
                    codes_dict[c] = ""
    
    if not codes_dict:
        print("{}")
        sys.exit(0)
    
    results = scan_batch(codes_dict, verbose=True)
    
    if args.json:
        print(json.dumps({
            "scan_time": datetime.now().isoformat(),
            "total": len(results),
            "stage3_count": len([r for r in results if r["stage"] == "STAGE3"]),
            "stage2_count": len([r for r in results if r["stage"] == "STAGE2"]),
            "stage1_count": len([r for r in results if r["stage"] == "STAGE1"]),
            "stage3": [r for r in results if r["stage"] == "STAGE3"],
            "stage2": [r for r in results if r["stage"] == "STAGE2"],
        }, ensure_ascii=False, indent=2))
    else:
        print(format_output(results))
