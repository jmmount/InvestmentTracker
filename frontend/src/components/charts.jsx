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
    setTip((t) => (t ? { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top } : t))
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
        <div className="chart-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
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
    setTip((t) => (t ? { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top } : t))
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
          <div className="chart-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
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
