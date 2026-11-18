// ---------------------------------------------------------------------------
// Portfolio data layer.
//
// SEED: PORTFOLIO below is a baked-in snapshot exported from snapshot.py's
// latest.json (see its as_of; prices are the prior close, per the
// snapshot's convention). It is the fallback and the offline default.
//
// LIVE READ: when VITE_SHEET_ENDPOINT is set (see config.js — the URL of
// the Apps Script web app in apps-script/Code.gs), loadPortfolio() fetches
// the portfolio JSON from the workbook: holdings, shares and cost are
// aggregated by the script from the CleanData lots; prices, Graham numbers
// and day/week moves come from the workbook's MarketData tab (populated by
// the Python yfinance functions in ~/workspace/investments/market_data/).
// For any field the workbook has no data for yet (e.g. a brand-new ticker
// with no MarketData row), mergeLiveWithSeed() carries the seed's value
// for the same ticker. Any fetch problem falls back to the seed entirely
// — the view never goes blank.
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import { SHEET_ENDPOINT } from './config.js'
// Shape: { as_of, total_value, total_cost, total_gain, total_gain_pct,
//          cost_basis, total_dividend_reinvested, sectors, buy_candidates,
//          positions: [{ ticker, name, sector, shares, cost, price,
//          prev_close, day_change_pct, week_close, week_change_pct, value,
//          gain, dividend_reinvested, gain_pct, graham, graham_note,
//          below_graham }] }
// ---------------------------------------------------------------------------
export const PORTFOLIO = {
  "as_of": "2026-11-14",
  "total_value": 6211.53,
  "total_cost": 4956.29,
  "total_gain": 1255.24,
  "total_gain_pct": 25.33,
  "cost_basis": "cash purchases only; reinvested dividends excluded (Jason, 2026-11-12)",
  "total_dividend_reinvested": 139.54,
  "history": [{"date": "2026-11-01", "value": 5877.11}, {"date": "2026-11-02", "value": 5877.11}, {"date": "2026-11-03", "value": 5862.04}, {"date": "2026-11-04", "value": 5845.91}, {"date": "2026-11-05", "value": 6205.66}, {"date": "2026-11-06", "value": 6005.48}, {"date": "2026-11-07", "value": 6036.33}, {"date": "2026-11-08", "value": 6036.33}, {"date": "2026-11-09", "value": 6036.33}, {"date": "2026-11-10", "value": 6140.27}, {"date": "2026-11-11", "value": 6131.05}, {"date": "2026-11-12", "value": 6237.18}, {"date": "2026-11-13", "value": 6221.18}, {"date": "2026-11-14", "value": 6211.53}, {"date": "2026-11-15", "value": 6211.53}, {"date": "2026-11-16", "value": 6211.53}, {"date": "2026-11-17", "value": 6083.51}],
  "sectors": {
    "Technology": 1728.52,
    "Bonds": 1510.01,
    "Mutual Funds": 924.27,
    "Financial": 792.59,
    "Consumer": 510.15,
    "Energy": 365.34,
    "Industrial": 292.39,
    "Healthcare": 88.26
  },
  "buy_candidates": [
    "BAC",
    "PR"
  ],
  "positions": [
    {
      "ticker": "BAC",
      "name": "Bank of America Corporation",
      "sector": "Financial",
      "shares": 7.19,
      "cost": 328.34,
      "price": 51.02,
      "prev_close": 50.51,
      "day_change_pct": 1.01,
      "week_close": 49.42,
      "week_change_pct": 3.24,
      "value": 366.83,
      "gain": 38.49,
      "dividend_reinvested": 10.14,
      "gain_pct": 11.72,
      "graham": 60.83,
      "graham_note": "",
      "below_graham": true
    },
    {
      "ticker": "FBNDX",
      "name": "Fidelity Investment Grade Bond ",
      "sector": "Bonds",
      "shares": 147.57,
      "cost": 1000.78,
      "price": 6.93,
      "prev_close": 6.94,
      "day_change_pct": -0.14,
      "week_close": 7.04,
      "week_change_pct": -1.56,
      "value": 1022.66,
      "gain": 21.88,
      "dividend_reinvested": 66.03,
      "gain_pct": 2.19,
      "graham": null,
      "graham_note": "mutual fund — Graham N/A",
      "below_graham": false
    },
    {
      "ticker": "FCBFX",
      "name": "Fidelity Corporate Bond Fund",
      "sector": "Bonds",
      "shares": 48.11,
      "cost": 500.07,
      "price": 10.13,
      "prev_close": 10.14,
      "day_change_pct": -0.1,
      "week_close": 10.27,
      "week_change_pct": -1.36,
      "value": 487.35,
      "gain": -12.72,
      "dividend_reinvested": 14.34,
      "gain_pct": -2.54,
      "graham": null,
      "graham_note": "mutual fund — Graham N/A",
      "below_graham": false
    },
    {
      "ticker": "FNILX",
      "name": "Fidelity ZERO Large Cap Index F",
      "sector": "Mutual Funds",
      "shares": 23.76,
      "cost": 579.93,
      "price": 27.11,
      "prev_close": 27.22,
      "day_change_pct": -0.4,
      "week_close": 26.43,
      "week_change_pct": 2.57,
      "value": 644.13,
      "gain": 64.2,
      "dividend_reinvested": 4.14,
      "gain_pct": 11.07,
      "graham": null,
      "graham_note": "mutual fund — Graham N/A",
      "below_graham": false
    },
    {
      "ticker": "FZILX",
      "name": "Fidelity International Index Fu",
      "sector": "Mutual Funds",
      "shares": 17.04,
      "cost": 245.07,
      "price": 16.44,
      "prev_close": 16.46,
      "day_change_pct": -0.12,
      "week_close": 16.08,
      "week_change_pct": 2.24,
      "value": 280.14,
      "gain": 35.07,
      "dividend_reinvested": 2.03,
      "gain_pct": 14.31,
      "graham": null,
      "graham_note": "mutual fund — Graham N/A",
      "below_graham": false
    },
    {
      "ticker": "GOOGL",
      "name": "Alphabet Inc.",
      "sector": "Technology",
      "shares": 5.01,
      "cost": 848.28,
      "price": 295.77,
      "prev_close": 298.7,
      "day_change_pct": -0.98,
      "week_close": 284.78,
      "week_change_pct": 3.86,
      "value": 1481.81,
      "gain": 633.53,
      "dividend_reinvested": 1.75,
      "gain_pct": 74.68,
      "graham": 152.04,
      "graham_note": "",
      "below_graham": false
    },
    {
      "ticker": "KO",
      "name": "Coca-Cola Company (The)",
      "sector": "Consumer",
      "shares": 5.14,
      "cost": 346.35,
      "price": 99.25,
      "prev_close": 97.44,
      "day_change_pct": 1.86,
      "week_close": 95.67,
      "week_change_pct": 3.74,
      "value": 510.15,
      "gain": 163.8,
      "dividend_reinvested": 10.89,
      "gain_pct": 47.29,
      "graham": 25.74,
      "graham_note": "",
      "below_graham": false
    },
    {
      "ticker": "NVO",
      "name": "Novo Nordisk A/S",
      "sector": "Healthcare",
      "shares": 2.12,
      "cost": 192.78,
      "price": 41.63,
      "prev_close": 40.65,
      "day_change_pct": 2.41,
      "week_close": 40.31,
      "week_change_pct": 3.27,
      "value": 88.26,
      "gain": -104.52,
      "dividend_reinvested": 5.75,
      "gain_pct": -54.22,
      "graham": 25.72,
      "graham_note": "",
      "below_graham": false
    },
    {
      "ticker": "PR",
      "name": "Permian Resources Corporation",
      "sector": "Energy",
      "shares": 15.85,
      "cost": 200.45,
      "price": 23.05,
      "prev_close": 22.77,
      "day_change_pct": 1.23,
      "week_close": 21.75,
      "week_change_pct": 5.98,
      "value": 365.34,
      "gain": 164.89,
      "dividend_reinvested": 14.06,
      "gain_pct": 82.26,
      "graham": 25.25,
      "graham_note": "",
      "below_graham": true
    },
    {
      "ticker": "STRL",
      "name": "Sterling Infrastructure, Inc.",
      "sector": "Industrial",
      "shares": 1.0,
      "cost": 283.34,
      "price": 292.39,
      "prev_close": 301.6,
      "day_change_pct": -3.05,
      "week_close": 252.82,
      "week_change_pct": 15.65,
      "value": 292.39,
      "gain": 9.05,
      "dividend_reinvested": 0.0,
      "gain_pct": 3.19,
      "graham": 140.6,
      "graham_note": "",
      "below_graham": false
    },
    {
      "ticker": "UMC",
      "name": "United Microelectronics Corpora",
      "sector": "Technology",
      "shares": 16.02,
      "cost": 106.8,
      "price": 15.4,
      "prev_close": 15.76,
      "day_change_pct": -2.28,
      "week_close": 13.85,
      "week_change_pct": 11.19,
      "value": 246.71,
      "gain": 139.91,
      "dividend_reinvested": 10.41,
      "gain_pct": 131.0,
      "graham": 11.76,
      "graham_note": "",
      "below_graham": false
    },
    {
      "ticker": "V",
      "name": "Visa Inc.",
      "sector": "Financial",
      "shares": 1.0,
      "cost": 324.1,
      "price": 425.76,
      "prev_close": 420.31,
      "day_change_pct": 1.3,
      "week_close": 422.65,
      "week_change_pct": 0.74,
      "value": 425.76,
      "gain": 101.66,
      "dividend_reinvested": 0.0,
      "gain_pct": 31.37,
      "graham": 72.89,
      "graham_note": "",
      "below_graham": false
    }
  ]
};

// ---------------------------------------------------------------------------
// Live read integration (Apps Script doGet). See the header comment.
// ---------------------------------------------------------------------------

const MARKET_FIELDS = ['graham', 'prev_close', 'day_change_pct', 'week_close', 'week_change_pct']

export function mergeLiveWithSeed(live) {
  const seedByTicker = new Map(PORTFOLIO.positions.map((p) => [p.ticker, p]))
  const positions = live.positions.map((lp) => {
    const seed = seedByTicker.get(lp.ticker)
    // No live price for this ticker: keep the seed row wholesale rather
    // than show a holding with no price at all.
    if (lp.price == null && seed) return { ...seed }
    const merged = { ...lp }
    if (seed) {
      for (const k of MARKET_FIELDS) {
        if (merged[k] == null && seed[k] != null) merged[k] = seed[k]
      }
      // If a Graham number was carried over, the seed's note (usually "")
      // is the right one; otherwise keep the endpoint's explanation.
      if (merged.graham != null) merged.graham_note = seed.graham_note || ''
    }
    merged.below_graham =
      merged.graham != null && merged.price != null ? merged.price < merged.graham : false
    return merged
  })
  return {
    ...live,
    positions,
    buy_candidates: positions.filter((p) => p.below_graham).map((p) => p.ticker),
    history: live.history && live.history.length > 1 ? live.history : PORTFOLIO.history,
    seed_as_of: PORTFOLIO.as_of,
  }
}

export async function loadPortfolio() {
  if (!SHEET_ENDPOINT) return { data: PORTFOLIO, source: 'seed' }
  try {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), 10000)
    const res = await fetch(SHEET_ENDPOINT, { signal: ctl.signal })
    clearTimeout(timer)
    if (!res.ok) throw new Error(`endpoint returned ${res.status}`)
    const live = await res.json()
    if (!live || !Array.isArray(live.positions) || live.positions.length === 0) {
      throw new Error('endpoint payload had no positions')
    }
    return { data: mergeLiveWithSeed(live), source: 'live' }
  } catch (err) {
    return { data: PORTFOLIO, source: 'seed', error: String(err) }
  }
}

export function usePortfolio() {
  const [state, setState] = useState({
    data: PORTFOLIO,
    source: 'seed',
    loading: Boolean(SHEET_ENDPOINT),
  })
  useEffect(() => {
    let alive = true
    loadPortfolio().then((r) => {
      if (alive) setState({ ...r, loading: false })
    })
    return () => { alive = false }
  }, [])
  // meta (the CleanData-derived dropdown values) rides along in the live
  // payload; null in seed mode, where the config fallbacks apply.
  return { ...state, meta: state.data.meta || null }
}
