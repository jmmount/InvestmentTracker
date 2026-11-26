"""Company-name lookup — one function, one file (see __init__.py).

    get_company_name(ticker) -> {"ticker": ..., "name": ... or None}

Data source: yfinance (same as graham.py / prices.py). Prefers the
long company name, falls back to the short name. Funds get their fund
name the same way. Returns None when Yahoo has no name for the ticker;
callers fall back to displaying the bare ticker.

Standalone check:  python3 names.py BAC
"""
import sys

import yfinance as yf


def get_company_name(ticker):
    info = yf.Ticker(ticker).info or {}
    name = info.get("longName") or info.get("shortName")
    return {"ticker": ticker, "name": name}


if __name__ == "__main__":
    print(get_company_name(sys.argv[1] if len(sys.argv) > 1 else "BAC"))
