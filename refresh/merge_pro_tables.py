#!/usr/bin/env python3
"""Merge the Pro-only tables into the VM investments.db before a refresh push.

The Investment Tracker app records some data ONLY on the server that
serves it (the MacBook Pro): watchlist cards (watchlist, watchlist_metrics)
and the SPAXX cash position (cash_positions). The twice-daily refresh
pushes the local investments.db over the server's copy, which would wipe
those rows. This script mirrors those three tables from the server's DB
into the local DB first, so the pushed DB carries them. It runs before
refresh_db.py in refresh_and_push.sh, so the watchlist price companion
in refresh_db.py sees the watched tickers and fills in their
price/Graham rows the same run.

NOTE: once the refresh itself runs on the server, this script (and the
push step in refresh_and_push.sh) drops away — the refresh then reads
and writes the same DB the app serves. Until then, this keeps the
two-database setup from eating server-only rows.

The Pro is the only writer of these tables, so the sync is a full mirror:
CREATE the table from the Pro's schema if missing, DELETE the VM rows,
INSERT every Pro row. Lots, market_data and every other table are never
touched here.

Exit codes:
  0  merged OK, or nothing to merge, or the Pro was unreachable (warning
     printed; the push downstream will fail too in that case, so no wipe).
  1  failure (corrupt Pro copy, merge error) -- the caller must abort and
     NOT push. The VM DB is restored from the backup taken first.
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# Configuration — all env vars, with defaults for the standard layout
# (this script in refresh/ at the repo root, the app in backend/, the
# server reachable over Tailscale (default host is the server's tailnet
# IP, which is what the known-hosts pin covers; the Tailscale hostname
# jasons-macbook-pro works too if the key is pinned under that name).
# Plain ssh is the default: any machine on the tailnet reaches the
# server directly.
# The VM's egress-proxy setup is reproduced by setting SSH_PROXY_COMMAND
# and SSH_KNOWN_HOSTS in the environment; nothing proxy-specific is
# hardcoded here.
_HERE = os.path.dirname(os.path.abspath(__file__))
REFRESH_BASE = os.environ.get("REFRESH_BASE", _HERE)
VM_DB = os.environ.get(
    "INVESTMENTS_DB",
    os.path.join(os.path.dirname(_HERE), "backend", "investments.db"))
BACKUP_DIR = os.path.join(REFRESH_BASE, "backups")
PRO_HOST = os.environ.get("PRO_HOST", "jasonmount@100.104.64.65")
PRO_PATH = os.environ.get(
    "PRO_DB_PATH", "~/code/InvestmentTracker/backend/investments.db")
# Tables the app writes only on the Pro (in the order the app creates them).
PRO_TABLES = ["watchlist", "watchlist_metrics", "cash_positions"]


def ssh_opts():
    """ssh/scp options from the environment. Plain ssh by default."""
    opts = ["-o", "ConnectTimeout=25", "-o", "IdentitiesOnly=yes",
            "-i", os.environ.get(
                "SSH_KEY", os.path.expanduser("~/.ssh/id_ed25519")),
            "-o", "PasswordAuthentication=no"]
    known = os.environ.get("SSH_KNOWN_HOSTS")
    if known:
        opts += ["-o", f"UserKnownHostsFile={known}"]
    proxy = os.environ.get("SSH_PROXY_COMMAND")
    if proxy:
        opts += ["-o", f"ProxyCommand={proxy}"]
    return opts


SSH_OPTS = ssh_opts()


def fetch_pro_db(local_path):
    """scp the Pro DB to local_path. Returns True, or False if unreachable."""
    for attempt in (1, 2):
        r = subprocess.run(
            ["scp"] + SSH_OPTS + [f"{PRO_HOST}:{PRO_PATH}", local_path],
            capture_output=True, text=True)
        if r.returncode == 0:
            return True
        print(f"merge: scp attempt {attempt} failed: "
              f"{r.stderr.strip()}", file=sys.stderr)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vm-db", default=VM_DB)
    ap.add_argument("--pro-db", default=None,
                    help="use a local file instead of scp (testing)")
    ap.add_argument("--backup-dir", default=BACKUP_DIR)
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H%M%SZ")
    backup = None
    if not args.no_backup:
        os.makedirs(args.backup_dir, exist_ok=True)
        backup = os.path.join(
            args.backup_dir, f"investments-{stamp}-pre-merge.db")
        src = sqlite3.connect(f"file:{args.vm_db}?mode=ro", uri=True)
        dst = sqlite3.connect(backup)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"merge: VM DB backed up to {backup}")

    tmpdir = tempfile.mkdtemp(prefix="merge-pro-")
    pro_copy = os.path.join(tmpdir, "pro.db")
    try:
        if args.pro_db:
            shutil.copyfile(args.pro_db, pro_copy)
        else:
            if not fetch_pro_db(pro_copy):
                print("merge: WARNING: Pro unreachable, watchlist/cash "
                      "tables NOT merged (push downstream will fail too, "
                      "so nothing is wiped)", file=sys.stderr)
                return 0

        pro = sqlite3.connect(f"file:{pro_copy}?mode=ro", uri=True)
        ok = pro.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            print(f"merge: ERROR: Pro DB copy failed integrity_check: {ok}",
                  file=sys.stderr)
            return 1
        present = {r[0]: r[1] for r in pro.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name IN (%s)" % ",".join(
                "?" * len(PRO_TABLES)), PRO_TABLES)}
        pro.close()

        # No ATTACH: read the Pro rows with a separate connection and
        # write them into the VM DB. (ATTACH + DETACH inside the write
        # transaction tripped "database pro is locked" in testing.)
        pro = sqlite3.connect(f"file:{pro_copy}?mode=ro", uri=True)
        vm = sqlite3.connect(args.vm_db)
        try:
            with vm:
                for table in PRO_TABLES:
                    if table not in present:
                        print(f"merge: {table}: not on Pro, skipped")
                        continue
                    vm.execute(present[table].replace(
                        f"CREATE TABLE {table}",
                        f"CREATE TABLE IF NOT EXISTS {table}", 1))
                    cur = pro.execute(f"SELECT * FROM {table}")
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                    vm.execute(f"DELETE FROM {table}")
                    vm.executemany(
                        f"INSERT INTO {table} ({','.join(cols)}) "
                        f"VALUES ({','.join('?' * len(cols))})", rows)
                    print(f"merge: {table}: mirrored {len(rows)} "
                          f"row(s) from Pro")
        finally:
            pro.close()
            vm.close()

        vm = sqlite3.connect(f"file:{args.vm_db}?mode=ro", uri=True)
        ok = vm.execute("PRAGMA integrity_check").fetchone()[0]
        vm.close()
        if ok != "ok":
            raise RuntimeError(f"VM DB integrity_check failed: {ok}")
        print("merge: done, VM DB integrity ok")
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"merge: ERROR: {e}", file=sys.stderr)
        if backup and os.path.exists(backup):
            shutil.copyfile(backup, args.vm_db)
            print(f"merge: VM DB restored from {backup}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
