// ---------------------------------------------------------------------------
// Portfolio data layer.
//
// ONE source: the local backend (backend/server.py), which computes the
// portfolio JSON from investments.db. There is no baked-in seed and no
// merge/fallback any more — the view never shows numbers the backend did
// not just serve, so a card can never look live while its data is stale.
//
// API_BASE comes from config.js (VITE_API_URL; empty = same origin, the
// backend serving the built frontend on its own port).
//
// Shape: { as_of, source, total_value, total_cost, total_gain,
//          total_gain_pct, cost_basis, total_dividend_reinvested,
//          sectors, buy_candidates, market_as_of,
//          positions: [{ ticker, name, sector, shares, cost, price,
//          prev_close, day_change_pct, week_close, week_change_pct,
//          value, gain, dividend_reinvested, gain_pct, graham,
//          graham_note, below_graham }],
//          history: [{ date, value }] }
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import { API_BASE } from './config.js'

export const PORTFOLIO_URL = `${API_BASE}/api/portfolio`

export async function loadPortfolio() {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), 10000)
  try {
    const res = await fetch(PORTFOLIO_URL, { signal: ctl.signal })
    clearTimeout(timer)
    if (!res.ok) throw new Error(`backend returned ${res.status}`)
    const data = await res.json()
    if (!data || !Array.isArray(data.positions) || data.positions.length === 0) {
      throw new Error('backend payload had no positions')
    }
    return { data, source: 'live', error: null }
  } catch (err) {
    clearTimeout(timer)
    return { data: null, source: null, error: String(err) }
  }
}

export function usePortfolio() {
  const [state, setState] = useState({
    data: null,
    source: null,
    loading: true,
    error: null,
  })
  useEffect(() => {
    let alive = true
    loadPortfolio().then((r) => {
      if (alive) setState({ ...r, loading: false })
    })
    return () => { alive = false }
  }, [])
  return state
}
