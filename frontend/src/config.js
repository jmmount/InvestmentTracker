// ---------------------------------------------------------------------------
// Investment Tracker configuration
//
// SHEET_ENDPOINT: the URL of the Google Apps Script web app bound to the
// "Investments (Responses)" workbook (see apps-script/Code.gs). It is read
// from the VITE_SHEET_ENDPOINT environment variable — copy .env.example to
// .env and paste the URL there. .env is gitignored: the URL is a bearer
// capability for the read endpoint, so it never sits in the source or in
// git history.
//
// What the endpoint is used for TODAY: reads. The Portfolio view fetches
// the portfolio JSON from it (doGet) and falls back to the baked-in
// snapshot in data-portfolio.js when the endpoint is unset or unreachable.
//
// Ticket WRITES stay in copy/download mode until the write phase is built
// (a doPost with a write-token check in the Apps Script). Only then does
// TICKET_POST_ENABLED flip to true — setting the read URL must never turn
// ticket submission on by accident.
// ---------------------------------------------------------------------------
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {};

export const SHEET_ENDPOINT = ENV.VITE_SHEET_ENDPOINT || "";

export const TICKET_POST_ENABLED = false;

// Offline FALLBACKS for the Purchase Ticket dropdowns. When the read
// endpoint answers, its meta block — derived by the Apps Script from the
// CleanData tab's distinct tickers, sectors and purchase types — replaces
// these lists, so a new ticker or sector in the workbook appears in the
// form automatically. These constants only mirror the workbook as of
// 2026-11-13 for when the endpoint is not configured or unreachable.
export const TICKERS = [
  "BAC", "FBNDX", "FCBFX", "FNILX", "FZILX", "GOOGL",
  "KO", "NVO", "PR", "STRL", "UMC", "V",
];

export const SECTORS = [
  "Bonds", "Consumer", "Energy", "Financial",
  "Healthcare", "Industrial", "Mutual Funds", "Technology",
];

export const PURCHASE_TYPES = ["Cash", "Dividends"];
