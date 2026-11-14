// Hand-rolled SVG/div charts -- no chart library, keeps the bundle light.

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
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 200 200" className="donut" role="img" aria-label="Allocation by sector">
        <g transform="rotate(-90 100 100)">
          {slices.map((s) => (
            <circle
              key={s.label}
              cx="100" cy="100" r={r}
              fill="none"
              stroke={sectorColor(s.label)}
              strokeWidth="34"
              strokeDasharray={`${Math.max(s.dash - 1.5, 0.5)} ${C - s.dash + 1.5}`}
              strokeDashoffset={-s.offset}
            />
          ))}
        </g>
        <text x="100" y="96" textAnchor="middle" className="donut-total">
          ${total.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </text>
        <text x="100" y="114" textAnchor="middle" className="donut-sub">total value</text>
      </svg>
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
