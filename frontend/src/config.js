// ---------------------------------------------------------------------------
// Investment Tracker configuration
//
// API_BASE: the backend that serves the portfolio JSON (and the
// Consultation chat). Same-origin by default — backend/server.py serves
// the built frontend and /api/* from one port — so no .env is needed
// when the app runs behind the backend. Set VITE_API_URL only to point
// the frontend at a backend on another origin (e.g. Vite dev against a
// backend on :8768: VITE_API_URL=http://localhost:8768).
//
// What the backend is used for TODAY: reads, plus the statement upload.
// The Portfolio view fetches the portfolio JSON from it
// (/api/portfolio), computed from the local SQLite store
// (investments.db). There is no seed or fallback data in this app any
// more: if the backend does not answer, the view says so instead of
// showing stale numbers. New lots arrive through the Upload statement
// view, which POSTs a Fidelity statement PDF to
// /api/upload-statement for a preview, then to
// /api/upload-statement/confirm to insert the confirmed lots.
// ---------------------------------------------------------------------------
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {};

export const API_BASE = (ENV.VITE_API_URL || '').replace(/\/$/, '');
