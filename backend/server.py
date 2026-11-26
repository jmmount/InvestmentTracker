#!/usr/bin/env python3
"""Investment Tracker — local backend (SQLite read path).

Serves the prebuilt frontend (frontend/dist) and the portfolio JSON from the
local SQLite store (backend/investments.db, refreshed by
~/workspace/investments/refresh_db.py — no sheet involved).
The payload is computed from the lots table with the exact aggregation
and rounding of apps-script/Code.gs buildPayload_ — including the
cash-only cost basis (Jason, 2026-11-12): reinvested-dividend lots add
shares and value, never cost. One deliberate difference from the old
endpoint: total_cost carries the frozen +$0.12 adjustment on the Nov
2026 seed lots (raw cash sum $4,956.17 vs Jason's settled $4,956.29),
read from sync_meta; see cost_adjustment().

Endpoints:
  GET  /api/portfolio            -> the doGet payload (same shape)
  POST /api/upload-statement     -> multipart Fidelity statement PDF;
                                   parses it and returns the lots it
                                   would insert plus the core cash
                                   balance it would record (preview
                                   only — writes nothing to the DB)
  POST /api/upload-statement/confirm -> { statement_period, lots, cash }
                                   inserts exactly the confirmed lots
                                   and records the cash balance
                                   (backup of investments.db first)
  POST /api/consult              -> { action: "consult", messages }
                                   (Gemini chat grounded in the live
                                   payload; GEMINI_API_KEY from the
                                   environment, never in the repo)

The uploaded statement PDF is never stored: it is parsed from a temp
file that is deleted right after parsing, and the confirm step only
ever sees the parsed lot list, never the PDF itself.

Run:  python3 backend/server.py [--port 8768]
"""
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import fidelity_pdf

HERE = Path(__file__).parent
DIST = HERE.parent / "frontend" / "dist"
DB_PATH = HERE / "investments.db"
ET = ZoneInfo("America/New_York")
COST_BASIS = ("cash purchases only; reinvested dividends excluded "
              "(Jason, 2026-11-12)")


def _load_env():
    """Load backend/.env (gitignored) into the environment if present.

    Lets the machine that runs this server hold GEMINI_API_KEY without
    exporting it in every shell. A real environment variable wins.
    """
    try:
        lines = (HERE / ".env").read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def round2(v):
    """JavaScript Math.round(v * 100) / 100 (half toward +infinity)."""
    return math.floor(v * 100 + 0.5) / 100


def round3(v):
    return math.floor(v * 1000 + 0.5) / 1000


def aggregate_lots(db):
    """lots -> per-ticker {shares, cost (cash only), dividend, sector},
    in first-appearance order, exactly as Code.gs aggregateLots_."""
    by_ticker = {}
    for row in db.execute(
            "SELECT ticker, shares, purchase_price, sector, purchase_type"
            " FROM lots ORDER BY row_num"):
        ticker, shares, price, sector, ptype = row
        a = by_ticker.setdefault(
            ticker, {"shares": 0.0, "cost": 0.0, "dividend": 0.0,
                     "sector": sector})
        a["shares"] += shares
        if ptype.strip().lower() == "dividends":
            a["dividend"] += shares * price
        else:
            a["cost"] += shares * price
        if sector:
            a["sector"] = sector
    return by_ticker


def cost_adjustment(db):
    """Frozen +$0.12 gap on the Nov 2026 seed lots (see refresh_db.py):
    the lots sum to $4,956.17 at raw precision while Jason's settled
    cash cost is $4,956.29 (the sheet's CurrentValue pivot, 2026-11-12).
    Stored in sync_meta by the refresh; 0.0 when absent."""
    try:
        row = db.execute(
            "SELECT value FROM sync_meta WHERE key='cost_adjustment'"
        ).fetchone()
        if row:
            return float(json.loads(row[0]).get("value", 0.0))
    except Exception:
        pass
    return 0.0


def build_payload(db):
    """The doGet payload, computed from the DB (Code.gs buildPayload_)."""
    by_ticker = aggregate_lots(db)
    market = {r[0]: r for r in db.execute(
        "SELECT ticker, name, price, prev_close, day_change_pct, week_close,"
        " week_change_pct, graham, graham_note, close_date FROM market_data")}
    fallback = {r[0]: r[1] for r in db.execute(
        "SELECT ticker, price FROM current_value_prices")}

    positions = []
    total_value = 0.0
    total_cost = 0.0
    total_dividend = 0.0
    sectors = {}
    market_as_of = None

    for ticker, a in by_ticker.items():
        m = market.get(ticker)
        if m and m[9] and market_as_of is None:
            market_as_of = m[9]
        # MarketData wins; the CurrentValue pivot price is the fallback.
        price = m[2] if (m and m[2] is not None) else fallback.get(ticker)
        value = round2(a["shares"] * price) if price is not None else None
        gain = round2(value - a["cost"]) if value is not None else None
        graham = m[7] if m else None
        graham_note = (m[8] or "") if m else "No market data yet for this ticker"
        positions.append({
            "ticker": ticker,
            "name": (m[1] if m and m[1] else ticker),
            "sector": a["sector"],
            "shares": round3(a["shares"]),
            "cost": round2(a["cost"]),
            "price": price,
            "prev_close": m[3] if m else None,
            "day_change_pct": m[4] if m else None,
            "week_close": m[5] if m else None,
            "week_change_pct": m[6] if m else None,
            "value": value,
            "gain": gain,
            "dividend_reinvested": round2(a["dividend"]),
            "gain_pct": (None if gain is None or a["cost"] == 0
                         else round2(gain / a["cost"] * 100)),
            "graham": graham,
            "graham_note": graham_note,
            "below_graham": (graham is not None and price is not None
                             and price < graham),
        })
        total_cost += a["cost"]
        total_dividend += a["dividend"]
        if value is not None:
            total_value += value
            sectors[a["sector"]] = round2(sectors.get(a["sector"], 0) + value)

    positions.sort(key=lambda p: -(p["value"] or 0))
    total_cost = round2(total_cost + cost_adjustment(db))
    total_gain = round2(total_value - total_cost)
    return {
        "as_of": datetime.now(ET).strftime("%Y-%m-%d"),
        "source": "sqlite-local",
        "total_value": round2(total_value),
        "total_cost": total_cost,
        "total_gain": total_gain,
        "total_gain_pct": (0 if total_cost == 0
                           else round2(total_gain / total_cost * 100)),
        "cost_basis": COST_BASIS,
        "total_dividend_reinvested": round2(total_dividend),
        "sectors": sectors,
        "buy_candidates": [p["ticker"] for p in positions if p["below_graham"]],
        "market_as_of": market_as_of,
        "cash": latest_cash(db),
        "positions": positions,
        "history": [{"date": r[0], "value": r[1]} for r in db.execute(
            "SELECT snapshot_date, total_value FROM portfolio_totals"
            " ORDER BY snapshot_date")],
    }


def latest_cash(db):
    """Newest recorded core cash position, or None. Defensive: the
    cash_positions table only exists after the first statement confirm
    that records one, so a missing table is a normal None, not an
    error. Cash is reported as its own line; total_value stays
    holdings-only and never includes it."""
    try:
        row = db.execute(
            "SELECT statement_period, balance, as_of FROM cash_positions"
            " ORDER BY statement_period DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return {"balance": round2(row[1]), "statement_period": row[0],
            "as_of": row[2]}


# ---------------------------------------------------------------------------
# Statement upload — Fidelity PDF -> lots, preview first, confirm writes.
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
LOT_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
TICKER_RE = re.compile(r"^[A-Z]{1,6}$")


def _parse_multipart(body, content_type):
    """Minimal multipart/form-data parse: return the first file part's
    (filename, bytes). Stdlib only; the app has exactly one upload
    field, so no general-purpose parser is warranted."""
    m = re.search(r"boundary=([^;]+)", content_type or "")
    if not m:
        raise ValueError("upload needs a multipart body with a boundary")
    boundary = m.group(1).strip().strip('"').encode()
    parts = body.split(b"--" + boundary)
    for part in parts:
        if b'filename="' not in part:
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not data:
            continue
        name_m = re.search(rb'filename="([^"]*)"', head)
        filename = (name_m.group(1).decode("utf-8", "replace")
                    if name_m else "statement.pdf")
        # Strip the trailing CRLF that precedes the next boundary.
        if data.endswith(b"\r\n"):
            data = data[:-2]
        return filename, data
    raise ValueError("no file part in the upload")


def _classify_lots(db, lots):
    """Read-only: for each parsed lot, is it new, already imported from
    this statement, or already in the lots table (e.g. from the seed)?
    Nothing here writes — the preview must never touch the DB."""
    has_imports = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table'"
        " AND name='pdf_imports'").fetchone() is not None
    sectors = {r[0]: r[1] for r in db.execute(
        "SELECT ticker, sector FROM tickers")}
    out = []
    for lot in lots:
        key = fidelity_pdf.txn_key(lot)
        if has_imports and db.execute(
                "SELECT 1 FROM pdf_imports WHERE txn_key=?",
                (key,)).fetchone():
            status = "already_imported"
        elif db.execute(
                "SELECT 1 FROM lots WHERE ticker=? AND purchase_date=?"
                " AND ABS(shares - ?) < 0.0005"
                " AND ABS(purchase_price - ?) < 0.005"
                " AND purchase_type=?",
                (lot["ticker"], lot["purchase_date"], lot["shares"],
                 lot["purchase_price"], lot["purchase_type"])).fetchone():
            status = "already_in_db"
        else:
            status = "new"
        out.append({"ticker": lot["ticker"],
                    "purchase_date": lot["purchase_date"],
                    "shares": lot["shares"],
                    "purchase_price": lot["purchase_price"],
                    "purchase_type": lot["purchase_type"],
                    "sector": sectors.get(lot["ticker"], ""),
                    "status": status})
    return out


def handle_upload_statement(body, content_type):
    """Parse an uploaded statement PDF and return the preview: every
    lot it would insert, each flagged new / already-imported /
    already-in-db, plus the rows that need review and will NOT be
    written. The PDF is parsed from a temp file that is deleted before
    this returns; nothing is written to the DB."""
    try:
        filename, data = _parse_multipart(body, content_type)
    except ValueError as e:
        return {"ok": False, "error": "bad_upload", "message": str(e)}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"ok": False, "error": "too_large",
                "message": "That file is over 10 MB — not a statement PDF."}
    if not data.startswith(b"%PDF"):
        return {"ok": False, "error": "not_a_pdf",
                "message": "That file is not a PDF — pick the Fidelity "
                           "statement PDF."}
    ticker_names = None
    if DB_PATH.exists():
        try:
            _db = sqlite3.connect(DB_PATH)
            ticker_names = {r[0]: r[1] for r in _db.execute(
                "SELECT ticker, name FROM tickers")}
            _db.close()
        except sqlite3.Error:
            ticker_names = None
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        try:
            parsed = fidelity_pdf.parse_pdf(tmp.name, ticker_names)
        except FileNotFoundError:
            return {"ok": False, "error": "pdftotext_missing",
                    "message": "pdftotext is not installed on the machine "
                               "running this server (poppler-utils). The "
                               "statement cannot be read without it."}
        except Exception as e:
            return {"ok": False, "error": "parse_failed",
                    "message": f"The statement could not be parsed: {e}"[:200]}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    if not DB_PATH.exists():
        return {"ok": False, "error": "no_db",
                "message": "investments.db not found on this server."}
    db = sqlite3.connect(DB_PATH)
    try:
        lots = _classify_lots(db, parsed["lots"])
    finally:
        db.close()
    return {"ok": True,
            "statement_period": parsed["statement_period"],
            "filename": filename,
            "lots": lots,
            "to_insert": sum(1 for x in lots if x["status"] == "new"),
            "skipped": parsed["skipped"],
            "unhandled": parsed["unhandled"],
            "activity_sections": parsed["activity_sections"],
            "cash": parsed["cash"],
            "cash_note": parsed.get("cash_note"),
            "needs_review": parsed["needs_review"]}


def _valid_lot(raw):
    """A confirmed lot, validated before it may reach the DB: the
    confirm step only ever receives what the preview showed, but the
    server still checks every field rather than trusting the client."""
    if not isinstance(raw, dict):
        return None
    ticker = raw.get("ticker")
    date = raw.get("purchase_date")
    shares = raw.get("shares")
    price = raw.get("purchase_price")
    ptype = raw.get("purchase_type")
    if (not isinstance(ticker, str) or not TICKER_RE.match(ticker)
            or not isinstance(date, str) or not LOT_DATE_RE.match(date)
            or not isinstance(shares, (int, float)) or not shares > 0
            or not isinstance(price, (int, float)) or not price >= 0
            or not isinstance(ptype, str) or not ptype.strip()):
        return None
    return {"ticker": ticker, "purchase_date": date,
            "shares": float(shares), "purchase_price": float(price),
            "purchase_type": ptype.strip()}


CASH_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_cash(raw):
    """A confirmed cash position, validated before it may reach the
    DB: {balance, as_of} echoed back from the preview, or None when
    the statement had no readable cash balance."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return False
    balance = raw.get("balance")
    as_of = raw.get("as_of")
    if (not isinstance(balance, (int, float)) or not balance >= 0
            or not isinstance(as_of, str)
            or not CASH_DATE_RE.match(as_of)):
        return False
    return {"balance": float(balance), "as_of": as_of}


def handle_upload_confirm(body):
    """Insert exactly the confirmed lots and record the confirmed cash
    position. Backup first (DB-care rule), then fidelity_pdf.ingest —
    which re-checks idempotency, so a lot that landed between preview
    and confirm is skipped, never doubled. The write is verified row
    by row before reporting success. A confirm with zero lots is
    allowed when it carries a cash position (e.g. re-uploading a
    statement whose lots are already in the DB)."""
    period = body.get("statement_period")
    raw_lots = body.get("lots")
    if not isinstance(period, str) or not period:
        return {"ok": False, "error": "bad_confirm",
                "message": "Confirm needs the statement period from the preview."}
    if raw_lots is None:
        raw_lots = []
    if not isinstance(raw_lots, list):
        return {"ok": False, "error": "bad_confirm",
                "message": "Nothing selected to insert."}
    cash = _valid_cash(body.get("cash"))
    if cash is False:
        return {"ok": False, "error": "bad_confirm",
                "message": "The cash position failed validation — nothing "
                           "was written."}
    if not raw_lots and cash is None:
        return {"ok": False, "error": "bad_confirm",
                "message": "Nothing selected to insert."}
    lots = [_valid_lot(x) for x in raw_lots]
    if any(x is None for x in lots):
        return {"ok": False, "error": "bad_confirm",
                "message": "A confirmed lot failed validation — nothing "
                           "was written."}
    if not DB_PATH.exists():
        return {"ok": False, "error": "no_db",
                "message": "investments.db not found on this server."}
    backup = (str(DB_PATH) + ".bak-"
              + datetime.now(ET).strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(DB_PATH, backup)
    try:
        result = fidelity_pdf.ingest(
            str(DB_PATH), {"statement_period": period, "lots": lots,
                          "cash": cash})
    except Exception as e:
        return {"ok": False, "error": "ingest_failed",
                "message": f"The insert failed: {e}"[:200],
                "db_backup": backup}
    inserted = result.get("inserted") or []
    db = sqlite3.connect(DB_PATH)
    try:
        verified = [x for x in inserted if db.execute(
            "SELECT 1 FROM lots WHERE row_num=?",
            (x["row_num"],)).fetchone()]
        cash_ok = True
        if cash is not None:
            cash_ok = db.execute(
                "SELECT 1 FROM cash_positions WHERE statement_period=?"
                " AND ABS(balance - ?) < 0.01",
                (period, cash["balance"])).fetchone() is not None
    finally:
        db.close()
    if len(verified) != len(inserted) or not cash_ok:
        return {"ok": False, "error": "verify_failed",
                "message": "The insert reported success but not every lot "
                           "or the cash position could be found afterwards "
                           "— the backup is at "
                           f"{backup}. Nothing further was written.",
                "db_backup": backup}
    return {"ok": True,
            "statement_period": period,
            "inserted": len(verified),
            "inserted_tickers": [x["ticker"] for x in verified],
            "already_imported": len(result.get("already_imported") or []),
            "already_in_db": len(result.get("already_in_db") or []),
            "new_ticker_warnings": result.get("new_ticker_warnings") or [],
            "cash_recorded": result.get("cash_recorded"),
            "db_backup": backup}


# ---------------------------------------------------------------------------
# Consultation — chat with a Gemini model about the portfolio.
# Ported from apps-script/Code.gs consult_ (same model, same grounding,
# thinking off). The API key NEVER appears in this file or the repo: it
# comes from GEMINI_API_KEY in the environment (the backend .env on the
# machine that runs this server). Without it, the action returns
# { ok: false, error: 'not_configured' } and the view shows setup
# instructions instead of a chat.
# ---------------------------------------------------------------------------

CONSULT_MODEL = "gemini-3.8-flash"
CONSULT_MAX_TURNS = 10


def handle_consult(body):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {
            "ok": False,
            "error": "not_configured",
            "message": "Consultation is not configured yet: add a "
                       "GEMINI_API_KEY to the backend .env on the machine "
                       "running this server, then restart it.",
        }
    msgs = [m for m in (body.get("messages") or [])
            if isinstance(m, dict) and isinstance(m.get("text"), str)
            and m["text"].strip()
            and m.get("role") in ("user", "model")][-CONSULT_MAX_TURNS:]
    if not msgs:
        return {"ok": False, "error": "empty_conversation"}

    db = sqlite3.connect(DB_PATH)
    try:
        p = build_payload(db)
    finally:
        db.close()
    context = {
        "as_of": p["as_of"],
        "market_as_of": p["market_as_of"],
        "total_value": p["total_value"],
        "total_cost": p["total_cost"],
        "total_gain": p["total_gain"],
        "total_gain_pct": p["total_gain_pct"],
        "cost_basis": p["cost_basis"],
        "total_dividend_reinvested": p["total_dividend_reinvested"],
        "sectors": p["sectors"],
        "buy_candidates": p["buy_candidates"],
        "positions": [{
            "ticker": x["ticker"], "name": x["name"],
            "sector": x["sector"], "shares": x["shares"],
            "price": x["price"], "value": x["value"], "cost": x["cost"],
            "gain": x["gain"], "gain_pct": x["gain_pct"],
            "day_change_pct": x["day_change_pct"],
            "week_change_pct": x["week_change_pct"],
            "graham": x["graham"], "below_graham": x["below_graham"],
        } for x in p["positions"]],
    }
    system = (
        "You are the consultation assistant built into a personal "
        "Investment Tracker app, discussing his own portfolio with him. "
        "The JSON below is his live portfolio, aggregated from his local "
        "investments database (cost basis = cash purchases only; "
        "reinvested dividends excluded from cost but their shares count "
        "in value). Ground every figure in that data; if something is "
        "not in the data, say so plainly instead of inventing it. The "
        "Graham number is sqrt(22.5 x trailing EPS x book value); "
        "holdings priced below it are flagged as buy candidates by the "
        "app. Explain concepts, compare holdings, and talk through "
        "scenarios he raises. You are not a licensed financial advisor: "
        "treat this as educational discussion, not personalized advice, "
        "and do not promise returns. Keep answers focused and readable "
        "in a chat pane: short paragraphs or brief lists, no tables. "
        "Portfolio JSON: " + json.dumps(context))
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + CONSULT_MODEL + ":generateContent?key=" + key,
        data=json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": m["role"],
                          "parts": [{"text": m["text"]}]} for m in msgs],
            # Thinking is OFF (thinkingBudget: 0): a consultation answer
            # should not burn thinking tokens — or the wait that comes
            # with them — before it starts. Jason's rule, 2026-11-14.
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        }).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            status = resp.status
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read())
        except Exception:
            data = {}
        return {"ok": False, "error": "gemini_error", "status": e.code,
                "message": ((data.get("error") or {}).get("message")
                            or "The model request failed.")}
    except Exception as e:
        return {"ok": False, "error": "gemini_error",
                "message": f"The model request failed: {e}"[:200]}
    if status != 200:
        return {"ok": False, "error": "gemini_error", "status": status,
                "message": ((data.get("error") or {}).get("message")
                            or "The model request failed.")}
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}
             ).get("parts") or []
    text = "".join(x.get("text") or "" for x in parts)
    if not text:
        return {"ok": False, "error": "empty_reply"}
    return {"ok": True, "reply": text}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DIST), **kw)

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload-statement":
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json(200, {"ok": False, "error": "bad_upload"})
            if length > MAX_UPLOAD_BYTES + 4096:
                return self._json(200, {"ok": False, "error": "too_large",
                                        "message": "That file is over 10 MB."})
            return self._json(200, handle_upload_statement(
                self.rfile.read(length),
                self.headers.get("Content-Type")))
        if parsed.path == "/api/upload-statement/confirm":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return self._json(200, {"ok": False, "error": "bad_json"})
            return self._json(200, handle_upload_confirm(body))
        if parsed.path == "/api/consult":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                return self._json(200, {"ok": False, "error": "bad_json"})
            if body.get("action") != "consult":
                return self._json(200, {"ok": False,
                                        "error": "unknown_action"})
            return self._json(200, handle_consult(body))
        return self._json(404, {"ok": False, "error": "unknown_path"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/portfolio":
            if not DB_PATH.exists():
                return self._json(500, {
                    "ok": False,
                    "error": "investments.db not found — run backend/sync_db.py"})
            db = sqlite3.connect(DB_PATH)
            try:
                return self._json(200, build_payload(db))
            finally:
                db.close()
        if parsed.path.startswith("/api/"):
            return self._json(404, {"ok": False, "error": "unknown_path"})
        if (not Path(DIST, parsed.path.lstrip("/")).exists()
                and "." not in Path(parsed.path).name):
            self.path = "/index.html"
        super().do_GET()


if __name__ == "__main__":
    _load_env()
    port = int(os.environ.get("INVESTMENT_TRACKER_PORT", "8768"))
    host = os.environ.get("INVESTMENT_TRACKER_HOST", "0.0.0.0")
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    print(f"Investment Tracker: http://{host}:{port}", flush=True)
    print(f"Started with: python3 {' '.join(sys.argv)}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
