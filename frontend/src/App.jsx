import { useState } from 'react'
import Portfolio from './views/Portfolio.jsx'
import UploadStatement from './views/UploadStatement.jsx'
import Consultation from './views/Consultation.jsx'
import { usePortfolio } from './data-portfolio.js'
import TickerTape from './components/TickerTape.jsx'

export default function App() {
  const [view, setView] = useState('portfolio')
  const pf = usePortfolio()
  return (
    <>
    <main className="page wide">
      <header className="heading">
        <h1>Investment Tracker</h1>
        <p>Holdings, backed by the local investments database.</p>
      </header>
      <nav className="tabs">
        <button type="button" className={view === 'portfolio' ? 'tab active' : 'tab'} onClick={() => setView('portfolio')}>
          Portfolio
        </button>
        <button type="button" className={view === 'upload' ? 'tab active' : 'tab'} onClick={() => setView('upload')}>
          Upload statement
        </button>
        <button type="button" className={view === 'consult' ? 'tab active' : 'tab'} onClick={() => setView('consult')}>
          Consultation
        </button>
      </nav>
      {view === 'portfolio' && pf.loading && (
        <p className="muted">Loading the portfolio from the local database…</p>
      )}
      {view === 'portfolio' && pf.error && !pf.loading && (
        <section className="card">
          <h2>Couldn’t load the portfolio</h2>
          <p>{pf.error}</p>
          <p>
            The backend answers <code>/api/portfolio</code> from the same
            machine that serves this page. Start it with{' '}
            <code>python3 backend/server.py</code> and refresh.
          </p>
        </section>
      )}
      {view === 'portfolio' && pf.data && <Portfolio data={pf.data} loading={pf.loading} />}
      {view === 'upload' && <UploadStatement />}
      {view === 'consult' && <Consultation />}
    </main>
    {pf.data && <TickerTape positions={pf.data.positions} />}
    </>
  )
}
