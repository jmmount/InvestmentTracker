#!/bin/bash
# Twice-daily investments refresh (DB-first) + push to the app server.
# 1. merge_pro_tables.py: mirror the server-only tables (watchlist,
#    watchlist_metrics, cash_positions) from the server DB into the local
#    DB first, so the push does not wipe cards/cash recorded on the server.
# 2. refresh_db.py: lots from investments.db, prices/Graham/names from
#    yfinance; writes market_data + portfolio_totals/snapshots (keyed by
#    the prices' trading date), latest.json and briefing charts.
# 3. scp the DB to the server (temp name + atomic rename, one .bak kept)
#    so the app serves the fresh data.
# Any failure aborts (set -e) and the caller reports it.
#
# Configuration — all env vars, with defaults for the standard layout
# (this script in refresh/ at the repo root, the app in backend/, the
# server reachable over Tailscale (its tailnet IP by default):
#   INVESTMENTS_DB      local DB (default: ../backend/investments.db)
#   REFRESH_BASE        output dir for latest.json/snapshots/charts/backups
#                       (default: this directory)
#   PRO_HOST            server ssh target (default: jasonmount@jasons-macbook-pro)
#   PRO_DIR             server backend dir (default: ~/code/InvestmentTracker/backend)
#   SSH_KEY             ssh private key (default: ~/.ssh/id_ed25519)
#   SSH_KNOWN_HOSTS     known-hosts file (default: ssh default)
#   SSH_PROXY_COMMAND   ProxyCommand for the ssh/scp calls (default: none)
set -e
cd "$(dirname "$0")"
INVESTMENTS_DB="${INVESTMENTS_DB:-$(pwd)/../backend/investments.db}"
export INVESTMENTS_DB
export REFRESH_BASE="${REFRESH_BASE:-$(pwd)}"
PRO_HOST="${PRO_HOST:-jasonmount@100.104.64.65}"
PRO_DIR="${PRO_DIR:-~/code/InvestmentTracker/backend}"
SSH_OPTS=(-o ConnectTimeout=25 -o IdentitiesOnly=yes -i "${SSH_KEY:-$HOME/.ssh/id_ed25519}" -o PasswordAuthentication=no)
[ -n "${SSH_KNOWN_HOSTS:-}" ] && SSH_OPTS+=(-o "UserKnownHostsFile=$SSH_KNOWN_HOSTS")
[ -n "${SSH_PROXY_COMMAND:-}" ] && SSH_OPTS+=(-o "ProxyCommand=$SSH_PROXY_COMMAND")
# 1. mirror the server-only tables into the local DB first
python3 merge_pro_tables.py || exit 1
# 2. refresh prices/totals/history
python3 refresh_db.py
# 3. push the DB to the server
scp "${SSH_OPTS[@]}" "$INVESTMENTS_DB" "$PRO_HOST:$PRO_DIR/investments.db.new"
ssh "${SSH_OPTS[@]}" "$PRO_HOST" "cd $PRO_DIR && cp -f investments.db investments.db.bak && mv -f investments.db.new investments.db && sqlite3 investments.db 'PRAGMA integrity_check;'"
