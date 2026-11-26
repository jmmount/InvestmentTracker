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
  history, plus a `cash` block (`{ balance, statement_period, as_of }`
  from the latest recorded statement, or `null`) — the holdings total
  stays holdings-only; cash is a separate line, never folded in. Cost
  basis is cash lots only; reinvested-dividend lots
  add shares/value, never cost. Total cost carries the frozen +$0.12
  adjustment on the Nov 2026 seed lots (raw cash sum $4,956.17 vs
  Jason's settled $4,956.29), read from `sync_meta`.
- `POST /api/upload-statement` — multipart Fidelity statement PDF;
  returns the preview (lots to insert with per-lot status, the core
  cash balance that would be recorded, rows that
  need review). Writes nothing; the PDF is parsed from a temp file
  that is deleted right after parsing. Needs `pdftotext` (poppler)
  on the machine running the server.
- `POST /api/upload-statement/confirm` — `{ statement_period, lots, cash }`;
  backs up `investments.db`, inserts exactly the confirmed lots via
  `fidelity_pdf.ingest` (idempotent) and records the cash balance in
  `cash_positions` (one row per statement period, re-uploads replace
  it), verifies the write row by row. A confirm with zero lots is
  allowed when it carries a cash position.
- `POST /api/consult` — `{ action: "consult", messages: [...] }`.
  Gemini chat grounded in the live payload (`gemini-3.8-flash`,
  thinking off). Needs `GEMINI_API_KEY` in the environment; without it
  the action answers `{ ok: false, error: "not_configured" }`.
- `GET /api/watchlist` — the watchlist: one item per ticker (name from
  the `tickers` table first, then EDGAR, sector from the `tickers`
  table, Graham number from `market_data`, the EDGAR fundamentals
  with their histories, data-quality notes, per-card EDGAR facts URL)
  plus the source citation block. No EDGAR calls on read — the metrics
  are cached in `watchlist_metrics`.
- `POST /api/watchlist` — `{ ticker }`; resolves the ticker to its CIK
  via the SEC tickers file, fetches its EDGAR companyfacts, computes
  the metrics (`backend/edgar.py`) and stores them. Idempotent:
  re-adding returns the existing item. Unknown ticker →
  `{ ok: false, error: "unknown_ticker" }`.
- `POST /api/watchlist/refresh` — `{ ticker }`; re-fetches EDGAR and
  recomputes the stored metrics for a watched ticker.
- `DELETE /api/watchlist?ticker=X` — removes the ticker and its cached
  metrics.

## Watchlist (SEC EDGAR fundamentals)

`backend/edgar.py` (stdlib only) is the EDGAR client: the SEC tickers
file maps ticker → CIK (cached a day, never hardcoded), then
`data.sec.gov/api/xbrl/companyfacts/CIK##########.json` supplies the
XBRL facts. Every request sends a User-Agent header identifying the
app operator and stays well under the SEC's 10 requests/second limit.
The metrics: current ratio (`AssetsCurrent` /
`LiabilitiesCurrent`), debt/equity (total debt =
`DebtCurrent` + `LongTermDebt` + `LongTermDebtCurrent`, over
`StockholdersEquity`), free cash flow
(`NetCashProvidedByUsedInOperatingActivities` −
`PaymentsToAcquirePropertyPlantAndEquipment`), 10-year revenue CAGR
(`Revenues`, latest year vs 10 years earlier) and quarterly revenue
growth YoY for the last four quarters only (`Revenues`, same quarter
prior year), return on equity (`NetIncomeLoss` / average
`StockholdersEquity`), R&D as share of revenue
(`ResearchAndDevelopmentExpense` / `Revenues`), net margin
(`NetIncomeLoss` / `Revenues`). Revenue falls back to
`RevenueFromContractWithCustomerExcludingAssessedTax` where a filer
does not tag plain `Revenues`. Every series is keyed by the year of
the `end` date, never by `fy` — `fy` is the filing year, so a 2015
10-K carries its 2013–2015 comparatives all with fy=2015; keying by
`fy` mislabels every series by up to two years. Restatements resolve
to the latest-filed 10-K / 10-Q per period. A Q2/Q3 10-Q usually tags
both YTD cumulative and single-quarter revenue — the tagged
single-quarter entry wins, and a cumulative-only filer is differenced
within the year (Q2 = H1 − Q1, Q3 = 9M − H1) before YoY is computed.
Known limit: short-term debt (`DebtCurrent`) is tagged only
sporadically (Alphabet: FY2014–16 only), so the debt total uses what
is tagged and the card says so. EDGAR has no prices and no dividend
history by period — the Graham number on each card comes from the
tracker's own price feed (`market_data`, yfinance), cited separately.
Sector for a ticker that is not already a holding is filled in by the
twice-daily refresh (see below), which upserts the `tickers` row from
yfinance; until then the card shows no sector chip. Name resolution:
`tickers` table first (same name the portfolio card shows), then
EDGAR's `entityName`, then the SEC tickers-file title — EDGAR's
entityName can be wrong for a filer (BAC's CIK reports "BofA Finance
LLC", not Bank of America).

## Refresh (twice daily, on the VM)

`~/workspace/investments/refresh_db.py` reads the lots, fetches prices /
Graham / names from yfinance, and writes `market_data`,
`portfolio_totals` and `portfolio_snapshots` for the prices' trading
date, plus `latest.json` and the briefing charts. It never touches the
lots. It also refreshes market data for watchlist tickers (price,
Graham, name/sector into `market_data` / `tickers`) in a guarded
step after the holdings commit, so a watchlist fetch failure can
never fail the holdings refresh. The sheet-era scripts (`snapshot.py`,
`populate_market_data.py`, `update_app_data.py`) are retired — do not run them.

## New lots: Fidelity statement PDF

```bash
python3 backend/fidelity_pdf.py statement.pdf [--db PATH] [--dry-run]
```

Parses the statement's dividend-reinvestment rows into lots
(idempotent — re-running a statement inserts nothing; a backup copy of
the DB is taken before any write). Cash buys from a "Securities Bought
& Sold" section become Cash lots (sales are reported for review, never
auto-ingested); that parser is written defensively and is unverified
against a real buy, since no statement seen so far contains the
section. Ticker names resolve from the statement's Holdings section
first, then from the DB's `tickers` names — no hardcoded alias map
remains except the core-fund classification (SPAXX is never a lot).
The statement's core cash balance is recorded per period in
`cash_positions` (no backfill — recording starts with the next upload).
See the module docstring for the layout it expects and what it reports
as needing review. The PDF itself
stays where Jason put it; never copy it into the repo. The Upload
statement tab in the app drives this same parser through
`POST /api/upload-statement` (preview) and
`POST /api/upload-statement/confirm` (insert) — the CLI is the same
flow without the preview screen.
