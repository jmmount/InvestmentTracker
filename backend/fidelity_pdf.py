#!/usr/bin/env python3
"""Fidelity statement -> investments.db lot ingest.

Parses a monthly Fidelity Investment Report (pdftotext -layout text)
and upserts its dividend-reinvestment lots into the lots table. Built
against the real October 2026 statement layout — do not assume other
months look identical; anything the parser cannot classify is reported
as needing review, never silently skipped or guessed.

What it handles (verified on the Oct 2026 statement):
  - "Dividends, Interest & Other Income" -> Reinvestment rows become
    lots with purchase_type "Dividends". "Dividend Received" rows carry
    no shares and are skipped. The settlement date is the purchase
    date (a row's embedded "TRADE DATE" is ignored — the sheet used
    the settlement date too).
  - Tickers come from the statement's Holdings section ("NAME (SYM)")
    with an alias map as fallback. The core money-market position
    (SPAXX) is never a lot.
  - Sectors come from the DB's tickers table; a new ticker gets "" and
    is flagged in the report.

What it does NOT handle yet (no example exists in the Oct statement):
  - A "Securities Bought & Sold" section (cash buys / sales). If one
    appears, its rows are listed as needs_review and the run exits 2
    after ingesting the clean dividend rows.

Idempotency: every lot carries a stable key
(ticker, purchase_date, shares, price, purchase_type). The pdf_imports
table records ingested keys per statement period, so a re-run inserts
nothing; a lot already in the DB from the sheet seed is matched by the
same key and skipped. A backup copy of the DB is taken before any
write (investments.db.bak-YYYYMMDD-HHMMSS next to the DB).

    python3 fidelity_pdf.py statement.pdf [--db PATH] [--dry-run]
    python3 fidelity_pdf.py --text statement.txt [--db PATH] [--dry-run]

The PDF itself is never copied into the repo — it stays where Jason
put it. No account numbers, addresses or balances are printed.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "investments.db")
ET = ZoneInfo("America/New_York")

# Distinctive name fragments -> ticker. Holdings-derived names win;
# this map covers names the Holdings section wraps or abbreviates.
# None = never a lot (core money-market position).
ALIASES = {
    "COCA-COLA": "KO",
    "ALPHABET": "GOOGL",
    "BANK AMERICA": "BAC",
    "NOVO NORDISK": "NVO",
    "PERMIAN RESOURCES": "PR",
    "UNITED MICR": "UMC",
    "VISA": "V",
    "FIDELITY ZERO LARGE CAP": "FNILX",
    "FIDELITY ZERO INTERNATIONAL": "FZILX",
    "FIDELITY INVESTMENT GRADE": "FBNDX",
    "FIDELITY CORPORATE BOND": "FCBFX",
    "FIDELITY GOVERNMENT MONEY": None,
}

CUSIP_RE = re.compile(r"\b[0-9A-Z]{9}\b")


def find_cusip(s):
    """First 9-char alnum token with >= 5 digits, else None."""
    for m in CUSIP_RE.finditer(s):
        if sum(c.isdigit() for c in m.group(0)) >= 5:
            return m
    return None
ROW_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(?P<rest>.+)$")
AMOUNT_RE = re.compile(
    r"^(?P<desc>Reinvestment|Dividend Received|Interest Received)\s+"
    r"(?P<qty>-|[\d,]+\.\d+)\s+"
    r"(?P<price>-|\$?[\d,]+\.\d+)\s*"
    r"(?P<amount>-?\$?[\d,]+\.\d+)?\s*$")
PERIOD_RE = re.compile(
    r"([A-Z][a-z]+) (\d{1,2}), (\d{4})\s*-\s*([A-Z][a-z]+) (\d{1,2}), (\d{4})")
SYMBOL_RE = re.compile(r"\(([A-Z]{2,6})\)")


def norm_name(s):
    s = re.sub(r"TRADE DATE \d{2}-\d{2}-\d{2}", "", s or "")
    s = re.sub(r"\s+", " ", s.upper()).strip()
    return s


def statement_period(text):
    m = PERIOD_RE.search(text)
    if not m:
        raise RuntimeError("statement period header not found "
                           "(expected 'Month D, YYYY - Month D, YYYY')")
    months = {"January": 1, "February": 2, "March": 3, "April": 4,
              "May": 5, "June": 6, "July": 7, "August": 8,
              "September": 9, "October": 10, "November": 11,
              "December": 12}
    y1, y2 = int(m.group(3)), int(m.group(6))
    if y1 != y2:
        raise RuntimeError(f"statement spans years {y1}-{y2}; refusing")
    return f"{y1}-{months[m.group(1)]:02d}", y1


def holdings_map(lines):
    """NAME -> ticker from the Holdings section's 'NAME (SYM)' lines.
    Wrapped names span two lines, so a short prefix pulls in the
    previous line's text (numbers stripped)."""
    out = {}
    prev_clean = ""
    for line in lines:
        m = SYMBOL_RE.search(line)
        if m:
            prefix = re.sub(r"[\d$,\.]+$", "", line[:m.start()]).strip()
            name = prefix
            if len(norm_name(prefix)) < 12 and prev_clean:
                name = f"{prev_clean} {prefix}"
            name = norm_name(name)
            if name:
                out[name] = m.group(1)
        # keep the previous line's text (numbers stripped) for wraps
        cleaned = re.sub(r"[\d$,\.]+$", "", line).strip()
        if cleaned and not re.search(r"\d", cleaned):
            prev_clean = norm_name(cleaned)
        elif cleaned:
            prev_clean = ""
    return out


def resolve_ticker(name, hmap):
    n = norm_name(name)
    if n in hmap:
        return hmap[n]
    for frag, ticker in ALIASES.items():
        if frag in n:
            return ticker
    return "?"


def parse_dividends(lines, year, hmap):
    """The Dividends, Interest & Other Income subsection -> lot dicts
    plus a report of rows/sections that need review."""
    lots, skipped, unhandled, seen_other_sections = [], [], [], []
    in_section = False
    current = None  # row being assembled (for wrapped names)

    def flush():
        nonlocal current
        if current is not None:
            lots.append(current) if current["kind"] == "lot" \
                else skipped.append(current)
            current = None

    for line in lines:
        if line.strip().startswith("Dividends, Interest & Other Income"):
            in_section = True
            continue
        if not in_section:
            continue
        if line.strip().startswith("Total Dividends"):
            flush()
            break
        m = ROW_RE.match(line)
        if m:
            flush()
            rest = m.group("rest")
            cm = find_cusip(rest)
            if not cm:
                unhandled.append({"date": m.group("date"), "line": line.strip(),
                                  "reason": "no CUSIP found"})
                continue
            name = norm_name(rest[:cm.start()])
            am = AMOUNT_RE.match(rest[cm.end():].strip())
            if not am:
                unhandled.append({"date": m.group("date"), "line": line.strip(),
                                  "reason": "amount columns did not parse"})
                continue
            desc = am.group("desc")
            if desc != "Reinvestment":
                skipped.append({"date": m.group("date"), "name": name,
                                "desc": desc, "kind": "income"})
                continue
            ticker = resolve_ticker(name, hmap)
            if ticker == "?":
                unhandled.append({"date": m.group("date"), "name": name,
                                  "reason": "unknown security name"})
                continue
            if ticker is None:
                skipped.append({"date": m.group("date"), "name": name,
                                "desc": desc, "kind": "core"})
                continue
            mm, dd = m.group("date").split("/")
            current = {
                "kind": "lot", "ticker": ticker,
                "purchase_date": f"{int(mm)}/{int(dd)}/{year}",
                "shares": float(am.group("qty").replace(",", "")),
                "purchase_price": float(am.group("price").replace("$", "")
                                        .replace(",", "")),
                "purchase_type": "Dividends",
                "name": name,
            }
            continue
        # continuation line: a wrapped security name belongs to the row
        # above (e.g. "MARKET" under "FIDELITY GOVERNMENT MONEY").
        stripped = line.strip()
        if current is not None and stripped and re.fullmatch(
                r"[A-Z][A-Z &\.\-]*", stripped):
            current["name"] = norm_name(current["name"] + " " + stripped)
            ticker = resolve_ticker(current["name"], hmap)
            if ticker == "?":
                unhandled.append({"date": current["purchase_date"],
                                  "name": current["name"],
                                  "reason": "unknown security name"})
                current = None
            elif ticker is None:
                skipped.append({"date": current["purchase_date"],
                                "name": current["name"],
                                "desc": "Reinvestment", "kind": "core"})
                current = None
            else:
                current["ticker"] = ticker
    flush()
    return lots, skipped, unhandled


def parse_text(text):
    period, year = statement_period(text)
    lines = text.splitlines()
    hmap = holdings_map(lines)
    lots, skipped, unhandled = parse_dividends(lines, year, hmap)
    # Any other Activity subsection is reported, not silently ignored.
    activity = []
    in_activity = False
    for line in lines:
        s = line.strip()
        if s.startswith("Activity"):
            in_activity = True
            continue
        if in_activity:
            if s in ("Dividends, Interest & Other Income", "Deposits",
                     "Core Fund Activity", "Securities Bought & Sold"):
                activity.append(s)
            if s.startswith("Total Core Fund Activity"):
                break
    bought_sold = [a for a in activity if "Bought" in a]
    return {"statement_period": period, "lots": lots,
            "skipped": skipped, "unhandled": unhandled,
            "activity_sections": activity,
            "needs_review": bool(unhandled or bought_sold)}


def parse_pdf(path):
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True, check=True)
    return parse_text(out.stdout)


def txn_key(lot):
    return "|".join([lot["ticker"], lot["purchase_date"],
                     f"{lot['shares']:.3f}", f"{lot['purchase_price']:.4f}",
                     lot["purchase_type"]])


def ensure_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS pdf_imports ("
        " statement_period TEXT, txn_key TEXT PRIMARY KEY,"
        " lot_row_num INTEGER, imported_at TEXT)")


def ingest(db_path, parsed, dry_run=False):
    db = sqlite3.connect(db_path)
    ensure_schema(db)
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")
    result = {"inserted": [], "already_in_db": [], "already_imported": [],
              "new_ticker_warnings": []}
    max_row = db.execute("SELECT COALESCE(MAX(row_num), 0) FROM lots"
                         ).fetchone()[0]
    sectors = {r[0]: r[1] for r in db.execute(
        "SELECT ticker, sector FROM tickers")}
    with db:
        for lot in parsed["lots"]:
            key = txn_key(lot)
            if db.execute("SELECT 1 FROM pdf_imports WHERE txn_key=?",
                          (key,)).fetchone():
                result["already_imported"].append(key)
                continue
            existing = db.execute(
                "SELECT row_num FROM lots WHERE ticker=? AND "
                "purchase_date=? AND ABS(shares - ?) < 0.0005 AND "
                "ABS(purchase_price - ?) < 0.005 AND purchase_type=?",
                (lot["ticker"], lot["purchase_date"], lot["shares"],
                 lot["purchase_price"], lot["purchase_type"])).fetchone()
            if existing:
                result["already_in_db"].append(
                    {"key": key, "row_num": existing[0]})
                if not dry_run:
                    db.execute(
                        "INSERT OR IGNORE INTO pdf_imports VALUES (?,?,?,?)",
                        (parsed["statement_period"], key, existing[0], now))
                continue
            if lot["ticker"] not in sectors:
                result["new_ticker_warnings"].append(lot["ticker"])
            max_row += 1
            ts = lot["purchase_date"] + " 00:00:00"
            if not dry_run:
                db.execute(
                    "INSERT INTO lots VALUES (?,?,?,?,?,?,?,?)",
                    (max_row, ts, lot["ticker"], lot["purchase_date"],
                     lot["shares"], lot["purchase_price"],
                     sectors.get(lot["ticker"], ""), lot["purchase_type"]))
                db.execute(
                    "INSERT INTO pdf_imports VALUES (?,?,?,?)",
                    (parsed["statement_period"], key, max_row, now))
            result["inserted"].append({"key": key, "row_num": max_row,
                                      "ticker": lot["ticker"]})
    db.close()
    return result


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    db_path = DEFAULT_DB
    if "--db" in args:
        db_path = args[args.index("--db") + 1]
        args = [a for a in args if a not in ("--db", db_path)]
    if not args:
        print("usage: fidelity_pdf.py <statement.pdf> [--db PATH] "
              "[--dry-run] | --text <statement.txt>", file=sys.stderr)
        return 2
    if args[0] == "--text":
        parsed = parse_text(open(args[1]).read())
    else:
        parsed = parse_pdf(args[0])
    summary = {"statement_period": parsed["statement_period"],
               "lots_found": len(parsed["lots"]),
               "skipped": parsed["skipped"],
               "unhandled": parsed["unhandled"],
               "activity_sections": parsed["activity_sections"],
               "dry_run": dry_run}
    if parsed["lots"] and not dry_run:
        backup = (f"{db_path}.bak-"
                  f"{datetime.now(ET).strftime('%Y%m%d-%H%M%S')}")
        shutil.copyfile(db_path, backup)
        summary["db_backup"] = backup
    summary.update(ingest(db_path, parsed, dry_run=dry_run))
    print(json.dumps(summary, indent=2))
    return 2 if parsed["needs_review"] else 0


if __name__ == "__main__":
    sys.exit(main())
