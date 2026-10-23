"""
On-demand tunnel report for a list of tickers and an end date: the standard assortment
(CSV, PDF, one tall PNG; a PNG per ticker for short lists) in a folder of its own.

    python tunnel_ondemand.py MSFT MU NOVO-B.CO --date 2026-09-30 [--name myrun]

Called by the MCP tool `tunnel_report` (repositoryRTBI/mcp/server.py), usable by hand.

Folder = <root>/<name>_<token> (token random, so the link can't be guessed; `name` just makes it
recognisable). Root = $TUNNEL_ONDEMAND_ROOT (default /srv/tunnel-reports), which Caddy serves
read-only at $TUNNEL_ONDEMAND_URL (default https://innovia.dk/tunnel-reports). It is NOT under
app/output/, so the nightly swap never touches it and repository.py never publishes it. Folders
older than KEEP_DAYS are removed at the start of every call.

The fit runs through `tunnel_diag.py --live` (reads the live repository; no input snapshot, so
it can't collide with the nightly run's), one report at a time (flock).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('TUNNEL_ONDEMAND_ROOT', '/srv/tunnel-reports'))
URL = os.environ.get('TUNNEL_ONDEMAND_URL', 'https://innovia.dk/tunnel-reports').rstrip('/')
KEEP_DAYS = 7
MAX_TICKERS = 200
TIMEOUT = 900                       # seconds; 200 tickers with plots take well under this


def _cleanup(root: Path):
    cutoff = time.time() - KEEP_DAYS * 86400
    for d in root.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def make_report(tickers: list[str], date: str | None = None, name: str | None = None) -> dict:
    """Run the report; returns {folder, url, files, rows} or raises RuntimeError with the reason."""
    tickers = list(dict.fromkeys(t.strip() for t in tickers if t.strip()))
    if not tickers:
        raise RuntimeError('no tickers given')
    if len(tickers) > MAX_TICKERS:
        raise RuntimeError(f'{len(tickers)} tickers; the limit is {MAX_TICKERS}')
    if date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise RuntimeError(f"date '{date}' is not YYYY-MM-DD")
    if name and not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
        raise RuntimeError('name may only hold letters, digits, _ and - (max 40)')
    ROOT.mkdir(parents=True, exist_ok=True)
    folder = ROOT / f"{name + '_' if name else ''}{secrets.token_urlsafe(9)}"

    with open(ROOT / '.lock', 'w') as lock:             # one report at a time
        fcntl.flock(lock, fcntl.LOCK_EX)
        _cleanup(ROOT)
        cmd = [sys.executable, str(HERE / 'tunnel_diag.py'), '--live', '--plot-all',
               '--out', str(folder), '--ticker', *tickers]
        if date:
            cmd += ['--asof-date', date]
        try:
            r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            shutil.rmtree(folder, ignore_errors=True)
            raise RuntimeError(f'timed out after {TIMEOUT}s')
    if r.returncode != 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise RuntimeError((r.stdout + r.stderr).strip()[-600:] or f'tunnel_diag.py exited {r.returncode}')

    files = sorted(p.name for p in folder.iterdir())
    csv = next(p for p in folder.iterdir() if p.suffix == '.csv')
    tab = pd.read_csv(csv, sep=';', decimal=',', dtype=str).fillna('')
    tab = tab.rename(columns={tab.columns[0]: 'ticker'})
    return dict(folder=str(folder), url=f'{URL}/{folder.name}', files=files,
                links=[f'{URL}/{folder.name}/{f}' for f in files],
                rows=tab.to_dict('records'), log=r.stdout.strip().splitlines()[-3:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tickers', nargs='+')
    ap.add_argument('--date', help='end date YYYY-MM-DD (default: newest)')
    ap.add_argument('--name')
    a = ap.parse_args()
    try:
        out = make_report(a.tickers, a.date, a.name)
    except RuntimeError as exc:
        print(f'ERROR: {exc}')
        return 1
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
