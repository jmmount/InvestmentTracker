import { useState } from 'react'
import { API_BASE } from '../config.js'

// Upload statement view: monthly Fidelity statement PDF -> lots.
//
// Upload -> the backend parses the PDF and returns a PREVIEW of
// exactly what would be written (each lot with ticker, date, shares,
// price and type, plus any rows that need review and will NOT be
// written). Nothing is written until Confirm is tapped, and only the
// checked lots go in. The PDF itself is never stored — the backend
// parses it from a temp file and deletes it right after.
const UPLOAD_URL = `${API_BASE}/api/upload-statement`
const CONFIRM_URL = `${API_BASE}/api/upload-statement/confirm`

export default function UploadStatement() {
  const [file, setFile] = useState(null)
  const [phase, setPhase] = useState('idle') // idle | uploading | preview | confirming | done
  const [preview, setPreview] = useState(null)
  const [checked, setChecked] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  function reset() {
    setFile(null)
    setPhase('idle')
    setPreview(null)
    setChecked({})
    setResult(null)
    setError('')
  }

  async function upload() {
    if (!file || phase === 'uploading') return
    setError('')
    setPhase('uploading')
    try {
      const form = new FormData()
      form.append('statement', file)
      const res = await fetch(UPLOAD_URL, { method: 'POST', body: form })
      const data = await res.json()
      if (!data.ok) {
        setError(data.message || 'The upload failed. Try again.')
        setPhase('idle')
        return
      }
      const initial = {}
      ;(data.lots || []).forEach((lot, i) => {
        initial[i] = lot.status === 'new'
      })
      setPreview(data)
      setChecked(initial)
      setPhase('preview')
    } catch (err) {
      setError('Could not reach the backend. Start it with python3 backend/server.py and refresh.')
      setPhase('idle')
    }
  }

  async function confirm() {
    if (!preview || phase === 'confirming') return
    const lots = (preview.lots || []).filter((lot, i) => checked[i])
    if (lots.length === 0) {
      setError('Nothing selected to insert — check at least one new lot.')
      return
    }
    setError('')
    setPhase('confirming')
    try {
      const res = await fetch(CONFIRM_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify({ statement_period: preview.statement_period, lots }),
      })
      const data = await res.json()
      if (!data.ok) {
        setError(data.message || 'The insert failed — nothing was written.')
        setPhase('preview')
        return
      }
      setResult(data)
      setPhase('done')
    } catch (err) {
      setError('Could not reach the backend — nothing was written. Try again.')
      setPhase('preview')
    }
  }

  const selected = preview ? (preview.lots || []).filter((lot, i) => checked[i]).length : 0
  const reviewRows = preview ? [...(preview.unhandled || [])] : []

  return (
    <section className="card">
      <h2>Upload statement</h2>
      <p className="hint">
        Pick a monthly Fidelity statement PDF. The app shows you exactly
        what it would write to the database first — nothing is inserted
        until you confirm. The PDF itself is never stored.
      </p>

      {phase === 'idle' || phase === 'uploading' ? (
        <>
          <div className="field">
            <label htmlFor="statement-file">Fidelity statement PDF</label>
            <input
              id="statement-file"
              type="file"
              accept=".pdf,application/pdf"
              disabled={phase === 'uploading'}
              onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
            />
          </div>
          <p>
            <button type="button" className="submit" disabled={!file || phase === 'uploading'} onClick={upload}>
              {phase === 'uploading' ? 'Reading the statement…' : 'Upload and preview'}
            </button>
          </p>
          {error && <p className="error">{error}</p>}
        </>
      ) : null}

      {phase === 'preview' && preview && (
        <>
          <p className="notice">
            Statement {preview.statement_period} — {preview.to_insert} lot{preview.to_insert === 1 ? '' : 's'} to
            insert, {(preview.lots || []).filter((l) => l.status !== 'new').length} already in the database.
            Check exactly what will be written, then confirm.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th></th><th>Ticker</th><th>Date</th><th>Shares</th><th>Price</th><th>Type</th><th>Status</th></tr>
              </thead>
              <tbody>
                {(preview.lots || []).map((lot, i) => (
                  <tr key={i}>
                    <td>
                      <input
                        type="checkbox"
                        checked={!!checked[i]}
                        disabled={lot.status !== 'new'}
                        onChange={(e) => setChecked({ ...checked, [i]: e.target.checked })}
                        aria-label={`Insert ${lot.ticker} ${lot.purchase_date}`}
                      />
                    </td>
                    <td>{lot.ticker}</td>
                    <td>{lot.purchase_date}</td>
                    <td>{lot.shares}</td>
                    <td>${lot.purchase_price}</td>
                    <td>{lot.purchase_type}</td>
                    <td>{lot.status === 'new' ? 'New' : lot.status === 'already_imported' ? 'Already imported' : 'Already in database'}</td>
                  </tr>
                ))}
                {(preview.lots || []).length === 0 && (
                  <tr><td colSpan="7" className="muted">No lots found in this statement.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {reviewRows.length > 0 && (
            <>
              <h3>Needs review — will NOT be written</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Date</th><th>Row</th><th>Reason</th></tr></thead>
                  <tbody>
                    {reviewRows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.date || ''}</td>
                        <td>{r.name || r.line || ''}</td>
                        <td>{r.reason || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {preview.activity_sections && preview.activity_sections.includes('Securities Bought & Sold') && (
            <p className="notice">
              This statement has a “Securities Bought &amp; Sold” section (cash buys/sales).
              Those rows are not inserted automatically — they need review first.
            </p>
          )}
          {error && <p className="error">{error}</p>}
          <p>
            <button type="button" className="submit" disabled={selected === 0 || phase === 'confirming'} onClick={confirm}>
              {phase === 'confirming' ? 'Inserting…' : `Insert ${selected} lot${selected === 1 ? '' : 's'}`}
            </button>
            {' '}
            <button type="button" onClick={reset}>Start over</button>
          </p>
        </>
      )}

      {phase === 'done' && result && (
        <>
          <p className="notice">
            Done — {result.inserted} lot{result.inserted === 1 ? '' : 's'} inserted
            {result.inserted_tickers && result.inserted_tickers.length > 0 ? ` (${result.inserted_tickers.join(', ')})` : ''}
            {result.already_in_db > 0 ? `, ${result.already_in_db} already in the database` : ''}
            {result.already_imported > 0 ? `, ${result.already_imported} already imported` : ''}.
            A backup of the database was taken before the write.
          </p>
          {result.new_ticker_warnings && result.new_ticker_warnings.length > 0 && (
            <p className="error">
              New ticker{result.new_ticker_warnings.length === 1 ? '' : 's'} with no sector yet: {result.new_ticker_warnings.join(', ')}.
            </p>
          )}
          <p>
            <button type="button" className="submit" onClick={reset}>Upload another statement</button>
          </p>
        </>
      )}
    </section>
  )
}
