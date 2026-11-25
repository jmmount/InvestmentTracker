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
// What the backend is used for TODAY: reads. The Portfolio view fetches
// the portfolio JSON from it (/api/portfolio), computed from the local
// SQLite store (investments.db). There is no seed or fallback data in
// this app any more: if the backend does not answer, the view says so
// instead of showing stale numbers.
//
// Ticket WRITES stay in copy/download mode until the write phase is
// built (a POST against the backend). Only then does TICKET_POST_ENABLED
// flip to true.
// ---------------------------------------------------------------------------
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {};

export const API_BASE = (ENV.VITE_API_URL || '').replace(/\/$/, '');

export const TICKET_POST_ENABLED = false;

// Offline FALLBACKS for the Purchase Ticket dropdowns. When the backend
// answers, its meta block — derived from the lots table's distinct
// tickers, sectors and purchase types — replaces these lists, so a new
// ticker or sector in the database appears in the form automatically.
// These constants only mirror the database as of 2026-11-13 for when
// the backend is not reachable.
export const TICKERS = [
  "BAC", "FBNDX", "FCBFX", "FNILX", "FZILX", "GOOGL",
  "KO", "NVO", "PR", "STRL", "UMC", "V",
];

export const SECTORS = [
  "Bonds", "Consumer", "Energy", "Financial",
  "Healthcare", "Industrial", "Mutual Funds", "Technology",
];

export const PURCHASE_TYPES = ["Cash", "Dividends"];
