#!/usr/bin/env python3
"""SEC EDGAR fundamentals for the Watchlist view. Stdlib only.

One purpose: turn a company's XBRL facts into the watchlist metrics,
with nothing hardcoded per ticker. The backend (server.py) calls
resolve_ticker() to map a ticker to its CIK, fetch_companyfacts() to
pull the filing data, and compute_metrics() to build the series. The
computed series are cached in investments.db (watchlist_metrics);
EDGAR is only hit on add and on an explicit refresh, because filing
data only changes when a new 10-K or 10-Q lands.

Access rules (SEC fair access): every request sends a User-Agent
header identifying the app operator, and the client stays well under
the 10 requests/second limit (a 0.15 s gap between requests).

Keying rule — this bit us once, so it is stated plainly: every series
is keyed by the YEAR OF THE `end` DATE, never by `fy`. `fy` is the
filing year, not the value's year: a 2015 10-K reports its 2013, 2014
and 2015 comparative values all with fy=2015. Keying by `fy`
mislabels every series by up to two years. For any period the value
from the latest-filed 10-K / 10-Q wins, so restatements resolve to
the newest filing. Annual metrics use form 10-K fp FY only.
Quarterly metrics use 10-Q fp Q1-Q3; Q4 is not a 10-Q quarter, it
lives in the annual series.

Quarterly subtlety: a Q2/Q3 10-Q usually tags BOTH the year-to-date
cumulative revenue and the single-quarter revenue. The tagged
single-quarter entry wins; when a filer only tags the cumulative
figure, the single quarter is derived by differencing within the
fiscal year (Q2 = H1 - Q1, Q3 = 9M - H1, or 9M - Q1 - Q2 when the
H1 cumulative is absent) before any YoY is computed.

Tag notes, all verified live against Alphabet (CIK 1652044,
end-years 2013-2025) before this module was written:
  - Revenue falls back to RevenueFromContractWithCustomerExcludingAssessedTax
    for years where a filer does not tag plain Revenues (Alphabet
    switches tags mid-history; the merge gives all 13 years).
  - Operating cash flow is NetCashProvidedByUsedInOperatingActivities
    — NOT NetCashProvidedByOperatingActivities, which Alphabet never
    tags.
  - Short-term debt (DebtCurrent) is tagged only sporadically —
    Alphabet tags it for FY2014-16 only — so the debt total uses
    what is tagged and the metric carries a note saying so.
  - Revenue growth is two figures, not a 10-year quarterly series:
    the 10-year revenue CAGR (annual, latest year vs 10 years
    earlier) and quarterly YoY for the last four quarters only.
Corrected reference values (end-keyed, reproduced by the module):
  revenue FY2015 $74.99B -> FY2025 $402.84B, 10-yr CAGR 18.3%;
  last-4-quarters YoY 2025 Q3 +15.9% ($102.34B), 2026 Q1 +21.8%
  ($109.90B), 2026 Q2 +24.2% ($119.80B), 2026 Q3 +24.7% ($127.58B);
  current ratio FY2014 4.69 -> FY2025 2.01; free cash flow FY2013
  $11.30B -> FY2025 $73.27B; ROE FY2017 8.7% -> FY2025 35.7%;
  net margin FY2017 11.4% -> FY2025 32.8%; R&D FY2013 12.9% ->
  FY2025 15.2%.
EDGAR has no prices and no dividend history by period; this module
never pretends otherwise. Prices and Graham numbers come from the
tracker's own market_data (yfinance refresh), never from EDGAR.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import date

USER_AGENT = "InvestmentTracker/1.0 (Jason Mount, jason.mount@sunyempire.edu)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
MIN_REQUEST_GAP = 0.15  # seconds; SEC limit is 10 requests/second
TICKERS_TTL = 24 * 3600  # the tickers file changes rarely; cache a day

REVENUE_TAGS = ["Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax"]

_last_request = 0.0
_tickers_cache = {"fetched_at": 0.0, "map": {}}


class EdgarError(Exception):
    """An EDGAR lookup failed; .code is one of the API error strings."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _get_json(url):
    """One GET with the required User-Agent header, rate-limited."""
    global _last_request
    gap = time.time() - _last_request
    if gap < MIN_REQUEST_GAP:
        time.sleep(MIN_REQUEST_GAP - gap)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Host": "data.sec.gov" if "data.sec.gov" in url
                else "www.sec.gov",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _last_request = time.time()
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise EdgarError("edgar_unavailable",
                         f"SEC EDGAR returned HTTP {e.code} for {url}")
    except Exception as e:
        raise EdgarError("edgar_unavailable",
                         f"Could not reach SEC EDGAR: {e}"[:200])


def _tickers():
    """{TICKER: {"cik": int, "title": str}} from the SEC tickers
    file, cached a day."""
    now = time.time()
    if (now - _tickers_cache["fetched_at"] < TICKERS_TTL
            and _tickers_cache["map"]):
        return _tickers_cache["map"]
    data = _get_json(TICKERS_URL)
    mapping = {}
    for entry in data.values():
        ticker = (entry.get("ticker") or "").strip().upper()
        cik = entry.get("cik_str")
        if ticker and cik:
            mapping[ticker] = {"cik": int(cik),
                               "title": entry.get("title") or ""}
    _tickers_cache.update({"fetched_at": now, "map": mapping})
    return mapping


def resolve_ticker(ticker):
    """A ticker symbol -> {"cik", "title"} from the SEC tickers file,
    or None when the SEC has no such ticker. Never hardcodes a CIK."""
    if not isinstance(ticker, str):
        return None
    return _tickers().get(ticker.strip().upper())


def fetch_companyfacts(cik):
    """The raw companyfacts JSON for one CIK."""
    return _get_json(COMPANYFACTS_URL.format(cik=int(cik)))


# ---------------------------------------------------------------------------
# Metric computation — pure functions over a companyfacts dict.
# ---------------------------------------------------------------------------

def _annual_series(us_gaap, tag, fallback_tags=()):
    """{end_year: value} from 10-K FY entries, latest filed wins per
    end-year. Keyed by the year of `end`, NOT by `fy` — `fy` is the
    filing year, so a 2015 10-K carries its 2013-2015 comparatives
    all with fy=2015. The fallback tags fill only the years the
    primary tag lacks."""
    series = {}
    for t in [tag, *fallback_tags]:
        data = (us_gaap or {}).get(t)
        if not data:
            continue
        vals = (data.get("units") or {}).get("USD") or []
        best = {}
        for e in vals:
            if e.get("form") != "10-K" or e.get("fp") != "FY":
                continue
            try:
                year = int(e["end"][:4])
            except (KeyError, TypeError, ValueError):
                continue
            if year not in best or (e.get("filed") or "") > (
                    best[year].get("filed") or ""):
                best[year] = e
        for year, e in best.items():
            if year not in series:
                series[year] = e.get("val")
    return {y: v for y, v in sorted(series.items())
            if isinstance(v, (int, float))}


def _quarterly_series(us_gaap, tag, fallback_tags=()):
    """{(end_year, fp): single-quarter value} for Q1-Q3.

    A 10-Q for Q2/Q3 usually tags BOTH the year-to-date cumulative
    figure and the single-quarter figure. Prefer the tagged
    single-quarter entry (start/end spanning ~3 months); when a filer
    only tags the cumulative figure, derive the single quarter by
    differencing within the fiscal year (Q2 = H1 - Q1, Q3 = 9M - H1,
    or 9M - Q1 - Q2 when the H1 cumulative is absent). Q4 is not a
    10-Q quarter — it lives in the annual series. Within one class
    (single or cumulative) the primary tag wins, then the
    latest-filed entry, so restatements resolve to the newest filing."""
    groups = {}
    for rank, t in enumerate([tag, *fallback_tags]):
        data = (us_gaap or {}).get(t)
        if not data:
            continue
        vals = (data.get("units") or {}).get("USD") or []
        for e in vals:
            if e.get("fp") not in ("Q1", "Q2", "Q3"):
                continue
            if e.get("form") not in ("10-Q", "10-K"):
                continue
            try:
                start = date.fromisoformat(e["start"])
                end = date.fromisoformat(e["end"])
                year = end.year
            except (KeyError, TypeError, ValueError):
                continue
            g = groups.setdefault((year, e["fp"]),
                                  {"single": [], "ytd": []})
            entry = (rank, e.get("filed") or "", e.get("val"))
            if (end - start).days <= 100:
                g["single"].append(entry)
            else:
                g["ytd"].append(entry)

    def pick(entries):
        """Primary tag first, then the latest filing."""
        if not entries:
            return None
        rank = min(r for r, _, _ in entries)
        cands = [x for x in entries if x[0] == rank]
        return max(cands, key=lambda x: x[1])[2]

    single, ytd = {}, {}
    for key, g in groups.items():
        v = pick(g["single"])
        if isinstance(v, (int, float)):
            single[key] = v
        v = pick(g["ytd"])
        if isinstance(v, (int, float)):
            ytd[key] = v
    for (year, fp) in sorted(ytd):
        if (year, fp) in single:
            continue
        if fp == "Q1":
            single[(year, fp)] = ytd[(year, fp)]
        elif fp == "Q2" and (year, "Q1") in single:
            single[(year, fp)] = ytd[(year, fp)] - single[(year, "Q1")]
        elif fp == "Q3" and (year, "Q2") in ytd:
            single[(year, fp)] = ytd[(year, fp)] - ytd[(year, "Q2")]
        elif (fp == "Q3" and (year, "Q1") in single
              and (year, "Q2") in single):
            single[(year, fp)] = (ytd[(year, fp)]
                                  - single[(year, "Q1")]
                                  - single[(year, "Q2")])
    return dict(sorted(single.items()))


def _window(series, years=11):
    """The latest `years` points: the latest value plus the 10-year
    history behind it."""
    keys = sorted(series)[-years:]
    return {k: series[k] for k in keys}


def _metric(label, fmt, series, period_label, history_fmt=None):
    """One metric's wire shape: latest value + history. history_fmt
    overrides fmt for the history rows — the revenue CAGR's latest
    is a percentage but its history is annual revenue in dollars."""
    points = [{"period": period_label(k), "value": v}
              for k, v in series.items()]
    out = {"label": label, "format": fmt,
           "latest": points[-1] if points else None,
           "series": points}
    if history_fmt and history_fmt != fmt:
        out["history_format"] = history_fmt
    return out


def compute_metrics(facts, cik):
    """A companyfacts dict -> the watchlist metrics, the company
    name, its EDGAR facts URL, and any data-quality notes. Raises
    EdgarError('no_facts') when the filing carries no usable XBRL."""
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    if not us_gaap:
        raise EdgarError("no_facts",
                         "EDGAR returned no XBRL facts for this company.")
    entity_name = facts.get("entityName") or ""
    edgar_url = COMPANYFACTS_URL.format(cik=int(cik))

    revenue = _annual_series(us_gaap, "Revenues", REVENUE_TAGS[1:])
    revenue_q = _quarterly_series(us_gaap, "Revenues", REVENUE_TAGS[1:])
    ca = _annual_series(us_gaap, "AssetsCurrent")
    cl = _annual_series(us_gaap, "LiabilitiesCurrent")
    dc = _annual_series(us_gaap, "DebtCurrent")
    lt = _annual_series(us_gaap, "LongTermDebt",
                        ["LongTermDebtNoncurrent"])
    ltc = _annual_series(us_gaap, "LongTermDebtCurrent")
    eq = _annual_series(us_gaap, "StockholdersEquity")
    ni = _annual_series(us_gaap, "NetIncomeLoss")
    ocf = _annual_series(
        us_gaap, "NetCashProvidedByUsedInOperatingActivities")
    capex = _annual_series(
        us_gaap, "PaymentsToAcquirePropertyPlantAndEquipment")
    rnd = _annual_series(us_gaap, "ResearchAndDevelopmentExpense")

    notes = []
    if revenue and "RevenueFromContractWithCustomerExcludingAssessedTax" in us_gaap:
        used_fallback = any(
            year not in _annual_series(us_gaap, "Revenues")
            for year in revenue)
        if used_fallback:
            notes.append(
                "Revenue uses RevenueFromContractWithCustomerExcludingAssessedTax "
                "for years where the filer does not tag plain Revenues.")

    metrics = {}

    cr = {y: ca[y] / cl[y] for y in sorted(set(ca) & set(cl))
          if cl[y]}
    metrics["current_ratio"] = _metric(
        "Current ratio", "x", cr, lambda y: f"FY{y}")

    debt_years = sorted(set(lt) | set(ltc) | set(eq))
    de = {}
    for y in debt_years:
        if y not in eq or not eq[y]:
            continue
        # A year with no debt tag at all is unknown debt, not zero debt.
        if y not in lt and y not in ltc and y not in dc:
            continue
        debt = (dc.get(y) or 0) + (lt.get(y) or 0) + (ltc.get(y) or 0)
        de[y] = debt / eq[y]
    metrics["debt_to_equity"] = _metric(
        "Debt to equity", "x", de, lambda y: f"FY{y}")
    if dc:
        tagged = sorted(dc)
        if set(tagged) != set(de):
            notes.append(
                "Short-term debt (DebtCurrent) is only tagged for "
                f"FY{tagged[0]}–FY{tagged[-1]}; other years use "
                "long-term debt only.")
    elif de:
        notes.append(
            "Short-term debt (DebtCurrent) is not tagged by this filer; "
            "debt is long-term debt only.")

    fcf = {y: ocf[y] - capex[y]
           for y in sorted(set(ocf) & set(capex))}
    metrics["free_cash_flow"] = _metric(
        "Free cash flow", "usd", fcf, lambda y: f"FY{y}")

    # Metric 4 is two figures: the 10-year revenue CAGR (annual) and
    # quarterly revenue growth YoY for the last four quarters only.
    if len(revenue) >= 2:
        latest_year = max(revenue)
        base_year = latest_year - 10
        if base_year in revenue and revenue[base_year]:
            cagr = (revenue[latest_year] / revenue[base_year]) ** (1 / 10) - 1
            metrics["revenue_cagr_10y"] = {
                "label": "Revenue CAGR (10-yr)",
                "format": "pct",
                "latest": {"period": f"FY{base_year}–FY{latest_year}",
                           "value": cagr * 100},
                "series": [{"period": f"FY{y}", "value": v}
                           for y, v in _window(revenue).items()],
                "history_format": "usd",
            }
    growth = {}
    for (year, fp), v in sorted(revenue_q.items()):
        prev = revenue_q.get((year - 1, fp))
        if prev:
            growth[(year, fp)] = (v - prev) / prev * 100
    growth = dict(sorted(growth.items())[-4:])
    metrics["revenue_growth_yoy"] = _metric(
        "Revenue growth (YoY, last 4 quarters)", "pct", growth,
        lambda k: f"{k[0]} {k[1]}")

    roe = {}
    for y in sorted(set(ni) & set(eq)):
        if y - 1 in eq and eq[y - 1] and eq[y]:
            roe[y] = ni[y] / ((eq[y] + eq[y - 1]) / 2) * 100
    metrics["return_on_equity"] = _metric(
        "Return on equity", "pct", roe, lambda y: f"FY{y}")

    rnd_pct = {y: rnd[y] / revenue[y] * 100
               for y in sorted(set(rnd) & set(revenue)) if revenue[y]}
    metrics["rnd_share"] = _metric(
        "R&D as share of revenue", "pct", rnd_pct, lambda y: f"FY{y}")

    nm = {y: ni[y] / revenue[y] * 100
          for y in sorted(set(ni) & set(revenue)) if revenue[y]}
    metrics["net_margin"] = _metric(
        "Net margin", "pct", nm, lambda y: f"FY{y}")

    thin = [m["label"] for m in metrics.values()
            if len(m["series"]) < 3]
    if thin:
        notes.append(
            "Thin history (under 3 points) for: " + ", ".join(thin)
            + " — the filer does not tag those items every year.")

    return {"entity_name": entity_name, "edgar_url": edgar_url,
            "metrics": metrics, "notes": notes}
