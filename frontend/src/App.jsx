import { useState } from 'react'
import Portfolio from './views/Portfolio.jsx'
import PurchaseTicket from './views/PurchaseTicket.jsx'

export default function App() {
  const [view, setView] = useState('portfolio')
  return (
    <main className="page wide">
      <header className="heading">
        <h1>Investment Tracker</h1>
        <p>Holdings and purchase tickets, backed by the Investments spreadsheet.</p>
      </header>
      <nav className="tabs">
        <button type="button" className={view === 'portfolio' ? 'tab active' : 'tab'} onClick={() => setView('portfolio')}>
          Portfolio
        </button>
        <button type="button" className={view === 'ticket' ? 'tab active' : 'tab'} onClick={() => setView('ticket')}>
          Purchase Ticket
        </button>
      </nav>
      {view === 'portfolio' ? <Portfolio /> : <PurchaseTicket />}
    </main>
  )
}
