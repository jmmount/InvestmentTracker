# Analysis View — suggestions (Sat Nov 14, 2026)

> Note (Nov 25, 2026): the Purchase Ticket was removed and replaced
> by the Fidelity statement PDF upload, so item 4's "promote to
> ticket" is superseded — a future promote action would have nowhere
> to jump to, and the only write path is now the statement upload.

A fourth view for stocks you do NOT own: a watchlist you can evaluate with
the same yardsticks you apply to your holdings, before any ticket exists.

## Core (the smallest useful version)

1. **Watchlist tab in the workbook.** You type tickers into a `Watchlist`
   tab (ticker + optional note). That tab is the only input — nothing
   hardcoded, same rule as everything else. The app reads it the same way
   it reads CleanData.
2. **Analysis cards, same shape as Portfolio cards.** Per prospect: name,
   sector, price, signed day/week change, Graham number — all from a
   `WatchlistData` tab populated by a script reusing the exact functions
   MarketData already uses (names, prices, Graham). No new data machinery.
3. **Distance from Graham, ranked.** Each card shows price vs Graham as a
   signed %; the list sorts cheapest-relative-to-Graham first. Your buy
   rule (price < Graham) becomes a traffic light: below = candidate,
   within 10% above = close, above = pass for now.
4. **Promote to ticket.** One tap on a card jumps to the Purchase Ticket
   with the ticker pre-filled. Analysis ends where the ticket begins.

## The stability screen — fundamentals via yfinance (Jason's requirement)

Graham says cheap; this panel says *sound*. All of it comes from
yfinance — the `info` snapshot plus the annual financial statements
(income statement, balance sheet, cash flow) — fetched per watchlist
ticker by new single-purpose functions alongside the existing ones
(e.g. `fundamentals.py`), with the ratios below calculated in the
populate script, never hardcoded.

5. **Debt load.** Total debt, cash, and *net debt* (debt minus cash);
   debt-to-equity; and interest coverage (operating income ÷ interest
   expense) — can the business carry what it owes?
6. **Free cash flow.** FCF (operating cash flow minus capex, from the
   cash-flow statement), FCF per share, and *FCF yield* (FCF ÷ market
   cap) — cash generation priced against what you'd pay.
7. **Profit margins.** Gross, operating, and net margins, with the last
   few years side by side — a stable business holds its margins;
   a shrinking trend is the tell.
8. **Dividend yield and DEEP history.** Current yield, payout ratio,
   and whether free cash flow covers the dividend (dividends paid ÷
   FCF) — plus the long record from the yfinance dividend series,
   which reaches back decades for established payers (verified
   2026-11-14: KO payments to 1962, BAC to 1986, NVO to 1982; V to
   its 2008 IPO). Calculations over that depth: consecutive-payment
   streak, 5- and 10-year dividend growth, and cut history — did it
   hold or raise through 2020 and 2008-09? That is the stability
   evidence, and yfinance alone covers it; no second source needed.
   The only thin cases are companies that simply have not paid for
   long — the history is short because the record is.
9. **Supporting cast.** Return on equity, current ratio (short-term
   cushion), revenue and earnings growth, beta — the rest of the
   stability picture, all standard yfinance fields.
10. **Stability read at a glance.** Each metric lands as a plain value
    plus a small trend (improving / flat / worsening over the statement
    years) — no scores you can't audit; the raw numbers stay visible.

## Context the Portfolio view can't give you

11. **Sector fit.** Each prospect shows what its sector would do to your
    mix — e.g. "Energy is 8% of your portfolio; PR is your only energy
    name" — so a prospect that fills a gap reads differently from one
    that stacks onto your biggest sector.
12. **Graham inputs, shown.** EPS and book value behind each Graham
    number. You've seen the number shift between runs because Yahoo
    refreshes those inputs — showing them makes the number auditable
    instead of magic.
13. **Price history sparkline.** Your own workbook script already pulls
    weekly closes back to 2023 (fetchTickersLongFormat). A small chart
    per prospect — price line against its Graham level — answers "is it
    cheap now, or cheap for a reason?" at a glance.

## Ask the data

14. **Consult the watchlist.** The Consultation pattern extends
    naturally: ground the model in the watchlist payload too, so
    "compare X to what I own in its sector" works across both views.
15. **Sizing preview.** Enter a budget; the card shows shares it buys
    and the position's would-be weight in the portfolio. Hypotheticals
    only — the view stays read-only.

## Guardrails (your rules, applied)

- Analysis never writes trades; the only write path is the statement upload.
- Fundamentals refresh is slower-moving than prices: the populate run
  can fetch statements on the same cadence as MarketData, or weekly —
  statements only change quarterly anyway.
- Refresh cadence is the open question, same as MarketData: manual
  script run, or fold watchlist population into the 4:30 AM snapshot
  job so all the data tabs land together.

## Recommended first slice

Items 1–4 plus the stability panel (5–9): Watchlist tab + populate
script with the fundamentals functions + cards with the stability read
(the old "promote-to-ticket" step is gone with the ticket). One evening's work, everything else layers on.
