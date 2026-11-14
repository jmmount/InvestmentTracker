// ---------------------------------------------------------------------------
// Purchase Ticket configuration
//
// SHEET_ENDPOINT: optional. Paste the URL of a Google Apps Script web app
// (or any HTTPS endpoint) that appends a row to the "Investments
// (Responses)" workbook, and submitted tickets will be sent there as JSON.
//
// Leave it empty to use copy/download mode: each submitted ticket becomes a
// tab-separated row in exactly the workbook's column order, ready to paste
// into the RawData tab. Either way the columns match RawData/CleanData, so
// the daily investments snapshot keeps working unchanged.
// ---------------------------------------------------------------------------
export const SHEET_ENDPOINT = "";

// The values below mirror the workbook as of 2026-11-13.
export const TICKERS = [
  "BAC", "FBNDX", "FCBFX", "FNILX", "FZILX", "GOOGL",
  "KO", "NVO", "PR", "STRL", "UMC", "V",
];

export const SECTORS = [
  "Bonds", "Consumer", "Energy", "Financial",
  "Healthcare", "Industrial", "Mutual Funds", "Technology",
];

export const PURCHASE_TYPES = ["Cash", "Dividends"];
