import { useEffect, useState } from 'react'
import { API_BASE } from '../config.js'
import { sectorColor } from '../components/charts.jsx'

// Watchlist view: tickers Jason adds by symbol, one card each with the
// EDGAR fundamentals (latest value plus the history behind it) and the
// Graham number. Revenue growth shows as two figures: the 10-year
// revenue CAGR (whose history is the annual revenue series) and
// quarterly YoY for the last four quarters. Fundamentals come from
// SEC EDGAR; the Graham number comes from the tracker's own price
// feed — the citation at the bottom of this view says exactly that,
// and each card links to its company's own EDGAR facts URL.
const WATCHLIST_URL = `${API_BASE}/api/watchlist`
const REFRESH_URL = `${API_BASE}/api/watchlist/refresh`

const METRIC_ORDER = [
  'current_ratio',
  'debt_to_equity',
  'free_cash_flow',
  'revenue_cagr_10y',
  'revenue_growth_yoy',
  'return_on_equity',
  'rnd_share',
  'net_margin',
]

function formatValue(metric, value) {
  if (value == null) return '—'
  if (metric.format === 'x') return `${value.toFixed(2)}×`
  if (metric.format === 'pct') return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}%`
  if (metric.format === 'usd') {
    const abs = Math.abs(value)
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`
    return `$${value.toLocaleString('en-US')}`
  }
  return String(value)
}

function MetricRow({ metric }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="metric-row">
      <button type="button" className="metric-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{metric.label}</span>
        <strong>{metric.latest ? formatValue(metric, metric.latest.value) : '—'}</strong>
        <span className="metric-period">
          {metric.latest ? metric.latest.period : 'not tagged'}
        </span>
      </button>
      {open && metric.series.length > 0 && (
        <table className="metric-history">
          <tbody>
            {metric.series.map((p) => (
              <tr key={p.period}>
                <td>{p.period}</td>
                <td>{formatValue({ ...metric, format: metric.history_format || metric.format }, p.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function WatchlistCard({ item, onDelete, onRefresh, busy }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const metrics = METRIC_ORDER.filter((k) => item.metrics[k]).map((k) => item.metrics[k])
  return (
    <article className="holding watchlist-card">
      <div className="holding-head">
        <span className="holding-ticker">{item.ticker}</span>
        {item.sector && (
          <span className="chip-sector" style={{ borderColor: sectorColor(item.sector), color: sectorColor(item.sector) }}>
            {item.sector}
          </span>
        )}
      </div>
      <p className="holding-name">{item.name}</p>
      <p className="holding-foot">
        {item.graham != null ? (
          <>Graham number: <strong>${item.graham.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></>
        ) : (
          <span className="muted">{item.graham_note || 'No Graham number yet.'}</span>
        )}
      </p>
      <div className="watchlist-metrics">
        {metrics.map((m) => (
          <MetricRow key={m.label} metric={m} />
        ))}
      </div>
      {item.notes && item.notes.length > 0 && (
        <ul className="watchlist-notes">
          {item.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <p className="holding-foot">
        {item.edgar_url && (
          <a href={item.edgar_url} target="_blank" rel="noreferrer">EDGAR facts</a>
        )}
        {item.fetched_at && <span className="muted">Fetched {item.fetched_at}</span>}
      </p>
      <div className="watchlist-actions">
        <button type="button" onClick={onRefresh} disabled={busy}>
          Refresh
        </button>
        {confirmDelete ? (
          <>
            <button type="button" className="danger" onClick={onDelete} disabled={busy}>
              Confirm delete
            </button>
            <button type="button" onClick={() => setConfirmDelete(false)} disabled={busy}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        )}
      </div>
    </article>
  )
}

export default function Watchlist() {
  const [items, setItems] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ticker, setTicker] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(WATCHLIST_URL)
      const data = await res.json()
      if (!data.ok) throw new Error(data.message || 'The watchlist failed to load.')
      setItems(data.items || [])
    } catch (err) {
      setError(String(err.message || err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(body),
    })
    return res.json()
  }

  async function add() {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol || busy) return
    setBusy(true)
    setFormError('')
    try {
      const data = await post(WATCHLIST_URL, { ticker: symbol })
      if (!data.ok) {
        setFormError(data.message || 'Could not add that ticker.')
        return
      }
      setTicker('')
      setItems((prev) => {
        const rest = (prev || []).filter((i) => i.ticker !== data.item.ticker)
        return [data.item, ...rest]
      })
    } catch (err) {
      setFormError('Could not reach the backend. Start it with python3 backend/server.py and refresh.')
    } finally {
      setBusy(false)
    }
  }

  async function refreshItem(symbol) {
    if (busy) return
    setBusy(true)
    setFormError('')
    try {
      const data = await post(REFRESH_URL, { ticker: symbol })
      if (!data.ok) {
        setFormError(data.message || 'The refresh failed.')
        return
      }
      setItems((prev) => (prev || []).map((i) => (i.ticker === symbol ? data.item : i)))
    } catch (err) {
      setFormError('Could not reach the backend. Start it with python3 backend/server.py and refresh.')
    } finally {
      setBusy(false)
    }
  }

  async function deleteItem(symbol) {
    if (busy) return
    setBusy(true)
    setFormError('')
    try {
      const res = await fetch(`${WATCHLIST_URL}?ticker=${encodeURIComponent(symbol)}`, { method: 'DELETE' })
      const data = await res.json()
      if (!data.ok) {
        setFormError(data.message || 'The delete failed.')
        return
      }
      setItems((prev) => (prev || []).filter((i) => i.ticker !== symbol))
    } catch (err) {
      setFormError('Could not reach the backend. Start it with python3 backend/server.py and refresh.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <form
        className="watchlist-add"
        onSubmit={(e) => { e.preventDefault(); add() }}
      >
        <label htmlFor="watchlist-ticker">Add a ticker</label>
        <input
          id="watchlist-ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="GOOGL"
          autoCapitalize="characters"
          autoComplete="off"
        />
        <button type="submit" disabled={busy || !ticker.trim()}>Add</button>
      </form>
      {formError && <p className="error">{formError}</p>}
      {loading && <p className="muted">Loading the watchlist…</p>}
      {error && !loading && (
        <section className="card">
          <h2>Couldn’t load the watchlist</h2>
          <p>{error}</p>
          <p>
            The backend answers <code>/api/watchlist</code> from the same
            machine that serves this page. Start it with{' '}
            <code>python3 backend/server.py</code> and refresh.
          </p>
        </section>
      )}
      {!loading && !error && items && items.length === 0 && (
        <p className="muted">No tickers on the watchlist yet — add one above.</p>
      )}
      {!loading && !error && items && items.length > 0 && (
        <div className="holdings">
          {items.map((item) => (
            <WatchlistCard
              key={item.ticker}
              item={item}
              onDelete={() => deleteItem(item.ticker)}
              onRefresh={() => refreshItem(item.ticker)}
              busy={busy}
            />
          ))}
        </div>
      )}
      <p className="footnote">
        Source: SEC EDGAR — the fundamentals on each card are
        computed from the company’s filings at{' '}
        <code>data.sec.gov/api/xbrl/companyfacts/CIK##########.json</code>{' '}
        (each card links to that company’s own facts URL). The Graham
        number comes from the Investment Tracker price feed (yfinance),
        not EDGAR.
      </p>
    </section>
  )
}
