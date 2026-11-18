import { DonutChart, GainBars, HistoryChart, sectorColor } from '../components/charts.jsx'

const money = (v, digits = 2) =>
  `$${v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
const signedPct = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`

function HoldingCard({ p, isBuyCandidate }) {
  return (
    <article className={isBuyCandidate ? 'holding buy' : 'holding'}>
      <div className="holding-head">
        <span className="holding-ticker">{p.ticker}</span>
        <span className="chip-sector" style={{ borderColor: sectorColor(p.sector), color: sectorColor(p.sector) }}>
          {p.sector}
        </span>
      </div>
      <p className="holding-name">{p.name.trim()}</p>
      <p className="holding-price">
        {money(p.price)}{' '}
        {p.day_change_pct != null && (
          <span className={p.day_change_pct >= 0 ? 'delta up' : 'delta down'}>
            {signedPct(p.day_change_pct)} today
          </span>
        )}
      </p>
      <dl className="holding-stats">
        <div><dt>Shares</dt><dd>{p.shares}</dd></div>
        <div><dt>Value</dt><dd>{money(p.value)}</dd></div>
        <div><dt>Cost</dt><dd>{money(p.cost)}</dd></div>
        <div>
          <dt>Gain</dt>
          <dd className={p.gain >= 0 ? 'up' : 'down'}>
            {p.gain >= 0 ? '+' : '−'}{money(Math.abs(p.gain))} ({signedPct(p.gain_pct)})
          </dd>
        </div>
      </dl>
      <p className="holding-foot">
        {p.graham != null ? (
          <>Graham number: <strong>{money(p.graham)}</strong></>
        ) : (
          <span className="muted">{p.graham_note}</span>
        )}
        {isBuyCandidate && <span className="badge">Below Graham · buy candidate</span>}
      </p>
    </article>
  )
}

export default function Portfolio({ data: d, source, loading }) {
  const positions = [...d.positions].sort((a, b) => b.value - a.value)
  return (
    <section>
      <div className="stats">
        <div className="stat">
          <span className="stat-label">Total value</span>
          <span className="stat-value">{money(d.total_value)}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Total gain</span>
          <span className={d.total_gain >= 0 ? 'stat-value up' : 'stat-value down'}>
            {d.total_gain >= 0 ? '+' : '−'}{money(Math.abs(d.total_gain))} ({signedPct(d.total_gain_pct)})
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Cost basis</span>
          <span className="stat-value">{money(d.total_cost)}</span>
        </div>
      </div>

      <div className="charts">
        <div className="card">
          <h2>Allocation by sector</h2>
          <DonutChart sectors={d.sectors} total={d.total_value} />
        </div>
        <div className="card">
          <h2>Gain / loss by holding</h2>
          <GainBars positions={d.positions} />
        </div>
      </div>

      <div className="card history-card">
        <h2>Total value history</h2>
        <HistoryChart history={d.history} />
      </div>

      <h2 className="section-title">Holdings</h2>
      {loading && <p className="muted">Fetching live data from the workbook…</p>}
      <div className="holdings">
        {positions.map((p) => (
          <HoldingCard key={p.ticker} p={p} isBuyCandidate={d.buy_candidates.includes(p.ticker)} />
        ))}
      </div>

      {source === 'live' ? (
        <p className="footnote">
          Live from the Investments workbook — holdings, shares and cost aggregated from the
          CleanData lots by the Apps Script read endpoint. Cost basis: {d.cost_basis}{' '}
          Reinvested dividends excluded from cost: {money(d.total_dividend_reinvested)}.
          {d.market_as_of ? (
            <> Prices, Graham numbers and day/week moves come from the workbook's MarketData
            tab (yfinance functions, close of {d.market_as_of}).</>
          ) : (
            <> Graham numbers and day/week moves are carried from the {d.seed_as_of} snapshot
            until the workbook's MarketData tab is populated.</>
          )}
        </p>
      ) : (
        <p className="footnote">
          Snapshot as of {d.as_of} — prices are the prior close. Cost basis: {d.cost_basis}
          {' '}Reinvested dividends excluded from cost: {money(d.total_dividend_reinvested)}.
          Data source: the Investments workbook — the spreadsheet stays the backend;
          this baked-in snapshot is showing because the live read endpoint is not
          configured in .env or did not answer.
        </p>
      )}
    </section>
  )
}
