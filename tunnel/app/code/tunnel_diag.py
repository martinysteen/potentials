#!/usr/bin/env python3
"""Tunnel diagnostic (ported from the 2026-10-06 reference prototype in ../../handoff/).

For every ticker: find the longest log-linear tunnel (trend channel) that ends at
the newest close, draw it, and tabulate it. Plotting and tabulating only:
no validation, no forecasting, no ranking.

Input: Longi/longi_price.csv + Cal.csv (+ the newest Strategy/StrategicStocks_<daynum>.csv)
from repositoryRTBI, read through preflight.py (vintage check, then a frozen snapshot in
app/data/input/) like every other consumer.

Usage:
    python tunnel_diag.py                               # StrategicStocks tickers -> app/output/
    python tunnel_diag.py --param lookback=50           # only the last 50 closes (default 100)
    python tunnel_diag.py --universe top [--top 100]    # best N of longi_rank.csv
    python tunnel_diag.py --universe all                # every longi_price ticker
    python tunnel_diag.py --ticker MSFT MU              # single/few tickers (+ PNG each)
    python tunnel_diag.py --plot-all                    # also draw tickers without tunnel
    python tunnel_diag.py --param touch_tol=0.05 --param min_supports=3
    python tunnel_diag.py --asof 2200                   # pretend daynum 2200 is "today"
    python tunnel_diag.py --stale-ok | --live           # input-guard modes, see preflight.py

Outputs in --out (default app/output/):
    tunnels_<date>_LB<lookback>[_strat|_topN].pdf   A4 portrait pages, 3 across x 6 down
    tunnels_<date>_LB<lookback>[_strat|_topN].csv   one row per ticker, ';' separated, ',' decimal
"""
import argparse, os, sys, time
from dataclasses import dataclass, asdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import ticker as mticker

from shared import config, data_loader
from shared.datacheck import DataUnavailable
import preflight

# --------------------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------------------
DEFAULTS = dict(
    l_min=20,             # shortest tunnel considered (trading days)
    lookback=100,         # only the most recent N closes are considered; 0 = full history
    touch_tol=0.10,       # a close touches a line if within this share of the band height
    cluster_gap=5,        # touches closer than this many trading days count as ONE support
    min_supports=2,       # supports required on EACH line
    min_span=0.50,        # first->last support on each line must span this share of the length
    slope_method='minwidth',  # 'minwidth' (narrowest band) or 'ols' (least squares)
    w_max=1.0,            # widest accepted tunnel (1.0 = 100 % lower->upper); 0 = no cap
)


@dataclass
class Tunnel:
    ticker: str
    status: str                  # tunnel | no_tunnel | insufficient_data
    length_td: int = 0           # tunnel length in trading days (number of closes)
    width_pct: float = np.nan    # % gain from lower to upper line
    slope20_pct: float = np.nan  # % gain per 20 trading days along the lines
    supports_upper: int = 0      # number of separate supports (touch clusters) on the upper line
    supports_lower: int = 0
    start_daynum: int | None = None
    end_daynum: int | None = None
    lower_start: float = np.nan  # price of each line at the first and last day:
    upper_start: float = np.nan  # with start/end daynum this redraws the plot exactly
    lower_end: float = np.nan
    upper_end: float = np.nan
    last_close: float = np.nan


# --------------------------------------------------------------------------------------
# Fitting
# --------------------------------------------------------------------------------------
def supports(mask, gap):
    """Group touching days into supports. A new support starts after > gap days without a touch."""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    return np.split(idx, np.flatnonzero(np.diff(idx) > gap) + 1)


def ols_slope(y):
    t = np.arange(y.size, dtype=float)
    tc = t - t.mean()
    return float((tc * (y - y.mean())).sum() / (tc * tc).sum())


def minwidth_slopes(y, l_min):
    """Slope of the narrowest all-containing band, for every trailing window length.

    Walk backwards from the newest close, building the upper and lower convex hull
    (monotone chain). After k points the stacks ARE the hulls of the newest k closes,
    so one pass serves every window. The narrowest vertical band always has the slope
    of one of the hull edges, so only those slopes are tried. Returns {L: slope}.
    """
    n = y.size
    up, lo, out = [], [], {}
    for i in range(n - 1, -1, -1):
        p = (float(i), float(y[i]))
        for h, sgn in ((up, 1), (lo, -1)):          # points arrive with decreasing t
            while len(h) >= 2:
                (x1, y1), (x2, y2) = h[-2], h[-1]
                if sgn * ((x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1)) <= 0:
                    h.pop()
                else:
                    break
            h.append(p)
        L = n - i
        if L >= l_min:
            pts = np.array(up + lo)
            cand = [np.diff(a[:, 1]) / np.diff(a[:, 0]) for a in map(np.array, (up, lo)) if len(a) >= 2]
            cand = np.concatenate(cand) if cand else np.array([0.0])
            r = pts[None, :, 1] - cand[:, None] * pts[None, :, 0]
            out[L] = float(cand[np.argmin(r.max(1) - r.min(1))])
    return out


def evaluate(y, b, p):
    """Measures for one window y (log closes, oldest->newest) with slope b."""
    n = y.size
    t = np.arange(n, dtype=float)
    r0 = y - b * t
    a = (r0.max() + r0.min()) / 2               # midline = centre of the band
    r = r0 - a
    hi, lo = r.max(), r.min()                   # lines touch the most extreme closes
    h = hi - lo
    width = float(np.exp(h) - 1)
    up = supports(r >= hi - p['touch_tol'] * h, p['cluster_gap'])
    dn = supports(r <= lo + p['touch_tol'] * h, p['cluster_gap'])
    span = lambda cl: (cl[-1][-1] - cl[0][0]) / (n - 1) if cl else 0.0
    ok = ((not p['w_max'] or width <= p['w_max'])
          and len(up) >= p['min_supports'] and len(dn) >= p['min_supports']
          and span(up) >= p['min_span'] and span(dn) >= p['min_span'])
    return dict(a=a, b=b, hi=hi, lo=lo, width=width, up=up, dn=dn, ok=ok)


def find_tunnel(ticker, closes, daynums, params=None):
    """closes/daynums oldest->newest. Longest passing window that ends at the newest close,
    searched only within the most recent `lookback` closes."""
    p = {**DEFAULTS, **(params or {})}
    good = np.isfinite(closes) & (closes > 0)
    if not good[-1]:
        return Tunnel(ticker, 'insufficient_data')
    bad = np.flatnonzero(~good)
    first = bad[-1] + 1 if bad.size else 0      # only the unbroken run up to today counts
    if p['lookback'] and first < closes.size - p['lookback']:
        first = closes.size - p['lookback']     # older data is not taken into account
    y_all, d_all = np.log(closes[first:]), daynums[first:]
    last = float(closes[-1])
    if y_all.size < p['l_min']:
        return Tunnel(ticker, 'insufficient_data', end_daynum=int(d_all[-1]), last_close=last)
    slopes = minwidth_slopes(y_all, p['l_min']) if p['slope_method'] == 'minwidth' else None
    best = None
    for L in range(p['l_min'], y_all.size + 1):
        y = y_all[-L:]
        ev = evaluate(y, slopes[L] if slopes else ols_slope(y), p)
        if ev['ok']:
            best = (L, ev)
    if best is None:
        return Tunnel(ticker, 'no_tunnel', end_daynum=int(d_all[-1]), last_close=last)
    L, ev = best
    line = lambda t, off: round(float(np.exp(ev['a'] + ev['b'] * t + off)), 4)
    return Tunnel(
        ticker, 'tunnel', length_td=L,
        width_pct=round(100 * ev['width'], 2),
        slope20_pct=round(100 * (np.exp(20 * ev['b']) - 1), 2),
        supports_upper=len(ev['up']), supports_lower=len(ev['dn']),
        start_daynum=int(d_all[-L]), end_daynum=int(d_all[-1]),
        lower_start=line(0, ev['lo']), upper_start=line(0, ev['hi']),
        lower_end=line(L - 1, ev['lo']), upper_end=line(L - 1, ev['hi']),
        last_close=last)


# --------------------------------------------------------------------------------------
# Plotting (the lines are rebuilt from the Tunnel record only)
# --------------------------------------------------------------------------------------
COLS, ROWS, A4 = 3, 6, (8.27, 11.69)
C_PRICE, C_CTX, C_LINE, C_MID, C_SUP = '#1f3b57', '0.70', '#2e8b57', '#c0392b', '#e67e22'


def draw_panel(ax, res, closes, dates, p=None):
    """closes: full price row (oldest->newest); dates: matching DatetimeIndex."""
    p = {**DEFAULTS, **(p or {})}
    x = np.arange(closes.size)                  # trading-day axis: straight lines stay straight
    ok = np.isfinite(closes)
    ax.set_yscale('log')
    if res.status != 'tunnel':
        ax.plot(x[ok], closes[ok], color='0.55', lw=0.6)
        ax.set_title(f'{res.ticker}  –  {res.status.replace("_", " ")}', fontsize=7, loc='left', color='0.4')
    else:
        L = res.length_td
        s = closes.size - L
        ctx = max(0, s - max(60, L // 2))       # some history before the tunnel, in grey
        t = np.arange(L)
        b = np.log(res.lower_end / res.lower_start) / (L - 1)
        lower = np.log(res.lower_start) + b * t
        upper = np.log(res.upper_start) + b * t
        xs = x[s:]
        ax.plot(x[ctx:s + 1], closes[ctx:s + 1], color=C_CTX, lw=0.6)
        ax.plot(xs, closes[s:], color=C_PRICE, lw=0.7)
        ax.plot(xs, np.exp(upper), color=C_LINE, lw=0.9)
        ax.plot(xs, np.exp(lower), color=C_LINE, lw=0.9)
        ax.plot(xs, np.exp((upper + lower) / 2), color=C_MID, lw=0.7, ls='--')
        y, h = np.log(closes[s:]), upper[0] - lower[0]
        for line, pick, side in ((upper, np.argmax, 1), (lower, np.argmin, -1)):
            r = y - line                        # one dot per support, at its most extreme close
            cl = supports(side * r >= -p['touch_tol'] * h - 1e-9, p['cluster_gap'])
            k = [c[pick(r[c])] for c in cl]
            ax.plot(xs[k], closes[s:][k], 'o', ms=2.2, color=C_SUP, mec='none', zorder=5)
        ax.set_title(res.ticker, fontsize=7.5, loc='left', fontweight='bold')
        ax.text(0.99, 1.02,
                f'L {L} d   W {res.width_pct:.0f}%   S {res.slope20_pct:+.1f}%/20d   '
                f'sup {res.supports_upper}/{res.supports_lower}',
                transform=ax.transAxes, ha='right', va='bottom', fontsize=5.6, color='0.25')
    # y axis: readable price labels on a log scale
    lo_, hi_ = ax.get_ylim()
    ax.yaxis.set_major_locator(mticker.MaxNLocator(5) if hi_ / lo_ < 3 else mticker.LogLocator(subs=(1, 2, 5)))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:.0f}' if v >= 100 else f'{v:.3g}'))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_ylim(lo_, hi_)
    # x axis: month labels at month starts, at most ~5 of them
    x0, x1 = ax.get_xlim()
    i0, i1 = max(0, int(np.ceil(x0))), min(len(dates) - 1, int(x1))
    months = (dates[i1].year - dates[i0].year) * 12 + dates[i1].month - dates[i0].month
    step = next(st for st in (1, 2, 3, 6, 12, 24) if months / st <= 5)
    starts = np.flatnonzero(dates.month[1:] != dates.month[:-1]) + 1
    ticks = [i for i in starts if i0 <= i <= i1 and (dates[i].year * 12 + dates[i].month - 1) % step == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i].strftime('%y-%m') for i in ticks])
    ax.tick_params(which='both', labelsize=5, length=2, pad=1)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.grid(alpha=0.25, lw=0.4)


def write_pdf(path, results, prices, dates, header, p=None, rows=ROWS, png_first=None):
    per = COLS * rows
    pages = [results[i:i + per] for i in range(0, len(results), per)] or [[]]
    with PdfPages(path) as pdf:
        for pi, chunk in enumerate(pages, 1):
            fig, axes = plt.subplots(rows, COLS, figsize=A4)
            fig.subplots_adjust(left=0.06, right=0.98, top=0.95, bottom=0.03, hspace=0.55, wspace=0.28)
            for ax in axes.flat[len(chunk):]:
                ax.axis('off')
            for ax, res in zip(axes.flat, chunk):
                draw_panel(ax, res, prices.loc[res.ticker].to_numpy(float), dates, p)
            fig.suptitle(f'{header}   –   page {pi}/{len(pages)}', fontsize=8, x=0.06, ha='left', y=0.985)
            pdf.savefig(fig)
            if png_first and pi == 1:
                fig.savefig(png_first, dpi=110)
            plt.close(fig)


def write_single_png(path, res, closes, dates, p=None):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    draw_panel(ax, res, closes, dates, p)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Data + CLI
# --------------------------------------------------------------------------------------
def load_prices(asof=None):
    """longi_price (row = ticker, column = daynum, newest first) -> DataFrame oldest->newest,
    plus a DatetimeIndex aligned with its columns. Reads whatever root preflight selected."""
    df = data_loader.load_longi(preflight.PRICES_FILE).copy()
    df.columns = df.columns.astype(int)
    df = df[sorted(df.columns)]
    if asof is not None:
        df = df[[c for c in df.columns if c <= asof]]
    cal = data_loader.load_cal()
    return df, pd.DatetimeIndex(cal.loc[df.columns].to_numpy())


def top_ranked(n, daynum):
    """The n best tickers of longi_rank.csv on `daynum` (rank 1 = best), best first.
    Tickers without a rank that day (indices) are left out."""
    rank = data_loader.load_longi(preflight.RANK_FILE)[str(daynum)].dropna()
    return list(rank.sort_values(kind='stable').index[:n])


_G = {}
def _init(X, dn, tk, p):
    _G.update(X=X, dn=dn, tk=tk, p=p)
def _one(i):
    return find_tunnel(_G['tk'][i], _G['X'][i], _G['dn'], _G['p'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(config.OUTPUT_ROOT))
    ap.add_argument('--live', action='store_true', help='read the live repository, no snapshot')
    ap.add_argument('--stale-ok', action='store_true', help='fall back to the previous snapshot')
    ap.add_argument('--universe', choices=('strategic', 'top', 'all'), default='strategic',
                    help='strategic = tickers of the newest StrategicStocks_<daynum>.csv (default); '
                         'top = the --top best of longi_rank.csv on the as-of day; '
                         'all = every longi_price ticker')
    ap.add_argument('--top', type=int, default=100, help='size of --universe top (default 100)')
    ap.add_argument('--ticker', nargs='*', help='explicit tickers, overrides --universe')
    ap.add_argument('--plot-all', action='store_true', help='also draw tickers without a tunnel')
    ap.add_argument('--rows', type=int, default=ROWS, help='plots down each A4 page (5 or 6)')
    ap.add_argument('--asof', type=int, help='treat this daynum as today')
    ap.add_argument('--workers', type=int, default=os.cpu_count())
    ap.add_argument('--param', action='append', default=[], help='key=value, overrides DEFAULTS')
    a = ap.parse_args()

    p = dict(DEFAULTS)
    for kv in a.param:
        k, v = kv.split('=', 1)
        p[k] = type(DEFAULTS[k])(v)
    universe = 'all' if a.ticker else a.universe
    try:
        preflight.ensure_data(universe, mode=preflight.mode_from_argv())
        prices, dates = load_prices(a.asof)
        if a.ticker:
            wanted = a.ticker
        elif universe == 'strategic':
            wanted = data_loader.load_strategic(preflight.required_files(universe)[-1])
        elif universe == 'top':
            wanted = top_ranked(a.top, prices.columns[-1])
        else:
            wanted = None
    except DataUnavailable as exc:
        print(exc)
        return 1
    if wanted:
        missing = [t for t in wanted if t not in prices.index]
        if missing:
            print(f'not in {preflight.PRICES_FILE}, skipped: {" ".join(missing)}')
        prices = prices.loc[[t for t in wanted if t in prices.index]]
    os.makedirs(a.out, exist_ok=True)
    tag = (dates[-1].strftime('%Y-%m-%d') + f'_LB{p["lookback"] or "all"}'
           + {'strategic': '_strat', 'top': f'_top{a.top}'}.get(universe, ''))

    t0 = time.time()
    X, dn, tk = prices.to_numpy(float), prices.columns.to_numpy(), list(prices.index)
    with Pool(max(1, a.workers), _init, (X, dn, tk, p)) as pool:
        results = pool.map(_one, range(len(tk)), chunksize=8)
    print(f'{len(results)} tickers in {time.time() - t0:.0f}s:',
          pd.Series([r.status for r in results]).value_counts().to_dict())

    # CSV: every ticker, European format like the rest of PotSystem
    tab = pd.DataFrame([asdict(r) for r in results])
    tab.insert(9, 'start_date', [dates[list(dn).index(d)].strftime('%Y-%m-%d') if pd.notna(d) else '' for d in tab.start_daynum])
    tab.insert(10, 'end_date', [dates[list(dn).index(d)].strftime('%Y-%m-%d') if pd.notna(d) else '' for d in tab.end_daynum])
    tab[['start_daynum', 'end_daynum']] = tab[['start_daynum', 'end_daynum']].astype('Int64')
    tab.to_csv(os.path.join(a.out, f'tunnels_{tag}.csv'), sep=';', decimal=',', index=False)

    # PDF: tunnels only (or all), alphabetical by ticker
    drawn = sorted([r for r in results if a.plot_all or r.status == 'tunnel'], key=lambda r: r.ticker)
    ptxt = '  '.join(f'{k}={v}' for k, v in p.items() if v != DEFAULTS[k]) or 'default parameters'
    header = (f'Tunnels ending {dates[-1]:%Y-%m-%d}  –  {sum(r.status == "tunnel" for r in results)} of '
              f'{len(results)} tickers ({universe})  –  {ptxt}')
    write_pdf(os.path.join(a.out, f'tunnels_{tag}.pdf'), drawn, prices, dates, header, p, a.rows,
              png_first=os.path.join(a.out, f'tunnels_{tag}_p1.png'))
    if a.ticker:
        for r in results:
            write_single_png(os.path.join(a.out, f'tunnel_{r.ticker}_{tag}.png'), r,
                             prices.loc[r.ticker].to_numpy(float), dates, p)
    print(data_loader.load_manifest_line())
    return 0


if __name__ == '__main__':
    sys.exit(main())
