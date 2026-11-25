import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../config.js'

// Consultation view: chat with a Gemini model about the portfolio.
// The browser talks ONLY to the local backend (POST /api/consult); the
// backend holds the Gemini API key in its environment and calls the
// model server-side, grounding the conversation in the live portfolio
// payload. The key never reaches this code.
const CONSULT_URL = `${API_BASE}/api/consult`
const SUGGESTIONS = [
  'How concentrated is my portfolio by sector?',
  'Which holdings are below their Graham number, and what does that mean?',
  'Walk me through my biggest winners and losers.',
  'What are the main risks in this portfolio?',
]

export default function Consultation() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const logRef = useRef(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, busy])

  async function send(text) {
    const trimmed = (text || '').trim()
    if (!trimmed || busy) return
    const history = [...messages, { role: 'user', text: trimmed }]
    setMessages(history)
    setInput('')
    setNotice('')
    setBusy(true)
    try {
      // text/plain keeps this a CORS "simple request" for cross-origin
      // backends; same-origin it is just a plain POST.
      const res = await fetch(CONSULT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify({ action: 'consult', messages: history }),
      })
      const data = await res.json()
      if (data.ok) {
        setMessages([...history, { role: 'model', text: data.reply }])
      } else if (data.error === 'not_configured') {
        setNotice(data.message || 'Consultation is not configured yet.')
        setMessages(messages)
      } else {
        setNotice(data.message || 'The model request failed. Try again.')
        setMessages(messages)
      }
    } catch (err) {
      setNotice('Could not reach the backend. Start it with python3 backend/server.py and refresh.')
      setMessages(messages)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>Consultation</h2>
      <p className="hint">
        Discuss the portfolio with the model — it sees the same live numbers
        as the Portfolio view. Educational discussion, not financial advice.
      </p>
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <p className="hint">Ask a question, or start with one of these:</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'msg user' : 'msg model'}>
            {m.text.split('\n').map((line, j) => (
              <span key={j}>{line}<br /></span>
            ))}
          </div>
        ))}
        {busy && <div className="msg model muted">Thinking…</div>}
      </div>
      {messages.length === 0 && (
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
      {notice && <p className="notice">{notice}</p>}
      <form
        className="chat-form"
        onSubmit={(e) => { e.preventDefault(); send(input) }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your portfolio…"
          disabled={busy}
        />
        <button type="submit" className="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
