import { useEffect, useState } from 'react'
import { API_BASE } from '../config.js'
import { MiniBars, MiniLine, sectorColor } from '../components/charts.jsx'

// Watchlist view: tickers Jason adds by symbol, one card each with the
// EDGAR fundamentals (latest value plus the history behind it) and the
// Graham number, plus the current price with day, 6-month and 1-year
// changes in the card header. Revenue growth shows as two figures:
// the 10-year revenue CAGR (whose history is the annual revenue
// series, shown as a line chart on click) and quarterly YoY for the
// last four quarters (shown as a bar chart on click); the other
// metrics expand to a history table. A reference dropdown at the top
// of the page explains the five headline metrics (name, formula,
// narrative — Jason's wording). Fundamentals come from
// SEC EDGAR; price, changes and the Graham number come from the
// tracker's own price feed — the citation at the bottom of this view
// says exactly that, and each card links to its company's own EDGAR
// facts URL. The data-quality notes EDGAR returns are stored in the
// DB but no longer shown on the card.
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

// Reference definitions for the five headline metrics, in Jason's
// wording verbatim. They name Yahoo Finance tabs as places to find
// the metrics — the numbers on the cards still come from SEC EDGAR
// (see the citation at the bottom of the page), never from Yahoo.
const REFERENCE_CARDS = [
  {
    name: 'Current Ratio (Most Recent Quarter / MRQ)',
    formula: 'Current Ratio = Total Current Assets / Total Current Liabilities',
    narrative: 'The current ratio measures whether a company has enough short-term assets (cash, receivables, inventory) to cover liabilities due within a year. On Yahoo Finance, you can find this directly under the Statistics tab or calculate it from the Balance Sheet. For financial health, a ratio comfortably above 1.0 signals near-term cushion against operational hiccups, though an unusually high ratio can sometimes point to slow-moving inventory or idle cash. For growth potential, healthy liquidity reduces the risk of a cash crunch while the business scales or absorbs working-capital swings.',
  },
  {
    name: 'Total Debt-to-Equity Ratio (MRQ)',
    formula: "Total Debt-to-Equity = Total Debt / Total Stockholders' Equity",
    narrative: 'This leverage ratio compares borrowed capital (short- and long-term debt) against shareholder equity. Note that Yahoo Finance often displays this figure as a percentage (for example, 150% equals 1.5x). For financial health, heavy debt increases fixed interest obligations and vulnerability during downturns or higher-rate environments. For growth potential, moderate leverage can fund expansion without diluting shareholders, whereas excessive debt can force management to prioritize interest payments over R&D or market expansion.',
  },
  {
    name: 'Free Cash Flow (FCF, Trailing Twelve Months / TTM)',
    formula: 'Free Cash Flow = Operating Cash Flow - Capital Expenditures (CapEx)',
    narrative: 'Free cash flow represents the actual cash a business generates after funding day-to-day operations and maintaining or expanding physical/capital assets. You can pull Operating Cash Flow and Capital Expenditures from the Yahoo Finance Cash Flow statement (or check Levered Free Cash Flow under Statistics). For financial health, consistent positive FCF is harder to manipulate than accounting earnings and shows true self-sufficiency. For growth potential, strong FCF gives a company internal "dry powder" to fund new products, acquisitions, or expansion without relying on expensive outside financing.',
  },
  {
    name: 'Quarterly Revenue Growth (Year-over-Year / YoY)',
    formula: 'YoY Revenue Growth = (Revenue Current Quarter - Revenue Same Quarter Prior Year) / Revenue Same Quarter Prior Year',
    narrative: 'YoY quarterly revenue growth tracks how quickly top-line sales are expanding compared with the same period a year earlier, smoothing out seasonal patterns. You can inspect quarterly revenue trends on the Yahoo Finance Income Statement or Analysis tab. For growth potential, sustained top-line expansion proves customer demand and market traction — without growing sales, cost cuts alone have a ceiling. For financial health, pairing revenue growth with healthy margins and cash flow confirms the expansion is durable rather than bought through unsustainable discounting.',
  },
  {
    name: 'Return on Equity (ROE, TTM)',
    formula: 'Return on Equity = Net Income / Average Stockholders\' Equity',
    narrative: "ROE measures how much profit a company generates for each dollar of shareholders' equity, listed on Yahoo Finance's Statistics tab. For growth potential, a solid, consistent ROE indicates that management deploys capital effectively into profitable opportunities. For financial health, always cross-check ROE against Total Debt-to-Equity: high debt shrinks the equity base and can inflate ROE artificially even when underlying operational health is average.",
  },
]

const REFERENCE_VIDEO = {
  title: 'Corporate Finance Explained | The Power of Financial Ratios',
  url: 'https://www.youtube.com/watch?v=Tom1rCDEY0g',
}

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

function MetricRow({ metric, chart }) {
  const [open, setOpen] = useState(false)
  const seriesFmt = (v) =>
    formatValue({ ...metric, format: metric.history_format || metric.format }, v)
  return (
    <div className="metric-row">
      <button type="button" className="metric-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{metric.label}</span>
        <strong>{metric.latest ? formatValue(metric, metric.latest.value) : '—'}</strong>
        <span className="metric-period">
          {metric.latest ? metric.latest.period : 'not tagged'}
        </span>
      </button>
      {open && metric.series.length > 0 && chart === 'bars' && (
        <MiniBars points={metric.series} formatValue={(v) => formatValue(metric, v)} />
      )}
      {open && metric.series.length > 0 && chart === 'line' && (
        <MiniLine points={metric.series} formatValue={seriesFmt} />
      )}
      {open && metric.series.length > 0 && !chart && (
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

function PriceChange({ label, value }) {
  if (value == null) return <span className="muted">{label} —</span>
  const up = value >= 0
  return (
    <span className={up ? 'up' : 'down'}>
      {label} {up ? '+' : '−'}{Math.abs(value).toFixed(2)}%
    </span>
  )
}

function WatchlistCard({ item, onDelete, onRefresh, busy }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
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
      <p className="holding-foot watchlist-price">
        {item.price != null ? (
          <>
            <strong>${item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
            <PriceChange label="1D" value={item.day_change_pct} />
            <PriceChange label="6M" value={item.change_6m_pct} />
            <PriceChange label="1Y" value={item.change_1y_pct} />
            {item.price_date && <span className="muted">as of {item.price_date}</span>}
          </>
        ) : (
          <span className="muted">No price yet — the price refresh has not covered this ticker.</span>
        )}
      </p>
      <p className="holding-foot">
        {item.graham != null ? (
          <>Graham number: <strong>${item.graham.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></>
        ) : (
          <span className="muted">{item.graham_note || 'No Graham number yet.'}</span>
        )}
      </p>
      <div className="watchlist-metrics">
        {METRIC_ORDER.filter((k) => item.metrics[k]).map((k) => (
          <MetricRow
            key={k}
            metric={item.metrics[k]}
            chart={k === 'revenue_growth_yoy' ? 'bars' : k === 'revenue_cagr_10y' ? 'line' : undefined}
          />
        ))}
      </div>
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
      <details className="watchlist-reference">
        <summary>Metric reference — what each card measures</summary>
        <div className="reference-cards">
          {REFERENCE_CARDS.map((c) => (
            <article key={c.name} className="reference-card">
              <h3>{c.name}</h3>
              <p className="reference-formula"><code>{c.formula}</code></p>
              <p>{c.narrative}</p>
            </article>
          ))}
        </div>
        <p className="muted">
          These are reference definitions — the numbers on the cards come
          from SEC EDGAR, not Yahoo Finance. Watching this helps clarify
          how the ratios connect profitability, leverage, and cash flow:{' '}
          <a href={REFERENCE_VIDEO.url} target="_blank" rel="noreferrer">{REFERENCE_VIDEO.title}</a>
        </p>
      </details>
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
