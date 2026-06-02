#!/usr/bin/env python3
"""Calculate the next trading day (skip weekends)."""

import sys
from datetime import date, timedelta

def next_trading_day(from_date: date = None) -> str:
    """Return next trading day as YYYY-MM-DD."""
    if from_date is None:
        from_date = date.today()
    next_day = from_date + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=Sat, 6=Sun
        next_day += timedelta(days=1)
    return next_day.isoformat()

def trading_day_for(date_str: str) -> str:
    """Given a date, return it if it's a weekday, else next Monday."""
    d = date.fromisoformat(date_str)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(next_trading_day(date.fromisoformat(sys.argv[1])))
    else:
        print(next_trading_day())
