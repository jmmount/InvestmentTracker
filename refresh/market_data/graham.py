#!/usr/bin/env python3
"""Graham number for a single ticker, via yfinance.

One function, one file — run it standalone to troubleshoot:
    python3 graham.py BAC
    python3 graham.py BAC GOOGL NVO FBNDX

Graham number = sqrt(22.5 * trailing EPS * book value per share).
Returns None (with a note) for mutual funds and when EPS/BVPS are
unavailable or non-positive. Mirrors snapshot.py's logic exactly.
"""
import math
import sys


def get_graham_number(ticker):
    """-> {"ticker", "graham", "graham_note"}"""
    import yfinance as yf
    t = ticker.strip().upper()
    try:
        info = yf.Ticker(t).info
        # Fund detection comes from the data (yfinance quoteType), never a
        # hardcoded ticker list: Graham does not apply to mutual funds.
        if info.get("quoteType") == "MUTUALFUND":
            return {"ticker": t, "graham": None,
                    "graham_note": "mutual fund — Graham N/A"}
        eps = info.get("trailingEps")
        bvps = info.get("bookValue")
        if eps and bvps and eps > 0 and bvps > 0:
            return {"ticker": t,
                    "graham": round(math.sqrt(22.5 * eps * bvps), 2),
                    "graham_note": ""}
        return {"ticker": t, "graham": None,
                "graham_note": "EPS/BVPS unavailable or non-positive"}
    except Exception as e:
        return {"ticker": t, "graham": None,
                "graham_note": f"lookup failed: {e}"[:80]}


if __name__ == "__main__":
    for tk in sys.argv[1:]:
        r = get_graham_number(tk)
        print(f"{r['ticker']}: graham={r['graham']} {r['graham_note']}")
