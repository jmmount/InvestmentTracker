import { useMemo, useState } from 'react'
import { TICKET_POST_ENABLED, TICKERS as FALLBACK_TICKERS, SECTORS as FALLBACK_SECTORS, PURCHASE_TYPES as FALLBACK_PURCHASE_TYPES } from '../config.js'

// Ticket column order (matches the lots table):
// Timestamp | Ticker | Date | Number of Shares | Purchase Price | Sector | Purchase Type

function todayISO() {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// "2026-03-05" -> "3/5/2026" (the workbook's date style)
function sheetDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return `${m}/${d}/${y}`
}

// Matches the Timestamp style the form writes, e.g. "7/26/2025 19:53:02"
function sheetTimestamp(date) {
  const m = date.getMonth() + 1
  const d = date.getDate()
  const y = date.getFullYear()
  const hh = date.getHours()
  const mm = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${m}/${d}/${y} ${hh}:${mm}:${ss}`
}

function toRow(t) {
  return [t.timestamp, t.ticker, t.date, t.shares, t.price, t.sector, t.purchaseType]
}

function toTSV(t) {
  return toRow(t).join('\t')
}

function csvEscape(v) {
  const s = String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export default function PurchaseTicket({ meta }) {
  // Dropdown values are derived from the lots table by the backend
  // (meta) whenever it answered; the config lists are only the offline
  // fallback, mirroring the database as of 2026-11-13.
  const TICKERS = meta && meta.tickers && meta.tickers.length ? meta.tickers : FALLBACK_TICKERS
  const SECTORS = meta && meta.sectors && meta.sectors.length ? meta.sectors : FALLBACK_SECTORS
  const PURCHASE_TYPES = meta && meta.purchase_types && meta.purchase_types.length ? meta.purchase_types : FALLBACK_PURCHASE_TYPES
  const [tickerChoice, setTickerChoice] = useState('')
  const [customTicker, setCustomTicker] = useState('')
  const [date, setDate] = useState(todayISO())
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [sector, setSector] = useState('')
  const [purchaseType, setPurchaseType] = useState('Cash')
  const [tickets, setTickets] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const ticker = tickerChoice === '__other__' ? customTicker.trim().toUpperCase() : tickerChoice

  const total = useMemo(() => {
    const s = parseFloat(shares)
    const p = parseFloat(price)
    return Number.isFinite(s) && Number.isFinite(p) ? s * p : null
  }, [shares, price])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setNotice('')

    if (!ticker) return setError('Pick a ticker (or choose Other and type one).')
    if (!date) return setError('Date is required.')
    const s = parseFloat(shares)
    if (!Number.isFinite(s) || s <= 0) return setError('Number of Shares must be greater than 0.')
    const p = parseFloat(price)
    if (!Number.isFinite(p) || p <= 0) return setError('Purchase Price must be greater than 0.')
    if (!sector) return setError('Pick a sector.')

    const ticket = {
      id: Date.now(),
      timestamp: sheetTimestamp(new Date()),
      ticker,
      date: sheetDate(date),
      shares: String(shares).trim(),
      price: String(price).trim(),
      sector,
      purchaseType,
      status: 'ready',
    }

    // Ticket POSTs are deliberately disabled (TICKET_POST_ENABLED=false):
    // the write phase that posts tickets to the backend is a separate,
    // later step. Until then every ticket is recorded below for copy or
    // CSV download.
    setNotice('Ticket recorded below. Copy its row for your records, or download the CSV.')

    setTickets((prev) => [ticket, ...prev])
    setTickerChoice('')
    setCustomTicker('')
    setShares('')
    setPrice('')
    setSector('')
    setPurchaseType('Cash')
    setDate(todayISO())
  }

  async function copyRow(t) {
    try {
      await navigator.clipboard.writeText(toTSV(t))
      setNotice(`Row for ${t.ticker} copied — paste it where you keep ticket rows.`)
    } catch {
      setError('Clipboard was blocked by the browser — use Download CSV instead.')
    }
  }

  function downloadCSV() {
    const header = ['Timestamp', 'Ticker', 'Date', 'Number of Shares', 'Purchase Price', 'Sector', 'Purchase Type']
    const lines = [header, ...[...tickets].reverse().map(toRow)]
      .map((r) => r.map(csvEscape).join(','))
      .join('\n')
    const blob = new Blob([lines + '\n'], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'purchase-tickets.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <main className="page">
      <header className="heading">
        <h1>Purchase Ticket</h1>
        <p>Log a stock purchase — same fields as the form. Tickets are recorded below until the database write phase lands.</p>
      </header>

      <form className="card" onSubmit={handleSubmit}>
        <label className="field">
          <span>Ticker *</span>
          <select value={tickerChoice} onChange={(e) => setTickerChoice(e.target.value)}>
            <option value="">Select ticker</option>
            {TICKERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            <option value="__other__">Other…</option>
          </select>
        </label>

        {tickerChoice === '__other__' && (
          <label className="field">
            <span>New ticker *</span>
            <input
              type="text"
              value={customTicker}
              onChange={(e) => setCustomTicker(e.target.value)}
              placeholder="e.g. AAPL"
              autoCapitalize="characters"
            />
          </label>
        )}

        <label className="field">
          <span>Date *</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>

        <div className="row2">
          <label className="field">
            <span>Number of Shares *</span>
            <input
              type="number"
              step="any"
              min="0"
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              placeholder="e.g. 27.548"
              inputMode="decimal"
            />
          </label>
          <label className="field">
            <span>Purchase Price *</span>
            <input
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="e.g. 165.74"
              inputMode="decimal"
            />
          </label>
        </div>

        {total !== null && (
          <p className="total">Total cost: <strong>${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></p>
        )}

        <label className="field">
          <span>Sector *</span>
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="">Select sector</option>
            {SECTORS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <fieldset className="field">
          <legend>Purchase Type *</legend>
          <div className="pills">
            {PURCHASE_TYPES.map((pt) => (
              <label key={pt} className={purchaseType === pt ? 'pill active' : 'pill'}>
                <input
                  type="radio"
                  name="purchaseType"
                  value={pt}
                  checked={purchaseType === pt}
                  onChange={() => setPurchaseType(pt)}
                />
                {pt}
              </label>
            ))}
          </div>
        </fieldset>

        {error && <p className="error">{error}</p>}

        <button type="submit" className="submit">Submit ticket</button>
      </form>

      {notice && <p className="notice">{notice}</p>}

      {tickets.length > 0 && (
        <section className="card">
          <div className="tickets-head">
            <h2>Tickets this session ({tickets.length})</h2>
            <button type="button" onClick={downloadCSV}>Download CSV</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ticker</th><th>Date</th><th>Shares</th><th>Price</th>
                  <th>Sector</th><th>Type</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <tr key={t.id}>
                    <td>{t.ticker}</td>
                    <td>{t.date}</td>
                    <td>{t.shares}</td>
                    <td>{t.price}</td>
                    <td>{t.sector}</td>
                    <td>{t.purchaseType}</td>
                    <td>{t.status}</td>
                    <td><button type="button" onClick={() => copyRow(t)}>Copy row</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">Copy row pastes as one tab-separated row in ticket column order: Timestamp, Ticker, Date, Number of Shares, Purchase Price, Sector, Purchase Type.</p>
        </section>
      )}
    </main>
  )
}
