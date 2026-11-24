// Ticker tape pinned to the bottom of the screen. Fed by the same
// portfolio payload as the cards and totals — price and day move per
// holding, scrolling in a seamless loop (the strip is rendered twice;
// hovering pauses it).
const signedPct = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`

export default function TickerTape({ positions }) {
  if (!positions || positions.length === 0) return null
  const items = [...positions].sort((a, b) => b.value - a.value)
  const strip = (id, hidden) => (
    <div className="tape-strip" aria-hidden={hidden || undefined} key={id}>
      {items.map((p) => (
        <span className="tape-item" key={p.ticker}>
          <strong>{p.ticker}</strong> ${p.price.toFixed(2)}
          {p.day_change_pct != null && (
            <span className={p.day_change_pct >= 0 ? 'up' : 'down'}> {signedPct(p.day_change_pct)}</span>
          )}
        </span>
      ))}
    </div>
  )
  return (
    <div className="ticker-tape">
      <div className="tape-track">{strip('a')}{strip('b', true)}</div>
    </div>
  )
}
