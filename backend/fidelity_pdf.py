#!/usr/bin/env python3
"""Fidelity statement -> investments.db lot ingest.

Parses a monthly Fidelity Investment Report (pdftotext -layout text)
and upserts its dividend-reinvestment and cash-purchase lots into the
lots table, and records the core cash balance per statement period.
Built against the real October 2026 statement layout — do not assume
other months look identical; anything the parser cannot classify is
reported as needing review, never silently skipped or guessed.

What it handles (verified on the Oct 2026 statement):
  - "Dividends, Interest & Other Income" -> Reinvestment rows become
    lots with purchase_type "Dividends". "Dividend Received" rows carry
    no shares and are skipped. The settlement date is the purchase
    date (a row's embedded "TRADE DATE" is ignored — the sheet used
    the settlement date too).
  - "Securities Bought & Sold" -> "You Bought" rows become lots with
    purchase_type "Cash" (same row shape as the dividend rows: date,
    name, CUSIP, quantity, price). "You Sold" rows are reported as
    needing review, never auto-ingested. CAVEAT: no statement seen so
    far contains this section, so this parser is written defensively
    against Fidelity's row shape and is UNVERIFIED against a real buy
    — anything that does not parse cleanly lands in needs_review.
  - Cash position: the core account (SPAXX) ending market value is
    read from the Holdings "Total Core Account" row, cross-checked
    against the core position row, and stored per statement period in
    cash_positions. No backfill — recording starts with the next
    statement uploaded after this change.
  - Tickers come from the statement's Holdings section ("NAME (SYM)")
    first. The fallback name map is DERIVED from the DB's tickers
    table (real company names, seeded from the sheet): a statement
    name resolves when its words match the company's name words in
    order, each a prefix of a name word ("UNITED MICR" ->
    "United Microelectronics Corporation"). Ambiguous or unmatched
    names resolve to "?" and land in needs_review.
  - The only hardcoded name rule left is the core classification:
    "FIDELITY GOVERNMENT MONEY" (and ticker SPAXX) is never a lot —
    it is the core money-market position, and it is not in the
    tickers table, so nothing can derive it.
  - Sectors come from the DB's tickers table; a new ticker gets "" and
    is flagged in the report.

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

# The only hardcoded name rule: the core money-market position is
# never a lot. Its name ("FIDELITY GOVERNMENT MONEY") and its ticker
# (SPAXX) are not in the DB's tickers table, so nothing can derive
# this classification — it has to be stated. Every other name resolves
# from the statement's Holdings section first, then from the DB's
# ticker names (see match_derived_name).
CORE_FRAGMENTS = ("FIDELITY GOVERNMENT MONEY",)
CORE_TICKER = "SPAXX"

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


def _name_words(s):
    """Normalized name -> word list, leading THE dropped (so
    "COCA-COLA" matches "The Coca-Cola Company")."""
    words = norm_name(s).replace(".", "").split()
    if words and words[0] == "THE":
        words = words[1:]
    return words


def match_derived_name(name, ticker_names):
    """Statement name -> ticker from the DB's ticker names, or "?".

    ticker_names maps ticker -> company name. A statement name
    resolves when its words match the company name's words in order,
    each a prefix of a name word, skipping filler words ("BANK
    AMERICA" -> "Bank of America Corporation"; "UNITED MICR" ->
    "United Microelectronics Corporation"). The match works in either
    direction, because the statement sometimes appends a word the DB
    name lacks ("FIDELITY CORPORATE BOND FUND" vs "Fidelity
    Corporate Bond"). Zero matches or more than one match both return
    "?" — never guess."""
    frag = _name_words(name)
    if not frag or not ticker_names:
        return "?"
    hits = []
    for ticker, company in ticker_names.items():
        words = _name_words(company)
        if _subseq_prefix(frag, words) or _subseq_prefix(words, frag):
            hits.append(ticker)
    return hits[0] if len(hits) == 1 else "?"


def _subseq_prefix(needle, haystack):
    """True when needle's words appear in haystack in order, each a
    prefix of a haystack word (other haystack words may be skipped)."""
    i = 0
    for w in haystack:
        if i < len(needle) and w.startswith(needle[i]):
            i += 1
    return i == len(needle)


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
    end = f"{y2}-{months[m.group(4)]:02d}-{int(m.group(5)):02d}"
    return f"{y1}-{months[m.group(1)]:02d}", y1, end


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


def resolve_ticker(name, hmap, ticker_names=None):
    """Statement name -> ticker, or None for the core position, or "?"
    when nothing resolves. Holdings map wins; then the core rule; then
    the DB-derived names."""
    n = norm_name(name)
    if n in hmap:
        return None if hmap[n] == CORE_TICKER else hmap[n]
    if any(frag in n for frag in CORE_FRAGMENTS):
        return None
    return match_derived_name(name, ticker_names)


def parse_dividends(lines, year, hmap, ticker_names=None):
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
            ticker = resolve_ticker(name, hmap, ticker_names)
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
            ticker = resolve_ticker(current["name"], hmap, ticker_names)
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


BUY_SELL_RE = re.compile(r"^(You\s+)?(Bought|Sold)\b\s*(.*)$")


def _trailing_amounts(s):
    """Last three numeric tokens of s as {qty, price, name_end}, or
    None. Used for Bought & Sold rows, whose trailing columns are
    quantity, price, amount (a commission column, if present, sits
    before them and is ignored by taking the last three)."""
    toks = [(m.group(0), m.start())
            for m in re.finditer(r"-?\$?[\d,]+\.\d+", s)]
    if len(toks) < 3:
        return None
    try:
        qty = float(toks[-3][0].replace("$", "").replace(",", ""))
        price = float(toks[-2][0].replace("$", "").replace(",", ""))
    except ValueError:
        return None
    return {"qty": qty, "price": price, "name_end": toks[-3][1]}


def parse_bought_sold(lines, year, hmap, ticker_names=None):
    """The "Securities Bought & Sold" section -> Cash lots, plus rows
    that need review. UNVERIFIED: no statement seen so far contains
    this section, so the row shape is assumed from Fidelity's layout
    (date, action, name, CUSIP, quantity, price, amount) — the same
    shape as the dividend rows. Anything that does not parse cleanly,
    and every sale, lands in unhandled rather than being guessed."""
    lots, unhandled = [], []
    in_section = False
    for line in lines:
        s = line.strip()
        if s.startswith("Securities Bought & Sold"):
            in_section = True
            continue
        if not in_section:
            continue
        if s.startswith("Total ") or s in (
                "Dividends, Interest & Other Income", "Deposits",
                "Core Fund Activity", "Other Activity"):
            break
        m = ROW_RE.match(line)
        if not m:
            continue
        rest = m.group("rest")
        bm = BUY_SELL_RE.match(rest)
        if not bm:
            unhandled.append({"date": m.group("date"), "line": line.strip(),
                              "reason": "no buy/sell action"})
            continue
        action = bm.group(2)
        after_action = bm.group(3)
        cm = find_cusip(after_action)
        name = None
        am = None
        if cm:
            name = norm_name(after_action[:cm.start()])
            am = _trailing_amounts(after_action[cm.end():])
        else:
            am = _trailing_amounts(after_action)
            if am:
                name = norm_name(after_action[:am["name_end"]])
        if not am or not name:
            unhandled.append({"date": m.group("date"), "line": line.strip(),
                              "reason": "amount columns did not parse"})
            continue
        if action == "Sold":
            unhandled.append({"date": m.group("date"), "name": name,
                              "reason": "sale — needs review (sales are "
                                        "not auto-ingested)"})
            continue
        ticker = resolve_ticker(name, hmap, ticker_names)
        if ticker == "?":
            unhandled.append({"date": m.group("date"), "name": name,
                              "reason": "unknown security name"})
            continue
        if ticker is None:
            continue  # core fund sweep, never a lot
        mm, dd = m.group("date").split("/")
        lots.append({
            "kind": "lot", "ticker": ticker,
            "purchase_date": f"{int(mm)}/{int(dd)}/{year}",
            "shares": am["qty"], "purchase_price": am["price"],
            "purchase_type": "Cash", "name": name,
        })
    return lots, unhandled


def parse_cash(lines):
    """Core account ending balance from the Holdings section.

    Primary: the "Total Core Account" row — its dollar amounts in
    order are [beginning market value, ENDING market value, EAI], so
    the ending balance is the second. Cross-check: the core position
    row ("FIDELITY GOVERNMENT MONEY ...") — its dollar amounts are
    [beginning market value, price, ENDING market value, EAI], so the
    ending balance is the third. The two must agree; if only one
    parses, it is used; if they disagree, nothing is returned and the
    caller reports why instead of guessing.
    Only the Holdings section is scanned (the Activity pages reuse the
    core fund's name with different columns). Returns
    (balance_or_None, note_or_None)."""
    total = None
    position = None
    in_holdings = False
    for line in lines:
        s = line.strip()
        if s.startswith("Holdings"):
            in_holdings = True
            continue
        if s.startswith("Activity"):
            break
        if not in_holdings:
            continue
        if s.startswith("Total Core Account"):
            amounts = [float(a.replace(",", ""))
                       for a in re.findall(r"\$([\d,]+\.\d{2})", s)]
            if len(amounts) >= 2:
                total = amounts[1]
        elif "FIDELITY GOVERNMENT MONEY" in s:
            amounts = [float(a.replace(",", ""))
                       for a in re.findall(r"\$([\d,]+\.\d{2})", s)]
            if len(amounts) >= 3:
                position = amounts[2]
    if total is not None and position is not None:
        if abs(total - position) > 0.01:
            return None, ("core balance lines disagree "
                          "(Total Core Account vs position row)")
        return total, None
    if total is not None:
        return total, None
    if position is not None:
        return position, None
    return None, "core balance lines not found in Holdings"


def parse_text(text, ticker_names=None):
    period, year, period_end = statement_period(text)
    lines = text.splitlines()
    hmap = holdings_map(lines)
    lots, skipped, unhandled = parse_dividends(lines, year, hmap,
                                               ticker_names)
    bs_lots, bs_unhandled = parse_bought_sold(lines, year, hmap,
                                              ticker_names)
    lots = lots + bs_lots
    unhandled = unhandled + bs_unhandled
    cash_balance, cash_note = parse_cash(lines)
    cash = ({"balance": cash_balance, "as_of": period_end}
            if cash_balance is not None else None)
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
    return {"statement_period": period, "lots": lots,
            "skipped": skipped, "unhandled": unhandled,
            "activity_sections": activity,
            "needs_review": bool(unhandled),
            "cash": cash, "cash_note": cash_note}


def parse_pdf(path, ticker_names=None):
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True, check=True)
    return parse_text(out.stdout, ticker_names)


def txn_key(lot):
    return "|".join([lot["ticker"], lot["purchase_date"],
                     f"{lot['shares']:.3f}", f"{lot['purchase_price']:.4f}",
                     lot["purchase_type"]])


def ensure_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS pdf_imports ("
        " statement_period TEXT, txn_key TEXT PRIMARY KEY,"
        " lot_row_num INTEGER, imported_at TEXT)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS cash_positions ("
        " statement_period TEXT PRIMARY KEY, balance REAL, as_of TEXT)")


def ingest(db_path, parsed, dry_run=False):
    db = sqlite3.connect(db_path)
    ensure_schema(db)
    now = datetime.now(ET).strftime("%Y-%m-%d %H:%M %Z")
    result = {"inserted": [], "already_in_db": [], "already_imported": [],
              "new_ticker_warnings": [], "cash_recorded": None}
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
        cash = parsed.get("cash")
        if cash and cash.get("balance") is not None:
            if not dry_run:
                db.execute(
                    "INSERT OR REPLACE INTO cash_positions VALUES (?,?,?)",
                    (parsed["statement_period"], cash["balance"],
                     cash.get("as_of")))
            result["cash_recorded"] = {
                "statement_period": parsed["statement_period"],
                "balance": cash["balance"], "as_of": cash.get("as_of")}
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
    ticker_names = None
    if os.path.exists(db_path):
        try:
            _db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            ticker_names = {r[0]: r[1] for r in _db.execute(
                "SELECT ticker, name FROM tickers")}
            _db.close()
        except sqlite3.Error:
            ticker_names = None
    if args[0] == "--text":
        parsed = parse_text(open(args[1]).read(), ticker_names)
    else:
        parsed = parse_pdf(args[0], ticker_names)
    summary = {"statement_period": parsed["statement_period"],
               "lots_found": len(parsed["lots"]),
               "skipped": parsed["skipped"],
               "unhandled": parsed["unhandled"],
               "activity_sections": parsed["activity_sections"],
               "cash": parsed["cash"],
               "cash_note": parsed.get("cash_note"),
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
