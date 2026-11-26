// Hand-rolled SVG/div charts -- no chart library, keeps the bundle light.

import { useRef, useState } from 'react'

const SECTOR_COLORS = {
  Technology: '#2f6fed',
  Bonds: '#94a3b8',
  'Mutual Funds': '#5da271',
  Financial: '#e0a100',
  Consumer: '#d96c33',
  Energy: '#7d5ba6',
  Industrial: '#3d8b8b',
  Healthcare: '#c0527d',
}

export function sectorColor(sector) {
  return SECTOR_COLORS[sector] || '#666'
}

const money0 = (v) =>
  `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

// Position a tooltip so it never runs off the chart (and so off the
// phone screen): flip it to the other side of the cursor near an edge.
const tipStyle = (tip) => {
  const fx = tip.w && tip.x > tip.w * 0.55
  const fy = tip.h && tip.y > tip.h * 0.55
  const tf = [fx && 'translateX(-100%)', fy && 'translateY(-100%)'].filter(Boolean).join(' ')
  return { left: fx ? tip.x - 14 : tip.x + 14, top: fy ? tip.y - 14 : tip.y + 14, transform: tf || undefined }
}

export function DonutChart({ sectors, total }) {
  const entries = Object.entries(sectors).sort((a, b) => b[1] - a[1])
  const r = 70
  const C = 2 * Math.PI * r
  let offset = 0
  const slices = entries.map(([label, value]) => {
    const frac = value / total
    const slice = { label, value, frac, dash: frac * C, offset }
    offset += frac * C
    return slice
  })
  const [tip, setTip] = useState(null)
  const wrapRef = useRef(null)
  const move = (e) => {
    const rect = wrapRef.current.getBoundingClientRect()
    setTip((t) => (t ? { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width, h: rect.height } : t))
  }
  return (
    <div className="donut-wrap chart-hover" ref={wrapRef} onMouseMove={move} onMouseLeave={() => setTip(null)}>
      <svg viewBox="0 0 200 200" className="donut" role="img" aria-label="Allocation by sector">
        <g transform="rotate(-90 100 100)">
          {slices.map((s) => (
            <circle
              key={s.label}
              cx="100" cy="100" r={r}
              fill="none"
              stroke={sectorColor(s.label)}
              strokeWidth={tip && tip.label === s.label ? 40 : 34}
              strokeDasharray={`${Math.max(s.dash - 1.5, 0.5)} ${C - s.dash + 1.5}`}
              strokeDashoffset={-s.offset}
              opacity={tip && tip.label !== s.label ? 0.4 : 1}
              onMouseEnter={() => setTip({ label: s.label, value: s.value, frac: s.frac, x: 0, y: 0 })}
            />
          ))}
        </g>
        {tip ? (
          <>
            <text x="100" y="96" textAnchor="middle" className="donut-total">{(tip.frac * 100).toFixed(1)}%</text>
            <text x="100" y="114" textAnchor="middle" className="donut-sub">{tip.label}</text>
          </>
        ) : (
          <>
            <text x="100" y="96" textAnchor="middle" className="donut-total">
              ${total.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </text>
            <text x="100" y="114" textAnchor="middle" className="donut-sub">total value</text>
          </>
        )}
      </svg>
      {tip && (
        <div className="chart-tip" style={tipStyle(tip)}>
          <strong>{tip.label}</strong> · {money0(tip.value)} · {(tip.frac * 100).toFixed(1)}%
        </div>
      )}
      <ul className="legend">
        {slices.map((s) => (
          <li key={s.label}>
            <span className="swatch" style={{ background: sectorColor(s.label) }} />
            <span className="legend-label">{s.label}</span>
            <span className="legend-value">
              ${s.value.toLocaleString('en-US', { maximumFractionDigits: 0 })} · {(s.frac * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Signed horizontal bars, zero line in the middle. Values always shown signed.
export function GainBars({ positions }) {
  const sorted = [...positions].sort((a, b) => b.gain_pct - a.gain_pct)
  const max = Math.max(...sorted.map((p) => Math.abs(p.gain_pct)), 1)
  return (
    <div className="gainbars">
      {sorted.map((p) => {
        const w = (Math.abs(p.gain_pct) / max) * 50
        const pos = p.gain_pct >= 0
        return (
          <div className="gainbar-row" key={p.ticker}>
            <span className="gainbar-ticker">{p.ticker}</span>
            <span className="gainbar-track">
              <span className="gainbar-zero" />
              <span
                className={pos ? 'gainbar-fill pos' : 'gainbar-fill neg'}
                style={pos ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
              />
            </span>
            <span className={pos ? 'gainbar-value pos' : 'gainbar-value neg'}>
              {pos ? '+' : '−'}{Math.abs(p.gain_pct).toFixed(2)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}

// Line graph of the portfolio's total value over time. history is
// [{date: 'YYYY-MM-DD', value}] ascending, one point per daily snapshot.
export function HistoryChart({ history }) {
  const [tip, setTip] = useState(null)
  const wrapRef = useRef(null)
  if (!history || history.length < 2) {
    return <p className="muted">Not enough history yet — the line builds as daily totals accumulate.</p>
  }
  const W = 640, H = 200, PADL = 8, PADR = 8, PADT = 16, PADB = 22
  const values = history.map((h) => h.value)
  const lo = Math.min(...values), hi = Math.max(...values)
  const pad = Math.max((hi - lo) * 0.15, 25)
  const min = lo - pad, max = hi + pad
  const x = (i) => PADL + (i / (history.length - 1)) * (W - PADL - PADR)
  const y = (v) => PADT + (1 - (v - min) / (max - min)) * (H - PADT - PADB)
  const pts = history.map((h, i) => [x(i), y(h.value)])
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L${x(history.length - 1).toFixed(1)},${H - PADB} L${x(0).toFixed(1)},${H - PADB} Z`
  const fmtDate = (d) =>
    new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const first = history[0], last = history[history.length - 1]
  const change = last.value - first.value
  const changePct = (change / first.value) * 100
  const move = (e) => {
    const rect = wrapRef.current.getBoundingClientRect()
    setTip((t) => (t ? { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width, h: rect.height } : t))
  }
  const tipPoint = tip ? history[tip.i] : null
  const tipDelta = tip && tip.i > 0 ? tipPoint.value - history[tip.i - 1].value : null
  return (
    <div>
      <p className="history-summary">
        {money0(last.value)} ·{' '}
        <span className={change >= 0 ? 'up' : 'down'}>
          {change >= 0 ? '+' : '−'}{money0(Math.abs(change))} ({change >= 0 ? '+' : '−'}{Math.abs(changePct).toFixed(1)}%)
        </span>{' '}
        since {fmtDate(first.date)}
      </p>
      <div className="chart-hover" ref={wrapRef} onMouseMove={move} onMouseLeave={() => setTip(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="history-chart" role="img" aria-label="Total portfolio value over time">
          <path d={area} className="history-area" />
          <path d={line} className="history-line" />
          {pts.map((p, i) => (
            <g key={history[i].date}>
              {tip && tip.i === i && <circle cx={p[0]} cy={p[1]} r="4.5" className="history-dot" />}
              <circle
                cx={p[0]} cy={p[1]} r="12" fill="transparent"
                onMouseEnter={() => setTip({ i, x: 0, y: 0 })}
              />
            </g>
          ))}
          <text x={PADL} y={H - 6} className="axis-label">{fmtDate(first.date)}</text>
          <text x={W - PADR} y={H - 6} textAnchor="end" className="axis-label">{fmtDate(last.date)}</text>
          <text x={W - PADR} y={PADT - 4} textAnchor="end" className="axis-label">{money0(hi)}</text>
          <text x={W - PADR} y={H - PADB - 4} textAnchor="end" className="axis-label">{money0(lo)}</text>
        </svg>
        {tipPoint && (
          <div className="chart-tip" style={tipStyle(tip)}>
            <strong>{fmtDate(tipPoint.date)}</strong> · {money0(tipPoint.value)}
            {tipDelta != null && (
              <> · <span className={tipDelta >= 0 ? 'up' : 'down'}>{tipDelta >= 0 ? '+' : '−'}{money0(Math.abs(tipDelta))}</span></>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Small bar chart: one vertical bar per point, zero line in the
// middle, value labelled on each bar. Used for the watchlist's
// quarterly YoY growth (four quarters). points: [{period, value}].
export function MiniBars({ points, formatValue }) {
  if (!points || points.length === 0) {
    return <p className="muted">No values yet.</p>
  }
  const W = 640, H = 200, PADL = 8, PADR = 8, PADT = 28, PADB = 24
  const values = points.map((p) => p.value)
  const hi = Math.max(0, ...values), lo = Math.min(0, ...values)
  const span = hi - lo || 1
  const y = (v) => PADT + (1 - (v - lo) / span) * (H - PADT - PADB)
  const zeroY = y(0)
  const slot = (W - PADL - PADR) / points.length
  const bw = Math.min(64, slot * 0.55)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="history-chart" role="img" aria-label="Quarterly values">
      <line x1={PADL} y1={zeroY} x2={W - PADR} y2={zeroY} stroke="#b9c6bb" strokeWidth="1" />
      {points.map((p, i) => {
        const cx = PADL + slot * (i + 0.5)
        const top = Math.min(y(p.value), zeroY)
        const h = Math.abs(zeroY - y(p.value))
        const labelY = p.value >= 0 ? top - 6 : top + h + 14
        return (
          <g key={p.period}>
            <rect x={cx - bw / 2} y={top} width={bw} height={Math.max(h, 1.5)}
              className={p.value >= 0 ? 'mini-bar-pos' : 'mini-bar-neg'} />
            <text x={cx} y={labelY} textAnchor="middle" className="mini-bar-value">
              {formatValue(p.value)}
            </text>
            <text x={cx} y={H - 6} textAnchor="middle" className="axis-label">{p.period}</text>
          </g>
        )
      })}
    </svg>
  )
}

// Small line chart with a tooltip on each point: period and value,
// nothing more. Used for the watchlist's 10-year annual revenue
// (the series behind the revenue CAGR). points: [{period, value}].
// The tooltip flips near the frame edge (tipStyle) so it stays on
// the phone screen; tapping a point shows it too.
export function MiniLine({ points, formatValue }) {
  const [tip, setTip] = useState(null)
  const wrapRef = useRef(null)
  if (!points || points.length < 2) {
    return <p className="muted">Not enough history yet.</p>
  }
  const W = 640, H = 200, PADL = 8, PADR = 8, PADT = 16, PADB = 22
  const values = points.map((p) => p.value)
  const lo = Math.min(...values), hi = Math.max(...values)
  const pad = Math.max((hi - lo) * 0.15, 1)
  const min = lo - pad, max = hi + pad
  const x = (i) => PADL + (i / (points.length - 1)) * (W - PADL - PADR)
  const y = (v) => PADT + (1 - (v - min) / (max - min)) * (H - PADT - PADB)
  const pts = points.map((p, i) => [x(i), y(p.value)])
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - PADB} L${x(0).toFixed(1)},${H - PADB} Z`
  const place = (e) => {
    const rect = wrapRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width, h: rect.height }
  }
  const move = (e) => {
    if (tip) setTip((t) => ({ ...t, ...place(e) }))
  }
  const show = (e, i) => setTip({ i, ...place(e) })
  const tipPoint = tip ? points[tip.i] : null
  return (
    <div className="chart-hover" ref={wrapRef} onMouseMove={move} onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="history-chart" role="img" aria-label="Annual values over time">
        <path d={area} className="history-area" />
        <path d={line} className="history-line" />
        {pts.map((p, i) => (
          <g key={points[i].period}>
            {tip && tip.i === i && <circle cx={p[0]} cy={p[1]} r="4.5" className="history-dot" />}
            <circle
              cx={p[0]} cy={p[1]} r="12" fill="transparent"
              onMouseEnter={(e) => show(e, i)}
              onClick={(e) => show(e, i)}
            />
          </g>
        ))}
        <text x={PADL} y={H - 6} className="axis-label">{points[0].period}</text>
        <text x={W - PADR} y={H - 6} textAnchor="end" className="axis-label">{points[points.length - 1].period}</text>
        <text x={W - PADR} y={PADT - 4} textAnchor="end" className="axis-label">{formatValue(hi)}</text>
        <text x={W - PADR} y={H - PADB - 4} textAnchor="end" className="axis-label">{formatValue(lo)}</text>
      </svg>
      {tipPoint && (
        <div className="chart-tip" style={tipStyle(tip)}>
          <strong>{tipPoint.period}</strong> · {formatValue(tipPoint.value)}
        </div>
      )}
    </div>
  )
}

// Bar chart of the gain or loss earned WITHIN each period — one bar per
// quarter or per year, computed from the daily portfolio_totals history
// (each point: {date, value, cost}). For each period:
//   gain = (value_end - value_start) - (cost_end - cost_start)
//   pct  = gain / cost_start * 100
// A period starts at the previous period's end snapshot; the first
// period starts at the first snapshot (2024-03-05). Bars are labelled
// with the % of start cost; the tooltip adds the dollar gain/loss.
// The tooltip flips near the frame edge (tipStyle) so it stays on the
// phone screen; tapping a bar shows it too.
const marginPeriods = (history, granularity) => {
  const keyOf = (d) => {
    const [y, m] = d.split('-').map(Number)
    return granularity === 'annual' ? `${y}` : `${y}-Q${Math.floor((m - 1) / 3) + 1}`
  }
  const labelOf = (d) => {
    const [y, m] = d.split('-').map(Number)
    if (granularity === 'annual') return `${y}`
    return `Q${Math.floor((m - 1) / 3) + 1} '${String(y).slice(2)}`
  }
  const longOf = (d) => {
    const [y, m] = d.split('-').map(Number)
    if (granularity === 'annual') return `${y}`
    return `Q${Math.floor((m - 1) / 3) + 1} ${y}`
  }
  const periodEnd = (d) => {
    const [y, m] = d.split('-').map(Number)
    if (granularity === 'annual') return `${y}-12-31`
    const qm = Math.floor((m - 1) / 3) * 3 + 3
    const last = new Date(y, qm, 0).getDate()
    return `${y}-${String(qm).padStart(2, '0')}-${String(last).padStart(2, '0')}`
  }
  const groups = []
  for (const h of history) {
    const k = keyOf(h.date)
    if (!groups.length || groups[groups.length - 1].key !== k) groups.push({ key: k, points: [] })
    groups[groups.length - 1].points.push(h)
  }
  let prevEnd = history[0]
  return groups.map((g) => {
    const end = g.points[g.points.length - 1]
    const start = prevEnd
    prevEnd = end
    const gain = (end.value - start.value) - (end.cost - start.cost)
    return {
      key: g.key,
      label: labelOf(end.date),
      longLabel: longOf(end.date),
      endDate: end.date,
      partial: end.date < periodEnd(end.date),
      gain,
      pct: start.cost ? (gain / start.cost) * 100 : 0,
    }
  })
}

const signedMoney0 = (v) =>
  `${v >= 0 ? '+' : '−'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const signedPct1 = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`

export function MarginBars({ history }) {
  const [granularity, setGranularity] = useState('quarterly')
  const [tip, setTip] = useState(null)
  const wrapRef = useRef(null)
  if (!history || history.length < 2) {
    return <p className="muted">Not enough history yet — the bars build as daily totals accumulate.</p>
  }
  const points = marginPeriods(history, granularity)
  const W = 640, H = 200, PADL = 8, PADR = 8, PADT = 28, PADB = 24
  const values = points.map((p) => p.pct)
  const hi = Math.max(0, ...values), lo = Math.min(0, ...values)
  const span = hi - lo || 1
  const y = (v) => PADT + (1 - (v - lo) / span) * (H - PADT - PADB)
  const zeroY = y(0)
  const slot = (W - PADL - PADR) / points.length
  const bw = Math.min(64, slot * 0.55)
  const fmtDate = (d) =>
    new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const fmtDateY = (d) =>
    new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  const place = (e) => {
    const rect = wrapRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width, h: rect.height }
  }
  const move = (e) => {
    if (tip) setTip((t) => ({ ...t, ...place(e) }))
  }
  const show = (e, i) => setTip({ i, ...place(e) })
  const tipPoint = tip ? points[tip.i] : null
  const last = points[points.length - 1]
  // The first snapshot can sit above or below cost (day one closed
  // below it); that gap predates the first bar, so the bars alone do
  // not sum to the total gain. Say so under the chart, from the data.
  const dayOneGap = history[0].value - history[0].cost
  return (
    <div>
      <div className="tabs" role="group" aria-label="Margin period">
        <button
          type="button"
          className={granularity === 'quarterly' ? 'tab active' : 'tab'}
          onClick={() => { setGranularity('quarterly'); setTip(null) }}
        >Quarterly</button>
        <button
          type="button"
          className={granularity === 'annual' ? 'tab active' : 'tab'}
          onClick={() => { setGranularity('annual'); setTip(null) }}
        >Annual</button>
      </div>
      <div className="chart-hover" ref={wrapRef} onMouseMove={move} onMouseLeave={() => setTip(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="history-chart" role="img" aria-label="Gain or loss within each period">
          <line x1={PADL} y1={zeroY} x2={W - PADR} y2={zeroY} stroke="#b9c6bb" strokeWidth="1" />
          {points.map((p, i) => {
            const cx = PADL + slot * (i + 0.5)
            const top = Math.min(y(p.pct), zeroY)
            const h = Math.abs(zeroY - y(p.pct))
            const labelY = p.pct >= 0 ? top - 6 : top + h + 14
            return (
              <g key={p.key}>
                <rect x={cx - bw / 2} y={top} width={bw} height={Math.max(h, 1.5)}
                  className={p.pct >= 0 ? 'mini-bar-pos' : 'mini-bar-neg'}
                  onMouseEnter={(e) => show(e, i)}
                  onClick={(e) => show(e, i)} />
                <text x={cx} y={labelY} textAnchor="middle" className="mini-bar-value">
                  {signedPct1(p.pct)}
                </text>
                <text x={cx} y={H - 6} textAnchor="middle" className="axis-label">{p.label}</text>
              </g>
            )
          })}
        </svg>
        {tipPoint && (
          <div className="chart-tip" style={tipStyle(tip)}>
            <strong>{tipPoint.longLabel}{tipPoint.partial ? ` (through ${fmtDate(tipPoint.endDate)})` : ''}</strong>
            {' · '}{signedMoney0(tipPoint.gain)}
            {' · '}<span className={tipPoint.pct >= 0 ? 'up' : 'down'}>{signedPct1(tipPoint.pct)}</span>
          </div>
        )}
      </div>
      <p className="muted">
        Gain or loss earned within each {granularity === 'quarterly' ? 'quarter' : 'year'}, as a % of the cost at the
        period start (new money added during the period is excluded).
        {last.partial && (
          <> The current {granularity === 'quarterly' ? 'quarter' : 'year'} is in progress — through {fmtDate(last.endDate)}.</>
        )}
        {dayOneGap !== 0 && (
          <> The first day ({fmtDateY(history[0].date)}) closed {money0(Math.abs(dayOneGap))} {dayOneGap < 0 ? 'below' : 'above'} cost, before the first bar.</>
        )}
      </p>
    </div>
  )
}
