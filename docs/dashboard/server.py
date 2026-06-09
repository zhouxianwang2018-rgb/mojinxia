import json, os, re, glob
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse

app = FastAPI(title="摸金虾投顾系统", version="1.1")
BASE = os.path.expanduser("~/.hermes/cron/state/moni/")
OUTPUT = os.path.expanduser("~/.hermes/cron/output/")

def load_strategies():
    d = os.path.join(BASE, "strategies")
    files = sorted([f for f in os.listdir(d) if f.endswith(".json")])
    data = []
    for f in files:
        with open(os.path.join(d, f)) as fp:
            j = json.load(fp)
        r = j.get("risk_state", {})
        data.append({
            "day": j.get("trading_day", f[:10]),
            "status": j.get("status"),
            "nav": j.get("nav") or 0,
            "profit_loss": j.get("profit_loss") or 0,
            "level": r.get("level", ""),
            "ban": r.get("new_position_ban", False),
            "dd": r.get("drawdown_from_peak", 0) or 0,
            "consecutive": r.get("consecutive_loss_days", 0) or 0,
            "equity_before": j.get("equity_before") or 0,
            "equity_after": j.get("equity_after") or 0,
            "thesis": (j.get("current_strategy", {}).get("core_thesis", "") or "")[:120],
        })
    return data

@app.get("/api/strategies")
def api_strategies():
    return load_strategies()

@app.get("/api/summary")
def api_summary():
    data = load_strategies()
    if not data: return {}
    cur = data[-1]
    navs = [d["nav"] for d in data]
    profits = [d["profit_loss"] for d in data]
    peak = max(navs) if navs else 1
    month_start = data[0]["nav"] if len(data) > 1 else 1
    month_target = month_start * 1.15
    return {
        "current_nav": cur["nav"],
        "current_level": cur["level"],
        "current_ban": cur["ban"],
        "current_dd": round((cur["nav"]/peak - 1)*100, 2),
        "month_return": round((cur["nav"]/month_start - 1)*100, 2),
        "month_target": round(month_target, 4),
        "target_gap": round((cur["nav"]/month_target - 1)*100, 2),
        "max_dd": round((min(navs)/peak - 1)*100, 2) if navs else 0,
        "cum_profit": round(sum(profits), 2),
        "trading_days": len(data),
        "last_day": cur["day"],
        "total_trades": sum(1 for p in profits if p != 0),
    }

@app.get("/api/positions")
def api_positions():
    d = os.path.join(BASE, "strategies")
    files = sorted([f for f in os.listdir(d) if f.endswith(".json")], reverse=True)
    seen = set()
    positions = []
    
    # Priority 1: close_snapshot.positions from the LATEST file that has them
    for f in files:
        with open(os.path.join(d, f)) as fp:
            j = json.load(fp)
        close_pos = j.get("close_snapshot", {}).get("positions", {})
        if close_pos:
            for code, info in close_pos.items():
                qty = info.get("qty", 0) or 0
                if qty > 0 and code not in seen:
                    seen.add(code)
                    positions.append({
                        "day": j.get("trading_day", f[:10]),
                        "code": code,
                        "name": info.get("name", code),
                        "cost": info.get("cost", 0),
                        "price": info.get("price", 0),
                        "pnl_pct": info.get("pnl_pct", 0),
                        "shares": qty,
                        "source": "close_snapshot",
                    })
            if positions:  # Found the latest close data
                break
    
    # Priority 2: if no close_snapshot positions, fall back to per_stock from latest file
    if not positions:
        for f in files:
            with open(os.path.join(d, f)) as fp:
                j = json.load(fp)
            ps = j.get("current_strategy", {}).get("per_stock", {})
            for code, info in ps.items():
                if code in seen:
                    continue
                shares = info.get("max_hold", info.get("position", 0)) or 0
                if shares > 0:
                    seen.add(code)
                    positions.append({
                        "day": j.get("trading_day", f[:10]),
                        "code": code,
                        "name": info.get("name", code),
                        "cost": info.get("cost", 0),
                        "stop": info.get("stop_loss", 0),
                        "take": info.get("take_profit", 0),
                        "shares": shares,
                        "source": "per_stock",
                    })
            if positions:
                break
    
    return positions

@app.get("/api/report/premarket")
def api_premarket_report():
    """Return latest pre-market report as markdown."""
    report_path = "/tmp/premarket_report.md"
    if not os.path.exists(report_path):
        return {"found": False, "content": ""}
    with open(report_path) as f:
        content = f.read()
    # Extract the actual report (skip cron metadata if present)
    idx = content.find("## 一、")
    if idx >= 0:
        # Include the title just before "一、"
        start = max(0, content.rfind("# ", 0, idx))
        if start < 0:
            start = idx
        content = content[start:]
    mtime = os.path.getmtime(report_path)
    return {
        "found": True,
        "content": content,
        "updated": datetime.fromtimestamp(mtime).isoformat(),
    }

@app.get("/api/report/closing")
def api_closing_report():
    """Return latest closing review report from 收盘复盘 cron."""
    # Find outputs from the 收盘复盘 cron (job 38f4374a2705)
    closing_dir = os.path.join(OUTPUT, "38f4374a2705")
    if not os.path.isdir(closing_dir):
        return {"found": False, "content": "", "updated": ""}
    
    files = sorted(glob.glob(os.path.join(closing_dir, "*.md")), reverse=True)
    if not files:
        return {"found": False, "content": "", "updated": ""}
    
    with open(files[0]) as f:
        content = f.read()
    
    # Extract agent response: find "## Response" marker
    resp_idx = content.rfind("## Response")
    if resp_idx >= 0:
        content = content[resp_idx + len("## Response"):].strip()
    
    return {
        "found": True,
        "content": content[:20000],
        "updated": datetime.fromtimestamp(os.path.getmtime(files[0])).isoformat(),
        "source": os.path.basename(files[0]),
    }


@app.get("/api/recs")
def api_recs():
    tf = os.path.join(BASE, "engine_tracker.json")
    if not os.path.exists(tf): return []
    with open(tf) as f:
        tracker = json.load(f)
    recs = tracker.get("recommendations", [])
    if isinstance(recs, dict):
        # Some trackers store recs indexed by date/code
        recs = list(recs.values())
    return recs if isinstance(recs, list) else []

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat(), "data_dir": BASE}

# Mount static files last (FastAPI routes take priority)
app.mount("/", StaticFiles(directory=os.path.expanduser("~/.hermes/web/static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
