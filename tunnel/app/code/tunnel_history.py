"""
Historical tunnels: the tunnel_diag fit for many end dates, ALL longi_price tickers, in ONE
long CSV indexed by [daynum, ticker]. No plots, no PDFs.

    python tunnel_history.py                       # every daynum -> ../output/history/ (production)
    python tunnel_history.py --days 20 --out /tmp/h   # development
    python tunnel_history.py --every 5             # every 5th daynum only (newest always in)

Row (D, T) is exactly what `tunnel_diag.py --ticker T --asof D` gives. Always a FULL rebuild
from the night's frozen input snapshot - never incremental (SM, 2026-10-23): PotDat is
corrected across the whole past (M&A, delistings, price fixes), so yesterday's rows can't be
trusted. The file is replaced atomically, so a failed run leaves the previous one in place.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from multiprocessing import Pool

import numpy as np
import pandas as pd

import tunnel_diag as td
from shared import config
from shared.datacheck import DataUnavailable
import preflight

_H = {}
def _init(X, dn, tk, p):
    _H.update(X=X, dn=dn, tk=tk, p=p)
def _day(j):
    """All tickers' tunnels for the end column j (index into dn). Only the last `lookback`
    columns can matter, so only they are passed (the full history if lookback = 0)."""
    X, dn, tk, p = _H['X'], _H['dn'], _H['tk'], _H['p']
    lo = max(0, j + 1 - p['lookback']) if p['lookback'] else 0
    return j, [td.find_tunnel(tk[i], X[i, lo:j + 1], dn[lo:j + 1], p) for i in range(len(tk))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(config.OUTPUT_ROOT / 'history'))
    ap.add_argument('--days', type=int, default=0, help='how many of the newest daynums to cover (default 0 = every daynum in longi_price; use e.g. 250 while developing)')
    ap.add_argument('--every', type=int, default=1, help='take every Nth daynum, counted back from the newest')
    ap.add_argument('--live', action='store_true', help='read the live repository, no snapshot')
    ap.add_argument('--stale-ok', action='store_true', help='fall back to the previous snapshot')
    ap.add_argument('--workers', type=int, default=os.cpu_count())
    ap.add_argument('--param', action='append', default=[], help='key=value, overrides DEFAULTS')
    a = ap.parse_args()

    p = dict(td.DEFAULTS)
    for kv in a.param:
        k, v = kv.split('=', 1)
        p[k] = type(td.DEFAULTS[k])(v)
    try:
        preflight.ensure_data('all', mode=preflight.mode_from_argv())
        prices, dates = td.load_prices()
    except DataUnavailable as exc:
        print(exc)
        return 1

    X, dn, tk = prices.to_numpy(float), prices.columns.to_numpy(), list(prices.index)
    first = max(len(dn) - a.days, 0) if a.days else 0
    ends = list(range(len(dn) - 1, first - 1, -a.every))[::-1]
    t0 = time.time()
    with Pool(max(1, a.workers), _init, (X, dn, tk, p)) as pool:
        days = dict(pool.imap_unordered(_day, ends, chunksize=1))
    print(f'{len(ends)} end dates x {len(tk)} tickers in {time.time() - t0:.0f}s')

    # same table as tunnel_diag's CSV, one block per end date, daynum in front of ticker
    results = [r for j in ends for r in days[j]]
    tab = td.tunnel_table(results, dn, dates)
    tab.insert(0, 'daynum', [int(dn[j]) for j in ends for _ in tk])
    tab = tab.rename(columns={'daynum': datetime.now().strftime(td.STAMP_FMT)})   # creation stamp top-left
    print(tab.iloc[:, 2].value_counts().to_dict())          # status counts

    os.makedirs(a.out, exist_ok=True)
    name = f'tunnels_history_LB{p["lookback"] or "all"}.csv'
    tmp = os.path.join(a.out, '.' + name + '.tmp')
    tab.to_csv(tmp, sep=';', decimal=',', index=False)
    os.replace(tmp, os.path.join(a.out, name))
    print(f'wrote {os.path.join(a.out, name)}: {len(tab)} rows')
    return 0


if __name__ == '__main__':
    sys.exit(main())
