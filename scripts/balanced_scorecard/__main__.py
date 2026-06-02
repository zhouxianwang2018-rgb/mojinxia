"""平衡计分卡 CLI 入口。"""
import argparse
import sys
import json
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from balanced_scorecard.engine import run
from balanced_scorecard.presentation.json_writer import save_scorecard
from balanced_scorecard.presentation.markdown_report import format_markdown


def main():
    parser = argparse.ArgumentParser(
        description="摸金虾 · 交易代理平衡计分卡",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -m balanced_scorecard\n  python -m balanced_scorecard --format markdown\n  python -m balanced_scorecard --last 7",
    )
    parser.add_argument("date", nargs="?", default="today",
                       help="日期 (today/last/YYYY-MM-DD)")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "both"],
                       default="both", help="输出格式")
    parser.add_argument("--last", "-n", type=int, metavar="N",
                       help="最近N天")
    parser.add_argument("--window", "-w", type=int, default=30,
                       help="计算窗口天数 (default: 30)")
    parser.add_argument("--trend", "-t", type=int, metavar="N",
                       help="N日趋势查询")

    args = parser.parse_args()

    if args.trend:
        for i in range(args.trend - 1, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            try:
                result = run(d, window_days=args.window)
                print(f"{d}: {result.total:.1f} ({result.grade})")
            except Exception as e:
                print(f"{d}: ERROR — {e}")
        return

    if args.last:
        from balanced_scorecard.collectors.strategy_reader import load_strategy
        printed = 0
        for i in range(args.last - 1, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            # 跳过无策略文件的非交易日
            if not load_strategy(d):
                continue
            try:
                result = run(d, window_days=args.window)
                save_scorecard(result)
                if args.format in ("markdown", "both"):
                    print(format_markdown(result))
                    printed += 1
                    # 检查下一日是否有数据，有才加分隔线
                    next_exists = any(
                        load_strategy((date.today() - timedelta(days=j)).isoformat())
                        for j in range(i - 1, -1, -1)
                    )
                    if next_exists:
                        print("\n---\n")
                elif args.format == "json":
                    print(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"{d}: ERROR — {e}")
        return

    # Single date
    result = run(args.date, window_days=args.window)
    save_scorecard(result)

    if args.format in ("json", "both"):
        print(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2))

    if args.format in ("markdown", "both"):
        if args.format == "both":
            print("\n---\n")
        print(format_markdown(result))


def _result_to_dict(result) -> dict:
    return {
        "date": result.date,
        "total": result.total,
        "grade": result.grade,
        "dimensions": {
            name: {
                "label": dim.label,
                "weight": dim.weight,
                "score": dim.score,
                "sub_scores": [
                    {"name": ss.name, "score": ss.score, "weight": ss.weight,
                     "detail": ss.detail, "raw_value": ss.raw_value}
                    for ss in dim.sub_scores
                ],
                "flags": dim.flags,
            }
            for name, dim in result.dimensions.items()
        },
        "trend": {
            "vs_yesterday": result.trend.vs_yesterday,
            "vs_7d_ago": result.trend.vs_7d_ago,
            "vs_30d_ago": result.trend.vs_30d_ago,
        },
        "anomalies": result.anomalies,
        "generated_at": result.generated_at,
    }


if __name__ == "__main__":
    main()
