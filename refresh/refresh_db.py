#!/usr/bin/env python3
"""Twice-daily portfolio refresh — no sheet.

Replaces snapshot.py + populate_market_data.py + update_app_data.py for
the Investment Tracker now that investments.db is the system of record.

  - Lots come from investments.db (never the sheet, never touched here).
  - Prices, Graham numbers and company names come from yfinance via the
    market_data package (prices / graham / names — same functions that
    used to populate the workbook's MarketData tab).
  - Writes market_data, portfolio_totals and portfolio_snapshots for the
    prices' actual trading date, plus latest.json, the dated snapshot
    JSON and the briefing charts (same outputs snapshot.py produced).

Cost basis (Jason, 2026-11-12): cash lots only; reinvested-dividend
lots add shares and value, never cost. The seed lots sum to $4,956.17
at raw precision while Jason's settled cash cost is $4,956.29
(the sheet's CurrentValue pivot; the 12c is display rounding on those
lots) — COST_ADJUSTMENT carries that gap so headline totals keep
matching his number. New lots add at face value; the adjustment is
frozen, stored in sync_meta so the app backend reads the same value.

    python3 refresh_db.py [--db PATH] [--no-charts]
"""
import json
import math
import os
import sqlite3
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

# This file lives in refresh/ next to market_data/ and charts.py; add its
# own directory to sys.path so those imports resolve wherever the refresh
# is run from. yfinance/matplotlib/pandas come from the environment
# (see requirements.txt), never from a machine-specific path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_data.graham import get_graham_number  # noqa: E402
from market_data.names import get_company_name    # noqa: E402
from market_data.prices import get_price_snapshot  # noqa: E402
from charts import build_charts                   # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("REFRESH_BASE", _HERE)
DEFAULT_DB = os.environ.get(
    "INVESTMENTS_DB",
    os.path.join(os.path.dirname(_HERE), "backend", "investments.db"))
ET = ZoneInfo("America/New_York")

# Frozen 12c gap on the Nov 2026 seed lots: raw cash sum $4,956.17 vs
# Jason's settled $4,956.29 (CurrentValue pivot, 2026-11-12).
COST_ADJUSTMENT = 0.12
COST_BASIS = ("cash purchases only; reinvested dividends excluded "
              "(Jason, 2026-11-12)")


def round2(v):
    return math.floor(v * 100 + 0.5) / 100


def _year_ago(price_date):
    """'YYYY-MM-DD' minus 12 calendar months (day clamped)."""
    y, m, d = (int(x) for x in price_date.split("-"))
    y -= 1
    return f"{y:04d}-{m:02d}-{min(d, monthrange(y, m)[1]):02d}"


def _backfill_price_history(db, yf, ticker, price_date):
    """One-time 2y daily backfill of price_history for a ticker.

    Retries until the last year holds real daily history (at least
    100 rows — the sheet-era weekly rows only reach ~53, and a lone
    latest-close row reaches 1, so neither counts as "history") and
    no weekend rows remain in it (the weekly rows are dated Sundays
    and would shadow the Friday daily close in the server's lookup).
    2y, not 1y, so the 1-year reference date has a close on or
    before it (a 1y window starts a day too late). Never raises: a
    backfill failure leaves the ticker to the next run.
    """
    recent = db.execute(
        "SELECT COUNT(*) FROM price_history WHERE ticker=? AND date>=?",
        (ticker, _year_ago(price_date))).fetchone()[0]
    weekends = db.execute(
        "SELECT COUNT(*) FROM price_history WHERE ticker=? AND date>=?"
        " AND strftime('%w', date) IN ('0', '6')",
        (ticker, _year_ago(price_date))).fetchone()[0]
    if recent >= 100 and weekends == 0:
        return
    try:
        hist = yf.download(ticker, period="2y", progress=False,
                           auto_adjust=False)
        closes = hist["Close"]
        if hasattr(closes, "columns"):
            closes = closes[ticker]
        rows = [(ticker, str(dt.date()), round(float(v), 4))
                for dt, v in closes.dropna().items()]
        if rows:
            with db:
                # Prune the sheet-era weekly rows inside the window
                # the download covers: they are dated Sundays and
                # would shadow the Friday daily close in the server's
                # "latest on or before" lookup. Rows before the window
                # (pre-Nov 2024 weekly) are left alone.
                db.execute(
                    "DELETE FROM price_history WHERE ticker=? AND date>=?",
                    (ticker, rows[0][1]))
                db.executemany(
                    "INSERT OR IGNORE INTO price_history VALUES (?,?,?)",
                    rows)
    except Exception as e:
        print(f"price backfill skipped for {ticker}: {e}", file=sys.stderr)


def _refresh_watchlist_dividends(db, yf, tickers):
    """Cache split-adjusted per-share dividend payments for watched
    tickers in dividend_history (ticker, ex_date, amount).

    yfinance's dividends series is indexed by ex-date and already
    split-adjusted, so a payment history needs no adjustment of its
    own. One yfinance call per ticker, same cadence as the price
    refresh; a failure for one ticker never breaks the refresh or
    the others. Non-payers simply store no rows."""
    db.execute("CREATE TABLE IF NOT EXISTS dividend_history ("
               "ticker TEXT NOT NULL, ex_date TEXT NOT NULL,"
               " amount REAL NOT NULL,"
               " PRIMARY KEY (ticker, ex_date))")
    for t in tickers:
        try:
            divs = yf.Ticker(t).dividends
            if divs is None or divs.empty:
                continue
            rows = [(t, str(idx.date()), round(float(v), 6))
                    for idx, v in divs.items()]
            if rows:
                with db:
                    db.executemany(
                        "INSERT OR REPLACE INTO dividend_history"
                        " VALUES (?,?,?)", rows)
        except Exception as e:
            print(f"dividend history skipped for {t}: {e}",
                  file=sys.stderr)


def read_holdings(db):
    """lots -> {ticker: {shares, cost (cash only), div_reinvested,
    sector}}, exactly as snapshot.py aggregated CleanData."""
    holdings = defaultdict(lambda: {"shares": 0.0, "cost": 0.0,
                                    "div_reinvested": 0.0, "sector": ""})
    for ticker, shares, price, sector, ptype in db.execute(
            "SELECT ticker, shares, purchase_price, sector, purchase_type"
            " FROM lots ORDER BY row_num"):
        h = holdings[ticker]
        h["shares"] += shares
        if (ptype or "").strip().lower() == "dividends":
            h["div_reinvested"] += shares * price
        else:
            h["cost"] += shares * price
        h["sector"] = (sector or "").strip() or h["sector"]
    return holdings


def fetch_market(tickers):
    market = {}
    for t in tickers:
        p = get_price_snapshot(t)
        g = get_graham_number(t)
        n = get_company_name(t)
        market[t] = {"name": n.get("name") or t,
                     "price": p["price"], "prev_close": p["prev_close"],
                     "week_close": p["week_close"],
                     "day_change_pct": p["day_change_pct"],
                     "week_change_pct": p["week_change_pct"],
                     "close_date": p["close_date"],
                     "graham": g["graham"], "graham_note": g["graham_note"]}
    return market


def main():
    db_path = DEFAULT_DB
    if "--db" in sys.argv:
        db_path = sys.argv[sys.argv.index("--db") + 1]
    no_charts = "--no-charts" in sys.argv

    db = sqlite3.connect(db_path)
    holdings = read_holdings(db)
    tickers = sorted(holdings)
    market = fetch_market(tickers)

    # The price date is the latest close date any ticker reported —
    # stocks set it; fund NAVs lag a day and must not drag it back.
    close_dates = [m["close_date"] for m in market.values()
                   if m["close_date"]]
    if not close_dates:
        raise RuntimeError("no closing prices fetched for any ticker")
    price_date = max(close_dates)

    positions = []
    total_value = 0.0
    total_cost = 0.0
    for t in tickers:
        h = holdings[t]
        m = market[t]
        value = round(h["shares"] * m["price"], 2) if m["price"] else 0.0
        gain = round(value - h["cost"], 2)
        day_chg = None
        if m["price"] and m["prev_close"]:
            day_chg = round(100 * (m["price"] - m["prev_close"])
                            / m["prev_close"], 2)
        week_chg = None
        if m["price"] and m.get("week_close"):
            week_chg = round(100 * (m["price"] - m["week_close"])
                             / m["week_close"], 2)
        below_graham = bool(m["graham"] and m["price"]
                            and m["price"] < m["graham"])
        positions.append({
            "ticker": t, "name": m.get("name", t), "sector": h["sector"],
            "shares": round(h["shares"], 3), "cost": round(h["cost"], 2),
            "price": m["price"], "prev_close": m["prev_close"],
            "day_change_pct": day_chg,
            "week_close": m.get("week_close"), "week_change_pct": week_chg,
            "value": value, "gain": gain,
            "dividend_reinvested": round(h["div_reinvested"], 2),
            "gain_pct": round(100 * gain / h["cost"], 2) if h["cost"] else 0.0,
            "graham": m["graham"], "graham_note": m["graham_note"],
            "below_graham": below_graham,
        })
        total_value += value
        total_cost += h["cost"]

    total_cost = round(total_cost + COST_ADJUSTMENT, 2)
    total_gain = round(total_value - total_cost, 2)
    sectors = defaultdict(float)
    for p in positions:
        sectors[p["sector"] or "Unknown"] += p["value"]

    now = datetime.now(ET)
    run_date = now.date().isoformat()  # ET date, not the VM clock
    snapshot = {
        "as_of": run_date,
        "total_value": round(total_value, 2),
        "total_cost": total_cost,
        "total_gain": total_gain,
        "total_gain_pct": round(100 * total_gain / total_cost, 2)
        if total_cost else 0.0,
        "cost_basis": COST_BASIS,
        "total_dividend_reinvested": round(
            sum(p["dividend_reinvested"] for p in positions), 2),
        "sectors": {k: round(v, 2) for k, v in
                    sorted(sectors.items(), key=lambda kv: -kv[1])},
        "buy_candidates": [p["ticker"] for p in positions
                           if p["below_graham"]],
        "positions": positions,
        "totals_source": "live: investments.db lots x latest market closes",
        "sheet_total_value": None,
        "sheet_total_cost": None,
        "sheet_total_gain": None,
        "sheet_totals_row": None,
    }

    updated_at = now.strftime("%Y-%m-%d %H:%M %Z")
    # price_history feeds the watchlist card's 6M/1Y changes (the
    # server reads the latest close on or before the reference date).
    # The sheet-era sync used to fill it weekly and it stopped Nov 15;
    # the refresh now keeps one row per ticker per run and backfills
    # each holding with daily closes once (the weekly values match no
    # daily close, so they would skew the 6M/1Y changes).
    db.execute(
        "CREATE TABLE IF NOT EXISTS price_history ("
        "ticker TEXT, date TEXT, close REAL, "
        "PRIMARY KEY (ticker, date))")
    with db:
        db.execute(
            "INSERT OR REPLACE INTO sync_meta VALUES ('cost_adjustment', ?)",
            (json.dumps({"value": COST_ADJUSTMENT,
                         "note": "seed lots raw cash sum $4,956.17 vs "
                                 "Jason's settled $4,956.29 (2026-11-12)"}),))
        db.execute(
            "INSERT OR REPLACE INTO sync_meta VALUES ('last_refreshed_at', ?)",
            (updated_at,))
        for p in positions:
            db.execute(
                "INSERT OR REPLACE INTO market_data VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (p["ticker"], p.get("name"), p.get("price"),
                 p.get("prev_close"), p.get("day_change_pct"),
                 p.get("week_close"), p.get("week_change_pct"),
                 p.get("graham"), p.get("graham_note"),
                 price_date, updated_at))
            if p.get("price"):
                db.execute(
                    "INSERT OR REPLACE INTO price_history VALUES "
                    "(?,?,?)",
                    (p["ticker"], price_date, p["price"]))
            db.execute(
                "INSERT OR REPLACE INTO portfolio_snapshots VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (price_date, p["ticker"], p.get("shares"), p.get("cost"),
                 p.get("price"), p.get("prev_close"),
                 p.get("day_change_pct"), p.get("week_close"),
                 p.get("week_change_pct"), p.get("value"), p.get("gain"),
                 p.get("gain_pct"), p.get("dividend_reinvested"),
                 p.get("graham"), p.get("graham_note"),
                 1 if p.get("below_graham") else 0))
        db.execute(
            "INSERT OR REPLACE INTO portfolio_totals VALUES (?,?,?,?,?,?)",
            (price_date, snapshot["total_value"], snapshot["total_cost"],
             snapshot["total_gain"], snapshot["total_gain_pct"],
             snapshot["total_dividend_reinvested"]))

    # Holdings price history: the sheet-era sync filled price_history
    # weekly with values that match no daily close, so the card's 6M/1Y
    # changes would disagree with Yahoo by ~1%. Backfill each holding
    # with daily closes once (same helper as the watchlist); the daily
    # rows supersede the weekly ones in the server's lookup.
    import yfinance as yf
    for p in positions:
        if p.get("price"):
            _backfill_price_history(db, yf, p["ticker"], price_date)

    # Watchlist companion: refresh the price-feed rows for watched
    # tickers that are NOT holdings, so their cards get a sector chip,
    # a Graham number and the price header (price, day change from
    # market_data; 6M/1Y changes from price_history, backfilled two
    # years once per ticker). Guarded — a failure here never breaks
    # the holdings refresh above, and a DB without the watchlist
    # tables skips silently.
    watched = []
    try:
        has_watchlist = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='watchlist'").fetchone()
        if has_watchlist:
            watched = [r[0] for r in db.execute(
                "SELECT ticker FROM watchlist")]
    except sqlite3.Error:
        watched = []
    watched = [t for t in watched if t not in holdings]
    if watched:
        try:
            wmarket = fetch_market(watched)
            with db:
                for t in watched:
                    m = wmarket[t]
                    sector = None
                    is_fund = 0
                    try:
                        info = yf.Ticker(t).info or {}
                        sector = info.get("sector")
                        is_fund = 1 if info.get("quoteType") in (
                            "ETF", "MUTUALFUND") else 0
                    except Exception:
                        pass
                    db.execute(
                        "INSERT OR REPLACE INTO market_data VALUES "
                        "(?,?,?,?,?,?,?,?,?,?,?)",
                        (t, m.get("name"), m.get("price"),
                         m.get("prev_close"), m.get("day_change_pct"),
                         m.get("week_close"), m.get("week_change_pct"),
                         m.get("graham"), m.get("graham_note"),
                         price_date, updated_at))
                    db.execute(
                        "INSERT OR REPLACE INTO tickers VALUES (?,?,?,?)",
                        (t, m.get("name"), sector, is_fund))
            # Price history for the card's 6M/1Y changes (the server
            # reads price_history): the latest close each run, plus a
            # one-time 2y backfill for a ticker with no history yet —
            # 2y, not 1y, so the 1-year reference date has a close
            # on or before it (a 1y window starts a day too late).
            with db:
                for t in watched:
                    if wmarket[t].get("price"):
                        db.execute(
                            "INSERT OR REPLACE INTO price_history"
                            " VALUES (?,?,?)",
                            (t, price_date, wmarket[t]["price"]))
            for t in watched:
                _backfill_price_history(db, yf, t, price_date)
        except Exception as e:
            print(f"watchlist refresh skipped: {e}", file=sys.stderr)
            watched = []

    # Dividend history for the watchlist cards (all watched tickers,
    # holdings included): one yfinance call each, cached in
    # dividend_history. Guarded like the companion block above — a
    # failure here never breaks the holdings refresh.
    try:
        has_watchlist = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='watchlist'").fetchone()
        watched_all = ([r[0] for r in db.execute(
            "SELECT ticker FROM watchlist")] if has_watchlist else [])
    except sqlite3.Error:
        watched_all = []
    if watched_all:
        try:
            _refresh_watchlist_dividends(db, yf, watched_all)
        except Exception as e:
            print(f"dividend history skipped: {e}", file=sys.stderr)
    db.close()

    os.makedirs(os.path.join(BASE, "snapshots"), exist_ok=True)
    with open(os.path.join(BASE, "snapshots", f"{run_date}.json"), "w") as f:
        json.dump(snapshot, f, indent=2)
    with open(os.path.join(BASE, "latest.json"), "w") as f:
        json.dump(snapshot, f, indent=2)
    charts = None
    if not no_charts:
        try:
            build_charts(positions)
            charts = True
        except Exception as e:
            charts = False
            snapshot["chart_error"] = str(e)[:200]
            with open(os.path.join(BASE, "latest.json"), "w") as f:
                json.dump(snapshot, f, indent=2)

    print(json.dumps({"ok": True, "price_date": price_date,
                      "run_date": run_date, "tickers": len(positions),
                      "watchlist": len(watched),
                      "total_value": snapshot["total_value"],
                      "total_cost": snapshot["total_cost"],
                      "charts": charts}))


if __name__ == "__main__":
    main()
