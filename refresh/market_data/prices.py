#!/usr/bin/env python3
"""Latest close snapshot for a single ticker, via yfinance.

One function, one file — run it standalone to troubleshoot:
    python3 prices.py STRL

Returns the last close ("price"), the prior close, the close from 5
trading days earlier ("week_close"), the % changes against both, and the
date of the last close. Mirrors snapshot.py's fetch_market conventions.
"""
import sys


def get_price_snapshot(ticker):
    """-> {"ticker", "price", "prev_close", "day_change_pct",
           "week_close", "week_change_pct", "close_date"}"""
    import yfinance as yf
    t = ticker.strip().upper()
    out = {"ticker": t, "price": None, "prev_close": None,
           "day_change_pct": None, "week_close": None,
           "week_change_pct": None, "close_date": None}
    dl = yf.download(t, period="10d", progress=False, auto_adjust=False)
    if dl is None or len(dl) == 0:
        return out
    closes = dl["Close"]
    if hasattr(closes, "columns"):
        s = closes[t].dropna()
    else:
        s = closes.dropna()
    if len(s) >= 1:
        out["price"] = round(float(s.iloc[-1]), 2)
        out["close_date"] = str(s.index[-1].date())
    if len(s) >= 2:
        out["prev_close"] = round(float(s.iloc[-2]), 2)
    if len(s) >= 6:
        out["week_close"] = round(float(s.iloc[-6]), 2)
    if out["price"] is not None and out["prev_close"]:
        out["day_change_pct"] = round(
            (out["price"] / out["prev_close"] - 1) * 100, 2)
    if out["price"] is not None and out["week_close"]:
        out["week_change_pct"] = round(
            (out["price"] / out["week_close"] - 1) * 100, 2)
    return out


if __name__ == "__main__":
    for tk in sys.argv[1:]:
        print(get_price_snapshot(tk))
