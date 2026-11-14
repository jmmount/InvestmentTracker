// ---------------------------------------------------------------------------
// Investment Tracker — Apps Script backend (READ phase only)
//
// Bound to the "Investments (Responses)" workbook. Deploy as a Web App:
//   Deploy -> New deployment -> Web app
//   Execute as: Me
//   Who has access: Anyone
//
// The web app URL is the only thing the frontend knows. This script runs
// under the workbook owner's Google account, so NO credentials exist in the
// frontend or in this file — there is nothing secret here, and this file is
// safe to keep in git.
//
// doGet returns the portfolio as JSON in the shape the frontend's data
// layer uses (mirrors snapshot.py's latest.json):
//   - Holdings, shares and cost are aggregated here from the CleanData lots.
//   - Prices, Graham numbers and day/week moves come from the workbook's
//     MarketData tab, which the Python market_data functions populate
//     (~/workspace/investments/market_data/: prices.py, graham.py,
//     populate_market_data.py). CurrentValue pivot prices are the fallback
//     for any ticker with no MarketData row yet.
//   - A field the workbook has no data for is returned as null; the
//     frontend carries those from its snapshot seed as a last resort.
//
// Cost basis convention (Jason, 2026-11-12): cost counts CASH purchase lots
// only. Reinvested-dividend lots add shares and value, but not cost.
//
// There is deliberately NO doPost in this phase: purchase-ticket writes are
// a separate, later step that will add a write token check before appending.
// ---------------------------------------------------------------------------

var NAMES = {
  BAC: 'Bank of America Corporation',
  FBNDX: 'Fidelity Investment Grade Bond Fund',
  FCBFX: 'Fidelity Corporate Bond Fund',
  FNILX: 'Fidelity ZERO Large Cap Index Fund',
  FZILX: 'Fidelity ZERO International Index Fund',
  GOOGL: 'Alphabet Inc.',
  KO: 'Coca-Cola Company (The)',
  NVO: 'Novo Nordisk A/S',
  PR: 'Permian Resources Corporation',
  STRL: 'Sterling Infrastructure, Inc.',
  UMC: 'United Microelectronics Corporation',
  V: 'Visa Inc.'
};

var MUTUAL_FUNDS = { FBNDX: true, FCBFX: true, FNILX: true, FZILX: true };

function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var agg = aggregateLots_(ss);
  var byTicker = agg.byTicker;
  // The form's dropdown values are DERIVED from CleanData, never hardcoded:
  // a ticker or sector that appears in the lots shows up here automatically.
  var meta = {
    tickers: Object.keys(byTicker).sort(),
    sectors: agg.sectors.slice().sort(),
    purchase_types: agg.purchaseTypes
  };
  if (e && e.parameter && e.parameter.view === 'meta') {
    return ContentService
      .createTextOutput(JSON.stringify({ meta: meta }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var prices = readCurrentPrices_(ss);
  var market = readMarketData_(ss);

  var positions = [];
  var totalValue = 0, totalCost = 0, totalDividend = 0;
  var sectors = {};
  var marketAsOf = null;

  Object.keys(byTicker).forEach(function (ticker) {
    var a = byTicker[ticker];
    var m = market[ticker] || null;
    if (m && m.close_date && !marketAsOf) marketAsOf = m.close_date;
    // MarketData is the market source of record; the CurrentValue pivot
    // price is only the fallback for a ticker with no MarketData row yet.
    var price = (m && m.price !== null) ? m.price
              : ((ticker in prices) ? prices[ticker] : null);
    var value = (price === null) ? null : round2_(a.shares * price);
    var gain = (value === null) ? null : round2_(value - a.cost);
    var isFund = !!MUTUAL_FUNDS[ticker];
    var graham = m ? m.graham : null;
    var grahamNote = m ? (m.graham_note || '')
      : (isFund ? 'Mutual fund — no Graham number'
                : 'No market data yet for this ticker');
    positions.push({
      ticker: ticker,
      name: NAMES[ticker] || ticker,
      sector: a.sector,
      shares: round3_(a.shares),
      cost: round2_(a.cost),
      price: price,
      prev_close: m ? m.prev_close : null,
      day_change_pct: m ? m.day_change_pct : null,
      week_close: m ? m.week_close : null,
      week_change_pct: m ? m.week_change_pct : null,
      value: value,
      gain: gain,
      dividend_reinvested: round2_(a.dividend),
      gain_pct: (gain === null || a.cost === 0) ? null : round2_(gain / a.cost * 100),
      graham: graham,
      graham_note: grahamNote,
      below_graham: (graham !== null && price !== null) ? price < graham : false
    });
    totalCost += a.cost;
    totalDividend += a.dividend;
    if (value !== null) {
      totalValue += value;
      sectors[a.sector] = round2_((sectors[a.sector] || 0) + value);
    }
  });

  positions.sort(function (x, y) { return (y.value || 0) - (x.value || 0); });
  var totalGain = round2_(totalValue - totalCost);
  var buyCandidates = positions
    .filter(function (p) { return p.below_graham; })
    .map(function (p) { return p.ticker; });

  var payload = {
    as_of: Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd'),
    source: 'apps-script-read',
    total_value: round2_(totalValue),
    total_cost: round2_(totalCost),
    total_gain: totalGain,
    total_gain_pct: totalCost === 0 ? 0 : round2_(totalGain / totalCost * 100),
    cost_basis: 'cash purchases only; reinvested dividends excluded (Jason, 2026-11-12)',
    total_dividend_reinvested: round2_(totalDividend),
    sectors: sectors,
    buy_candidates: buyCandidates,
    market_as_of: marketAsOf,
    positions: positions,
    meta: meta
  };

  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

// CurrentValue pivot -> { TICKER: current share price }
function readCurrentPrices_(ss) {
  var sheet = ss.getSheetByName('CurrentValue');
  var rows = sheet.getDataRange().getValues();
  var tickerCol = -1, priceCol = -1;
  for (var c = 0; c < rows[0].length; c++) {
    var h = String(rows[0][c]).toLowerCase();
    if (h === 'ticker') tickerCol = c;
    if (h.indexOf('currentshareprice') !== -1) priceCol = c;
  }
  var prices = {};
  for (var r = 1; r < rows.length; r++) {
    var ticker = String(rows[r][tickerCol] || '').trim().toUpperCase();
    if (!ticker || ticker === 'GRAND TOTAL') continue;
    var p = toNumber_(rows[r][priceCol]);
    if (p !== null) prices[ticker] = p;
  }
  return prices;
}

// MarketData tab (written by the Python market_data functions:
// prices.py + graham.py via populate_market_data.py) ->
// { TICKER: { price, prev_close, day_change_pct, week_close,
//             week_change_pct, graham, graham_note, close_date } }
function readMarketData_(ss) {
  var sheet = ss.getSheetByName('MarketData');
  var out = {};
  if (!sheet) return out;
  var rows = sheet.getDataRange().getValues();
  var col = {};
  rows[0].forEach(function (h, i) { col[String(h).trim().toLowerCase()] = i; });
  for (var r = 1; r < rows.length; r++) {
    var row = rows[r];
    var ticker = String(row[col['ticker']] || '').trim().toUpperCase();
    if (!ticker) continue;
    out[ticker] = {
      price: toNumber_(row[col['price']]),
      prev_close: toNumber_(row[col['prevclose']]),
      day_change_pct: toNumber_(row[col['daychangepct']]),
      week_close: toNumber_(row[col['weekclose']]),
      week_change_pct: toNumber_(row[col['weekchangepct']]),
      graham: toNumber_(row[col['graham']]),
      graham_note: String(row[col['grahamnote']] || ''),
      close_date: String(row[col['closedate']] || '')
    };
  }
  return out;
}

// CleanData lots -> { byTicker: { TICKER: { shares, cost (cash only),
// dividend, sector } }, sectors: [...], purchaseTypes: [...] }
function aggregateLots_(ss) {
  var sheet = ss.getSheetByName('CleanData');
  var rows = sheet.getDataRange().getValues();
  var col = {};
  rows[0].forEach(function (h, i) { col[String(h).trim().toLowerCase()] = i; });
  var byTicker = {};
  var sectorSet = {};
  var typeList = [];
  for (var r = 1; r < rows.length; r++) {
    var row = rows[r];
    var ticker = String(row[col['ticker']] || '').trim().toUpperCase();
    if (!ticker) continue;
    var shares = toNumber_(row[col['number of shares']]) || 0;
    var price = toNumber_(row[col['purchase price']]) || 0;
    var type = String(row[col['purchase type']] || '').trim().toLowerCase();
    var typeRaw = String(row[col['purchase type']] || '').trim();
    var sector = String(row[col['sector']] || '').trim();
    if (typeRaw && typeList.indexOf(typeRaw) === -1) typeList.push(typeRaw);
    if (sector) sectorSet[sector] = true;
    if (!byTicker[ticker]) byTicker[ticker] = { shares: 0, cost: 0, dividend: 0, sector: sector };
    var a = byTicker[ticker];
    a.shares += shares;
    if (type === 'dividends') a.dividend += shares * price;
    else a.cost += shares * price; // 'Cash' — and any non-dividend lot counts as cost
    if (sector) a.sector = sector;
  }
  return { byTicker: byTicker, sectors: Object.keys(sectorSet), purchaseTypes: typeList };
}

function toNumber_(v) {
  if (typeof v === 'number') return v;
  if (v === null || v === undefined || v === '') return null;
  var n = Number(String(v).replace(/[$,]/g, '').trim());
  return isNaN(n) ? null : n;
}

function round2_(v) { return Math.round(v * 100) / 100; }
function round3_(v) { return Math.round(v * 1000) / 1000; }
