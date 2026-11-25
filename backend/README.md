# Investment Tracker — Backend

Stdlib-only Python. Serves the built frontend (`../dist`) and the
portfolio API from `investments.db` — no sheet, no Google credentials.

## Run

```bash
python3 backend/server.py              # :8768, binds 0.0.0.0
python3 backend/server.py --port 8791
INVESTMENT_TRACKER_HOST=127.0.0.1 python3 backend/server.py
```

`investments.db` lives next to `server.py` and is **not in git** (it is
rebuilt by the refresh; see below). The server reads it on every
request, so a refresh shows up on the next page load — no restart.

## Endpoints

- `GET /api/portfolio` — the portfolio JSON (same shape the old Apps
  Script `doGet` returned): totals, positions, sectors, buy candidates,
  history. Cost basis is cash lots only; reinvested-dividend lots
  add shares/value, never cost. Total cost carries the frozen +$0.12
  adjustment on the Nov 2026 seed lots (raw cash sum $4,956.17 vs
  Jason's settled $4,956.29), read from `sync_meta`.
- `POST /api/upload-statement` — multipart Fidelity statement PDF;
  returns the preview (lots to insert with per-lot status, rows that
  need review). Writes nothing; the PDF is parsed from a temp file
  that is deleted right after parsing. Needs `pdftotext` (poppler)
  on the machine running the server.
- `POST /api/upload-statement/confirm` — `{ statement_period, lots }`;
  backs up `investments.db`, inserts exactly the confirmed lots via
  `fidelity_pdf.ingest` (idempotent), verifies the write row by row.
- `POST /api/consult` — `{ action: "consult", messages: [...] }`.
  Gemini chat grounded in the live payload (`gemini-3.8-flash`,
  thinking off). Needs `GEMINI_API_KEY` in the environment; without it
  the action answers `{ ok: false, error: "not_configured" }`.

## Refresh (twice daily, on the VM)

`~/workspace/investments/refresh_db.py` reads the lots, fetches prices /
Graham / names from yfinance, and writes `market_data`,
`portfolio_totals` and `portfolio_snapshots` for the prices' trading
date, plus `latest.json` and the briefing charts. It never touches the
lots. The sheet-era scripts (`snapshot.py`, `populate_market_data.py`,
`update_app_data.py`) are retired — do not run them.

## New lots: Fidelity statement PDF

```bash
python3 backend/fidelity_pdf.py statement.pdf [--db PATH] [--dry-run]
```

Parses the statement's dividend-reinvestment rows into lots
(idempotent — re-running a statement inserts nothing; a backup copy of
the DB is taken before any write). See the module docstring for the
layout it expects and what it reports as needing review. The PDF itself
stays where Jason put it; never copy it into the repo. The Upload
statement tab in the app drives this same parser through
`POST /api/upload-statement` (preview) and
`POST /api/upload-statement/confirm` (insert) — the CLI is the same
flow without the preview screen.
