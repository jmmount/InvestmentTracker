# Investment Tracker — Frontend

A React single-page app for Jason's investments. The **Google Sheets
workbook "Investments (Responses)" stays the backend data source**; this is
the frontend. Two views:

- **Portfolio** — every holding highlighted on its own card (price, day/week
  movement, shares, value, cost, signed gain/loss, Graham number, and a
  "Below Graham · buy candidate" highlight), plus visualizations: an
  allocation-by-sector donut and a signed gain/loss bar chart per holding.
- **Purchase Ticket** — mimics the Google Form purchase ticket. Fields, in
  the workbook's column order: Timestamp (automatic), Ticker, Date,
  Number of Shares, Purchase Price, Sector, Purchase Type (Cash / Dividends).
  Ticker/Sector options mirror the workbook's current values; a new ticker
  can be entered via "Other…". Output matches RawData/CleanData, so the
  daily snapshot (`snapshot.py`) keeps working unchanged.

## Data

`src/data-portfolio.js` is the data layer, with two sources:

- **Live read (when configured)** — the Portfolio view fetches portfolio
  JSON from the Apps Script web app bound to the workbook
  (`apps-script/Code.gs`, `doGet`): holdings, shares and cost aggregated
  from the CleanData lots (cost = cash lots only; reinvested dividends add
  shares/value, not cost), prices from the workbook's own CurrentValue
  pivot.
- **Seed snapshot (fallback)** — a baked-in export of `snapshot.py`'s
  `latest.json` (see its `as_of`). Used when no endpoint is configured or
  the fetch fails, so the page never goes blank.

The payload also carries a `meta` block — the Purchase Ticket's dropdown
values (tickers, sectors, purchase types) **derived by the script from
CleanData's distinct values**, never hardcoded. A ticker or sector that
appears in the lots shows up in the form automatically. The lists in
`src/config.js` are only the offline fallback for when the endpoint is not
configured or unreachable.

Prices, Graham numbers and day/week moves come from the workbook's
**MarketData tab**, populated by the Python functions in
`~/workspace/investments/market_data/` — one file per function
(`graham.py`: `get_graham_number`, via yfinance trailing EPS and book
value; `prices.py`: `get_price_snapshot`, latest/prev/week closes), each
runnable standalone for troubleshooting, plus `populate_market_data.py`,
which reads the held tickers from CleanData and writes the tab. Graham's
formula is `sqrt(22.5 × EPS × BVPS)`; mutual funds get no Graham number.
The endpoint prefers MarketData prices and falls back to the CurrentValue
pivot for a ticker with no MarketData row yet; the seed snapshot remains
the final fallback for any field the workbook cannot supply.

## Credentials — there are none in this repo

- The Apps Script runs **as the workbook owner**; Google holds the access
  server-side. No API key, service account or OAuth secret exists in the
  frontend or in `Code.gs` — by design, and never add one.
- The web app URL is the only capability the frontend holds. It is read
  from `VITE_SHEET_ENDPOINT` in a **gitignored `.env` file** (copy
  `.env.example`), so the URL never enters the source or git history.
- Revocation = redeploy the web app (a new URL) and update `.env`.

## Run it

```bash
cp .env.example .env   # then paste the web app URL into .env
npm install
npm run dev      # local dev server (Vite)
npm run build    # production build into dist/
```

## Deploying the read endpoint (one time, ~2 minutes)

In the "Investments (Responses)" workbook:

1. **Extensions → Apps Script**, delete any placeholder code, and paste in
   the whole of `apps-script/Code.gs`.
2. **Deploy → New deployment → Web app**, with **Execute as: Me** and
   **Who has access: Anyone**. Approve the authorization prompt (it is your
   own script reading your own workbook).
3. Copy the web app URL into `.env` as `VITE_SHEET_ENDPOINT` and restart
   `npm run dev`. The Portfolio footnote switches to "Live from the
   Investments workbook…" when the fetch succeeds.

To update the script later: paste the new code, then **Deploy → Manage
deployments → edit → New version** — the URL stays the same.

Known limits of the read phase: the MarketData tab is only as fresh as
its last `populate_market_data.py` run (prices are the last close at that
moment); a ticker bought since then shows with CurrentValue/seed fallback
values until the next populate run.

## Consultation view (chat with a model about the portfolio)

The third tab chats with a Gemini model about the portfolio. The browser
talks only to the Apps Script endpoint; the script grounds the model in
the live portfolio payload and calls Gemini server-side. **The API key
lives only in the script's Script Properties — never in this repo, the
frontend, or the script source.**

One-time setup, in the Apps Script editor:

1. Create a **dedicated** AI Studio API key for this app at
   aistudio.google.com/apikey (do not reuse other keys — e.g. a teaching
   key — here).
2. **Project Settings (gear) → Script Properties → Add script property:**
   name `GEMINI_API_KEY`, value = the key.
3. Deploy the change: **Deploy → Manage deployments → edit → New
   version** (URL unchanged).

Until the property exists, the endpoint answers
`{ ok: false, error: 'not_configured' }` and the view shows setup guidance
instead of failing. The model is the `CONSULT_MODEL` constant at the top
of the consultation section in `Code.gs` (`gemini-2.5-flash`).

## Getting a submitted ticket into the workbook

**Copy/download mode (the only mode for now)** — each ticket is listed
under "Tickets this session" with a **Copy row** button (a tab-separated
row in workbook column order, ready to paste into the RawData tab) or
**Download CSV** for the whole session.

Ticket POSTs are deliberately disabled (`TICKET_POST_ENABLED = false` in
`src/config.js`) even when the read URL is configured: the endpoint's
`doPost` answers only the `consult` action and rejects everything else.
The write phase — a ticket action in the Apps Script guarded by a write
token typed into the app —
is a separate, later step. When it lands, the app will POST each ticket as
JSON with keys `timestamp, ticker, date, shares, price, sector,
purchaseType`.
