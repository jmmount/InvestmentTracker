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

`src/data-portfolio.js` is the data layer. For now it holds a baked-in
snapshot exported from `snapshot.py`'s `latest.json` (see its `as_of`).
That module is the single seam where the live spreadsheet connection plugs
in later: swap the static export for a fetch of the same shape and the
views do not change.

## Run it

```bash
npm install
npm run dev      # local dev server (Vite)
npm run build    # production build into dist/
```

## Getting a submitted ticket into the workbook

Set in `src/config.js`:

1. **Copy/download mode (default, `SHEET_ENDPOINT = ""`)** — each ticket is
   listed under "Tickets this session" with a **Copy row** button (a
   tab-separated row in workbook column order, ready to paste into the
   RawData tab) or **Download CSV** for the whole session.
2. **Endpoint mode** — set `SHEET_ENDPOINT` to a Google Apps Script web app
   URL (or any HTTPS endpoint) that appends a row to the workbook; the app
   POSTs each ticket as JSON with keys `timestamp, ticker, date, shares,
   price, sector, purchaseType`. (The Apps Script side is a small
   follow-up.)
