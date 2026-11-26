# Investment Tracker refresh

The twice-daily portfolio refresh, versioned. It used to live only on the
machine that ran the cron; it now lives here so the pipeline is reviewable
and reproducible.

## What it does

1. **`merge_pro_tables.py`** — mirrors the tables the app writes only on
   the server (`watchlist`, `watchlist_metrics`, `cash_positions`) from
   the server's `investments.db` into the local copy, backup-first. The
   server is the only writer of those tables, so the sync is a full
   mirror. Fails closed (aborts the run) on a corrupt copy or merge
   error; skips with a warning only when the server is unreachable (the
   push below would fail too in that case, so nothing is wiped).
2. **`refresh_db.py`** — reads lots from `investments.db`, fetches
   prices, Graham numbers and company names from yfinance, and writes
   `market_data`, `portfolio_totals` and `portfolio_snapshots` keyed by
   the prices' actual trading date, plus `latest.json`, the dated
   snapshot JSON and the briefing charts. It also keeps `price_history`
   current (one row per ticker per run, plus a one-time 2-year daily
   backfill) and fills in price/Graham rows for watchlist tickers that
   are not holdings.
3. **`refresh_and_push.sh`** — runs the merge, then the refresh, then
   pushes the DB to the server (`scp` to a temp name, atomic rename,
   one `.bak` kept).

Cost basis is frozen by design: cash lots only, plus a $0.12
`COST_ADJUSTMENT` so headline totals keep matching Jason's settled
$4,956.29 (the seed lots sum to $4,956.17 at raw precision; the 12¢ is
display rounding — see `COST_ADJUSTMENT` in `refresh_db.py`). Do not
"fix" that number; it is pinned in `sync_meta` so the app backend reads
the same value.

## Running it

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r refresh/requirements.txt
# from refresh/:
python3 refresh_db.py            # refresh only, local DB
./refresh_and_push.sh            # merge + refresh + push to the server
```

On minimal Linux images, `refresh_db.py` needs timezone data for
`zoneinfo` — install the system `tzdata` package (or `pip install
tzdata`).

## Configuration

All paths and hosts are env vars; the defaults assume the standard
layout (this folder at the repo root, the app in `backend/`, the server
reachable over Tailscale (tailnet IP by default)).

| Variable | Default |
|---|---|
| `INVESTMENTS_DB` | `../backend/investments.db` (relative to `refresh/`) |
| `REFRESH_BASE` | this directory (outputs: `latest.json`, `snapshots/`, `charts/`, `backups/`) |
| `PRO_HOST` | `jasonmount@100.104.64.65` (the server's tailnet IP; the Tailscale hostname `jasons-macbook-pro` works too if the host key is pinned under that name) |
| `PRO_DB_PATH` | `~/code/InvestmentTracker/backend/investments.db` |
| `PRO_DIR` | `~/code/InvestmentTracker/backend` (used by the push script) |
| `SSH_KEY` | `~/.ssh/id_ed25519` |
| `SSH_KNOWN_HOSTS` | ssh default (set it to pin a known-hosts file) |
| `SSH_PROXY_COMMAND` | none — plain ssh by default; set it only if the refresh host needs a proxy to reach the server |

## What this PR does NOT change

- **The schedule has not moved.** The twice-daily cron (04:30 and
  16:30 ET) still runs the copies on the machine that has been running
  it. This PR versions the code; switching the cron over is a separate
  step.
- **The totals logic is untouched.** Only imports, paths and the
  `build_charts` extraction changed; `COST_ADJUSTMENT` and the
  holdings/watchlist math are byte-for-byte the same behavior.
- **No secrets, no database.** `investments.db`, `latest.json`,
  snapshots, charts and backups are outputs, not sources — they are
  gitignored (see `.gitignore`) and never committed.

## The next step (separate decision, not this PR)

Run the refresh on the server itself, so the app no longer depends on
another machine at all. On the server the merge and push steps drop
away — the refresh reads and writes the same DB the app serves — and
the 04:30/16:30 crons move with it. That needs a Pro-side scheduling
decision and is not part of this change.
