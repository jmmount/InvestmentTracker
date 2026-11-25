# Investment Tracker — Frontend

A React single-page app for Jason's investments. The **local SQLite
store (`backend/investments.db`) is the backend data source**; this is
the frontend. Three views:

- **Portfolio** — every holding highlighted on its own card (price, day/week
  movement, shares, value, cost, signed gain/loss, Graham number, and a
  "Below Graham · buy candidate" highlight), plus visualizations: an
  allocation-by-sector donut and a signed gain/loss bar chart per holding.
- **Purchase Ticket** — mimics the Google Form purchase ticket. Fields, in
  ticket column order: Timestamp (automatic), Ticker, Date,
  Number of Shares, Purchase Price, Sector, Purchase Type (Cash / Dividends).
  Ticker/Sector options mirror the database's current values; a new ticker
  can be entered via "Other…".
- **Consultation** — chat with a Gemini model about the portfolio (see
  below).

## Data

`src/data-portfolio.js` is the data layer, with ONE source: the local
backend (`backend/server.py`), which computes the portfolio JSON from
`investments.db` — holdings, shares and cost aggregated from the lots
table (cost = cash lots only; reinvested dividends add shares/value,
not cost), prices/Graham/day-week moves from yfinance. There is no
baked-in seed and no fallback: if the backend does not answer, the
Portfolio view says so instead of showing stale numbers.

The payload also carries a `meta` block — the Purchase Ticket's dropdown
values (tickers, sectors, purchase types) **derived by the backend from
the lots table's distinct values**, never hardcoded. A ticker or sector
that appears in the lots shows up in the form automatically. The lists in
`src/config.js` are only the offline fallback for when the backend is not
reachable.

Prices, Graham numbers and day/week moves come from yfinance via the
Python functions in `~/workspace/investments/market_data/` — one file per
function (`graham.py`: `get_graham_number`, trailing EPS and book
value; `prices.py`: `get_price_snapshot`, latest/prev/week closes;
`names.py`: `get_company_name`), each runnable standalone for
troubleshooting. Graham's formula is `sqrt(22.5 × EPS × BVPS)`; mutual
funds get no Graham number. The twice-daily refresh
(`~/workspace/investments/refresh_db.py`) writes the fresh market data
into the database; the backend serves whatever the last refresh wrote.

## Credentials — there are none in this repo

- The backend reads the database file on disk; no Google credentials
  exist anywhere in this app, by design, and never add one.
- The Gemini API key for Consultation lives only in the backend's
  environment (see below) — never in this repo, the frontend, or the
  backend source.
- `VITE_API_URL` (optional, same-origin by default) is not a secret; it
  is just an origin. It still lives in a gitignored `.env` when set, so
  a local setup never leaks into git history.

## Run it

```bash
npm install
npm run dev      # local dev server (Vite) — point it at a backend with VITE_API_URL
npm run build    # production build into dist/
```

The backend serves the built frontend and the API from one port:

```bash
python3 backend/server.py            # serves dist/ + /api/* on :8768
python3 backend/server.py --port 8791
```

No `.env` is needed for the app itself. The backend reads
`GEMINI_API_KEY` from its environment only for Consultation; without it
the view shows setup guidance instead of a chat.

## Consultation view (chat with a model about the portfolio)

The third tab chats with a Gemini model about the portfolio. The browser
talks only to the local backend (POST `/api/consult`); the backend
grounds the model in the live portfolio payload and calls Gemini
server-side. **The API key lives only in the backend's environment —
never in this repo, the frontend, or the backend source.**

One-time setup, on the machine that runs the backend:

1. Create a **dedicated** AI Studio API key for this app at
   aistudio.google.com/apikey (do not reuse other keys — e.g. a teaching
   key — here).
2. Add it to the backend's environment — e.g. a gitignored
   `backend/.env` with `GEMINI_API_KEY=...`, exported before starting
   the server (or set it in the service's environment on the host).
3. Restart the backend.

Until the key exists, the backend answers
`{ ok: false, error: 'not_configured' }` and the view shows setup guidance
instead of failing. The model is `gemini-3.8-flash` (`CONSULT_MODEL` in
`backend/server.py`), with thinking off.

## Getting a submitted ticket into the database

**Copy/download mode (the only mode for now)** — each ticket is listed
under "Tickets this session" with a **Copy row** button (a tab-separated
row in ticket column order) or **Download CSV** for the whole session.

Ticket POSTs are deliberately disabled (`TICKET_POST_ENABLED = false` in
`src/config.js`). The write phase — a ticket action in the backend that
appends a lot to `investments.db` — is a separate, later step. When it
lands, the app will POST each ticket as JSON with keys
`timestamp, ticker, date, shares, price, sector, purchaseType`.

## Lots: where they come from

New lots arrive from the monthly Fidelity statement PDF, not from a
form: `python3 backend/fidelity_pdf.py statement.pdf` parses the
statement's dividend-reinvestment rows and upserts them into the lots
table (idempotent — re-running a statement inserts nothing). See the
module's docstring for the layout it expects and what it cannot parse
yet (cash buys/sales need a real example first). The old Google Sheet
and its Apps Script read endpoint are retired; `apps-script/Code.gs`
remains in the repo as the record of the old read path.
