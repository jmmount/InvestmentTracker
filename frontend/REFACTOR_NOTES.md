# Investment Tracker — SQLite refactor notes

Built Mon Nov 16, 2026 (evening), for Jason's morning review.
**Nothing is cut over.** The live app still reads from the Apps Script
endpoint; the sheet, snapshot.py, the 4:30 AM cron and the briefing
pipeline are untouched. Everything below is additive, in `backend/`.

## What was added

| File | What it is |
|---|---|
| `backend/investments.db` | The production SQLite store (created by the sync; ~2,900 rows total). |
| `backend/sync_db.py` | Refreshes the DB from its sources. Idempotent — safe to re-run (`--skip-history` skips the yfinance pull). |
| `backend/server.py` | Stdlib-only local server, port **8768**, binds 127.0.0.1. Serves `dist/` and the portfolio API. Banner on startup, same pattern as the other apps. |

## The store

Tables (sheet-derived tables are rebuilt in one transaction per sync;
snapshot/history rows are upserted):

- `lots` — all 88 CleanData lots, in sheet order (timestamp, ticker,
  purchase date, shares, purchase price, sector, purchase type).
- `market_data` — the 12 MarketData rows (price, prev close, day/week
  change %, Graham + note, close date, updated-at).
- `current_value_prices` — CurrentValue pivot prices, kept as the
  fallback exactly as Code.gs uses them (MarketData wins).
- `tickers` — derived meta: ticker, name (from MarketData), sector
  (from lots), is_fund (from the MarketData Graham note).
- `portfolio_totals` / `portfolio_snapshots` — the 16 daily snapshots
  from `~/workspace/investments/snapshots/*.json` (188 position rows),
  same schema as the Nov 16 test build in `~/workspace/databases/`.
- `price_history` — weekly closes since 2023-01-01 via yfinance,
  2,432 rows (202–203 per ticker). Best effort: a failed ticker keeps
  its existing rows and the sync still succeeds.
- `sync_meta` — last sync time + source description.

Sync sources are **read-only**: the sheet via `hatch_gws_cli`
(CleanData, MarketData, CurrentValue — the Key tab is never read, the
sheet is never written), the local snapshot JSONs, and yfinance.

## The API contract — unchanged

`GET /api/portfolio` returns the same JSON shape as the Apps Script
`doGet`, computed from the DB by code that mirrors `buildPayload_` /
`aggregateLots_` line for line, including:

- **Cash-only cost basis** — `Dividends` lots add shares and value,
  never cost; any other lot type counts as cost (same as Code.gs).
- JavaScript `Math.round` semantics for every rounded field.
- MarketData price wins, CurrentValue price is the fallback,
  `market_as_of` from the MarketData close date, positions sorted by
  value descending, `meta` derived from the lots (tickers/sectors
  sorted, purchase types in first-seen order).
- `GET /api/portfolio?view=meta` → `{ meta: {...} }`, mirroring
  `doGet?view=meta`.

One deliberate difference: the payload's `source` field is
`"sqlite-local"` instead of `"apps-script-read"`, so the data's origin
is never ambiguous. Nothing in the frontend reads that field.

## Verified (Nov 16, 2026)

Against the Fri Nov 13 close data in MarketData:

- `total_value` **$6,211.53**, `total_cost` **$4,956.29**,
  `total_gain` **+$1,255.24 (+25.33%)**,
  `total_dividend_reinvested` **$139.54** — all exact.
- All 12 tickers present; buy candidates BAC + PR; sector totals match
  `latest.json` to the cent.
- Per-position diff vs `latest.json`: every numeric field identical.
  The only differences are 6 company *names* — the DB serves the
  MarketData names (e.g. "Fidelity ZERO International Index") where
  snapshot.py's yfinance names are truncated ("Fidelity International
  Index Fu"). Code.gs serves the MarketData names too, so the DB is
  faithful to the endpoint contract.
- Re-running the sync reproduces identical counts; DB integrity ok.

## What still lives in the sheet (unchanged)

- **Purchase-ticket writes** — still copy/download mode in the app
  (`TICKET_POST_ENABLED=false`); the future write phase (Apps Script
  `doPost` appending to RawData, after the RawData → CleanData flow is
  pinned down) is untouched by this refactor.
- **The Consultation view** — still posts to the Apps Script endpoint
  (Gemini key stays in Script Properties, server-side). The local
  server has no POST endpoints.
- **Jason's `fetchTickersLongFormat()`** — his own script in the
  workbook's bound project; untouched, still sheet-side.
- **MarketData population** — still `populate_market_data.py` writing
  to the sheet; the sync reads that tab. The 4:30 AM snapshot cron and
  the morning briefing still run off the sheet + snapshot.py exactly
  as before.

## Cutover decisions for Jason

1. **Point the frontend at the local server?** Set
   `VITE_SHEET_ENDPOINT=http://localhost:8768/api/portfolio` and
   rebuild — the Portfolio and Purchase Ticket (meta) views then run
   entirely off the DB. The Consultation view would still need the
   Apps Script URL, which is currently the same variable — so either
   the consult endpoint gets its own config value, or Consultation
   keeps using the sheet endpoint while reads go local. (Small change;
   not done yet, awaiting the call.)
2. **Sync cadence** — run `sync_db.py` by hand for now. Wiring it into
   a schedule (e.g. alongside the 4:30 AM snapshot, or after
   `populate_market_data.py`) is a separate decision; no cron was
   touched.
3. **Does the sheet stay the system of record for lots?** In this
   build the DB is a read replica: new purchases still land in the
   sheet first (via the Google Form / ticket flow) and flow into the
   DB on the next sync. Making the DB primary would mean building the
   ticket write path against SQLite instead of RawData — a bigger
   step, deliberately not taken here.
4. **Git** — `backend/` is new and untracked in this local copy;
   nothing was pushed. If it goes to GitHub later, `investments.db`
   itself should stay out of the repo (it's a generated replica —
   `sync_db.py` rebuilds it), same as the Workout Guide's
   `workouts.db`.

## Cutover — sheet -> SQLite (Nov 24-25, 2026, branch feature/db-backend)

The decisions above are now implemented; the sheet is retired as the
data source. See the PR body for the full verification.

- `backend/server.py` — binds 0.0.0.0, serves dist/ + /api/portfolio
  (total_cost pinned to Jason's settled $4,956.29 via the frozen +$0.12
  in sync_meta) and POST /api/consult (Gemini, key from GEMINI_API_KEY).
- `backend/fidelity_pdf.py` — monthly statement PDF -> lots (idempotent).
  Verified on the Oct 2026 statement: 3 reinvestment lots matched the
  seed rows exactly.
- `~/workspace/investments/refresh_db.py` — twice-daily refresh, no
  sheet (replaces snapshot.py + populate_market_data.py +
  update_app_data.py; those files are retired, do not run them).
- Frontend reads `/api/portfolio` only; the baked-in seed and its merge
  are deleted. `apps-script/Code.gs` stays in the repo as the record of
  the old read path; nothing calls it any more.
- `backend/sync_db.py` is retired with the sheet (it rebuilt the DB
  from CleanData/MarketData). Do not run it.

## Purchase Ticket removed, statement upload replaces it (Nov 25, 2026, branch feature/fidelity-upload-replaces-ticket)

- The Purchase Ticket view is gone (frontend form, nav tab,
  `TICKET_POST_ENABLED` gating, the ticket dropdown fallbacks in
  `src/config.js`, the `?view=meta` endpoint and the `meta` block in
  the portfolio payload). The ticket write phase it was waiting on
  will not be built — new lots come from the statement upload instead.
- New flow: **Upload statement** tab → pick a Fidelity statement PDF
  → preview screen lists exactly what would be written (ticker, date,
  shares, price, type per lot, plus needs-review rows flagged
  separately) → confirm inserts only the checked lots. Backup of
  `investments.db` first, row-by-row verification after, via
  `POST /api/upload-statement` and `/api/upload-statement/confirm`
  in `backend/server.py`, reusing `backend/fidelity_pdf.py`'s parser
  and idempotency. The PDF is parsed from a temp file and deleted;
  it is never stored.
- One leftover the snapshot-push flow cannot do: `src/views/
  PurchaseTicket.jsx` still exists on main (push-files cannot delete
  files). It is unreferenced — nothing imports it. Delete it in the
  GitHub web UI after merging this PR.
