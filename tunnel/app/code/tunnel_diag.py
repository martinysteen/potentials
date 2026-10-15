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
    python tunnel_diag.py --universe growth [--sigma 2] # tunnels with S >= mean + 2s of all tickers
    python tunnel_diag.py --ticker MSFT MU              # single/few tickers (+ PNG each)
    python tunnel_diag.py --plot-all                    # also draw tickers without tunnel
    python tunnel_diag.py --param touch_tol=0.05 --param min_supports=3
    python tunnel_diag.py --asof 2200                   # pretend daynum 2200 is "today"
    python tunnel_diag.py --stale-ok | --live           # input-guard modes, see preflight.py

Outputs in --out (default app/output/):
    tunnels_<date>_LB<lookback>[_strat|_topN|_growthNs].pdf   A4 portrait, 3 across x 6 down
    tunnels_<date>_LB<lookback>[_strat|_topN|_growthNs].csv   one row per ticker, ';' / ','
    tunnels_<...>_hist.png / _SW.png                S histogram + S/W scatter (tunnel_spread.py)
"""
import argparse, contextlib, os, re, sys, time
from dataclasses import dataclass, asdict
from datetime import datetime
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
import tunnel_spread

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
    w_max=0.5,            # widest accepted tunnel (0.5 = 50 % lower->upper); 0 = no cap
)


STAMP_FMT = '%d-%m-%Y %H-%M'    # CSV top-left cell, as in PotDat.csv / longi_*.csv


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

    @property
    def close_pos(self):
        """Where the last close sits between the lines: 0 = lower, 1 = upper (NaN if no tunnel)."""
        h = self.upper_end - self.lower_end
        return (self.last_close - self.lower_end) / h if h > 0 else np.nan


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
NAMES = {}                                      # ticker -> company name (Stamdata), set by main()
SPEC_FS = 5.6                                   # font size of the L/W/S/close_pos line
NAME_LEN = 38                                   # characters of the name that fit above a panel's spec
C_BANNER = '#1f3b57'                            # grouped PDF: Sector2 banner / GICS divider colour


def common_scale(results, p):
    """One scale for every panel of a PDF, so widths and slopes compare by eye: the same
    log span vertically (fits the tallest tunnel, + 10 % margin) and the same number of
    trading days horizontally (1.25 x lookback, or x the longest tunnel). Returns
    (log_span, days) or None if nothing has a tunnel."""
    t = [r for r in results if r.status == 'tunnel']
    if not t:
        return None
    span = max(np.log(max(r.upper_start, r.upper_end) / min(r.lower_start, r.lower_end)) for r in t)
    return 1.1 * span, int(np.ceil(1.25 * (p['lookback'] or max(r.length_td for r in t))))


def draw_panel(ax, res, closes, dates, p=None, scale=None):
    """closes: full price row (oldest->newest); dates: matching DatetimeIndex.
    scale: (log_span, days) from common_scale(), or None to fit the panel to its own data."""
    p = {**DEFAULTS, **(p or {})}
    x = np.arange(closes.size)                  # trading-day axis: straight lines stay straight
    closes = np.where(closes > 0, closes, np.nan)   # a 0 would plunge the log axis to its floor
    ok = np.isfinite(closes)
    ax.set_yscale('log')
    if scale:
        ax.set_xlim(closes.size - scale[1] - 0.5, closes.size - 0.5)
    if res.status != 'tunnel':
        w = slice(-scale[1], None) if scale else slice(None)
        ax.plot(x[w][ok[w]], closes[w][ok[w]], color='0.55', lw=0.6)
        ax.set_title(f'{res.ticker}  –  {res.status.replace("_", " ")}', fontsize=7, loc='left', color='0.4')
    else:
        L = res.length_td
        s = closes.size - L
        ctx = max(0, closes.size - scale[1] if scale else s - max(60, L // 2))  # history, in grey
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
                f'W {res.width_pct:.0f}%   S20d {res.slope20_pct:+.1f}%   closePos {res.close_pos:.2f}',
                transform=ax.transAxes, ha='right', va='bottom', fontsize=SPEC_FS, color='0.25')
        if scale:                               # tunnel centred, same log span in every panel
            mid = (max(upper[0], upper[-1]) + min(lower[0], lower[-1])) / 2
            ax.set_ylim(np.exp(mid - scale[0] / 2), np.exp(mid + scale[0] / 2))
    name = NAMES.get(res.ticker)                # small print above the spec line (or the status title)
    if name:
        name = name if len(name) <= NAME_LEN else name[:NAME_LEN - 1].rstrip() + '…'
        ax.text(0.99, 1.125, name, transform=ax.transAxes, ha='right', va='bottom', fontsize=SPEC_FS, color='0.4')
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


def write_pdf(path, results, prices, dates, header, p=None, rows=ROWS, png_all=None, common=True, cols=COLS):
    """common: one scale for every panel (see common_scale); False fits each panel to its data.
    png_all: also write every page stacked top to bottom as ONE tall PNG (viewer-free reading)."""
    import io
    from PIL import Image
    set_name_len(cols)
    strips = []
    per = cols * rows
    pages = [results[i:i + per] for i in range(0, len(results), per)] or [[]]
    scale = common_scale(results, {**DEFAULTS, **(p or {})}) if common else None
    stxt = (f'same scale in every panel: {scale[1]} trading days wide, '
            f'bottom → top = +{100 * (np.exp(scale[0]) - 1):.0f} %') if scale else ''
    with PdfPages(path) as pdf:
        for pi, chunk in enumerate(pages, 1):
            fig, axes = plt.subplots(rows, cols, figsize=A4)
            fig.subplots_adjust(left=0.06, right=0.98, top=0.94, bottom=0.03, hspace=0.55, wspace=0.28)
            for ax in axes.flat[len(chunk):]:
                ax.axis('off')
            for ax, res in zip(axes.flat, chunk):
                draw_panel(ax, res, prices.loc[res.ticker].to_numpy(float), dates, p, scale)
            fig.suptitle(f'{header}   –   page {pi}/{len(pages)}', fontsize=8, x=0.06, ha='left', y=0.99)
            fig.text(0.06, 0.972, stxt, fontsize=6.5, ha='left', va='top', color='0.35')
            pdf.savefig(fig)
            if png_all:
                buf = io.BytesIO()
                fig.savefig(buf, dpi=110, format='png')
                strips.append(Image.open(buf).convert('RGB'))
            plt.close(fig)
    if strips:
        tall = Image.new('RGB', (strips[0].width, sum(s.height for s in strips)), 'white')
        y = 0
        for s in strips:
            tall.paste(s, (0, y))
            y += s.height
        tall.save(png_all, optimize=True)


def set_name_len(cols):
    """Narrower panels (more columns) fit a shorter company name above the spec line."""
    global NAME_LEN, SPEC_FS
    NAME_LEN = {1: 60, 2: 50, 3: 38}.get(cols, 30)
    SPEC_FS = 5.6 if cols <= 3 else 4.7         # the spec line must not run into the ticker title


def _slug(s):
    return re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_') or 'none'


@contextlib.contextmanager
def pdf_with_outline(path, outline):
    """PdfPages that also writes a bookmark tree. matplotlib has no API for this and writes
    the catalog (which must name /Outlines) at file creation, so for the duration of the
    `with` its PdfFile is swapped for a subclass that adds /Outlines + /PageMode to the
    catalog and writes the outline objects at finalize. Uses PdfFile internals
    (rootObject, reserveObject, writeObject, pageList) - matplotlib 3.10 in potsystem_env.
    outline: [(title, page_index, [(child_title, page_index), ...]), ...], page_index 0-based."""
    from matplotlib.backends import backend_pdf as b

    class OutlinePdfFile(b.PdfFile):
        def writeObject(self, obj, contents):
            if isinstance(contents, dict) and contents.get('Pages') is self.pagesObject \
                    and 'Kids' not in contents:             # the catalog
                self._outlines = self.reserveObject('outlines')
                contents = {**contents, 'Outlines': self._outlines, 'PageMode': b.Name('UseOutlines')}
            super().writeObject(obj, contents)

        def finalize(self):
            self.endStream()
            tops = [(t, pg, self.reserveObject('outline'), [(ct, cpg, self.reserveObject('outline'))
                                                           for ct, cpg in kids]) for t, pg, kids in outline]
            dest = lambda pg: [self.pageList[pg], b.Name('Fit')]
            for i, (t, pg, ref, kids) in enumerate(tops):
                d = {'Title': t, 'Parent': self._outlines, 'Dest': dest(pg)}
                if i: d['Prev'] = tops[i - 1][2]
                if i < len(tops) - 1: d['Next'] = tops[i + 1][2]
                if kids:
                    d.update(First=kids[0][2], Last=kids[-1][2], Count=-len(kids))     # collapsed
                self.writeObject(ref, d)
                for j, (ct, cpg, cref) in enumerate(kids):
                    c = {'Title': ct, 'Parent': ref, 'Dest': dest(cpg)}
                    if j: c['Prev'] = kids[j - 1][2]
                    if j < len(kids) - 1: c['Next'] = kids[j + 1][2]
                    self.writeObject(cref, c)
            self.writeObject(self._outlines, {'Type': b.Name('Outlines'), 'First': tops[0][2],
                                              'Last': tops[-1][2], 'Count': len(tops)})
            super().finalize()

    orig = b.PdfFile
    b.PdfFile = OutlinePdfFile
    try:
        with PdfPages(path) as pdf:
            yield pdf
    finally:
        b.PdfFile = orig


def _index_page(pdf, groups, where_g, where_s, header, total):
    """Page 1 of the grouped PDF: GICS (bold) with its Sector2s beneath, in two columns, each
    line a link target. Saves the page and returns [(rect_in_points, page_index), ...] for
    _add_links (links can only be attached once every target page exists)."""
    fig = plt.figure(figsize=A4)
    fig.suptitle(f'{header}   –   page 1/{total}', fontsize=8, x=0.06, ha='left', y=0.99)
    fig.text(0.06, 0.955, 'Index', fontsize=22, fontweight='bold', color=C_BANNER, va='center')
    fig.text(0.98, 0.955, 'click a line to jump  ·  bookmarks panel has the same tree', fontsize=7.5,
             color='0.45', ha='right', va='center')
    H_G, H_S, GAP = 0.0145, 0.0112, 0.009
    blocks = [(g, sum(len(r) for r in subs.values()), subs) for g, subs in groups.items()]
    height = lambda b: H_G + H_S * len(b[2]) + GAP
    half, acc, cut = sum(map(height, blocks)) / 2, 0.0, len(blocks)
    for i, b in enumerate(blocks):               # first block that would push column 1 past half
        if acc + height(b) / 2 > half:
            cut = i
            break
        acc += height(b)
    W, Hh = A4[0] * 72, A4[1] * 72
    links = []
    for col, (x0, x1, chunk) in enumerate(((0.06, 0.49, blocks[:cut]), (0.55, 0.98, blocks[cut:]))):
        y = 0.915
        for g, n, subs in chunk:
            fig.text(x0, y, g, fontsize=11, fontweight='bold', color=C_BANNER, va='center')
            fig.text(x1, y, f'{n} tunnels   p. {where_g[g] + 1}', fontsize=8, color='0.35', ha='right', va='center')
            links.append(([x0 * W, (y - H_G / 2) * Hh, x1 * W, (y + H_G / 2) * Hh], where_g[g]))
            y -= H_G
            for s2, res in subs.items():
                fig.text(x0 + 0.02, y, s2, fontsize=7.5, color='0.2', va='center')
                fig.text(x1, y, f'{len(res)}   p. {where_s[(g, s2)] + 1}', fontsize=7, color='0.45', ha='right', va='center')
                links.append(([x0 * W, (y - H_S / 2) * Hh, x1 * W, (y + H_S / 2) * Hh], where_s[(g, s2)]))
                y -= H_S
            y -= GAP
    pdf.savefig(fig)
    plt.close(fig)
    return links


def _add_links(pdf, links):
    """Attach the index page's links (annotations of page 0) once all pages exist."""
    from matplotlib.backends import backend_pdf as b
    f = pdf._file
    for rect, target in links:
        f._annotations[0][1].append({'Type': b.Name('Annot'), 'Subtype': b.Name('Link'), 'Rect': rect,
                                     'Border': [0, 0, 0], 'Dest': [f.pageList[target], b.Name('Fit')]})


def write_pdf_grouped(path, groups, prices, dates, header, p=None, rows=ROWS, png_dir=None, tag='',
                      cols=COLS):
    """groups: {gics: {sector2: [Tunnel, ...]}}, both levels in print order. A new GICS gets a
    divider page (its name large, its Sector2s listed). Within a GICS the panels just flow on,
    a new row for each Sector2, which opens with a dark full-width banner naming it - so a
    Sector2 change is loud only where it happens, not on every page. Panels fit their own data.
    png_dir: one tall PNG per GICS (its pages stacked, divider left out), undated names so a
    link in a Sheet stays stable across nights: <GICS>_<tag>.png.
    Page 1 is an index: every GICS and Sector2 is a clickable link to its page, and the same
    structure is the PDF's bookmark tree (GICS > Sector2, collapsed)."""
    import io
    from PIL import Image
    set_name_len(cols)
    BANNER, CAP = 0.45, rows + 0.45             # banner row height / page capacity, in panel rows
    plan = []                                   # ('divider', g, None) | ('page', g, [row, ...])
    for g, subs in groups.items():
        plan.append(('divider', g, None))
        page, used = [], 0.0
        for s2, res in subs.items():
            prow = [res[i:i + cols] for i in range(0, len(res), cols)]
            for j, r in enumerate(prow):
                need = (BANNER if j == 0 else 0) + 1      # a banner never ends a page alone
                if used + need > CAP + 1e-9:
                    plan.append(('page', g, page))
                    page, used = [], 0.0
                if j == 0:
                    page.append(('banner', s2, len(res)))
                    used += BANNER
                page.append(('panels', s2, r))
                used += 1
        if page:
            plan.append(('page', g, page))
    # where everything lands: plan item i is the PDF's page i + 2 (page 1 = the index), pageList[i + 1]
    where_g, where_s = {}, {}
    for i, (kind, g, page) in enumerate(plan):
        if kind == 'divider':
            where_g[g] = i + 1
        else:
            for row in page:
                if row[0] == 'banner':
                    where_s[(g, row[1])] = i + 1
    outline = [(g, where_g[g], [(s2, where_s[(g, s2)]) for s2 in subs]) for g, subs in groups.items()]
    total = len(plan) + 1
    strips = {}
    with pdf_with_outline(path, outline) as pdf:
        links = _index_page(pdf, groups, where_g, where_s, header, total)
        for pi, (kind, g, page) in enumerate(plan, 2):
            n_g = sum(len(r) for r in groups[g].values())
            if kind == 'divider':
                fig = plt.figure(figsize=A4)
                fig.text(0.5, 0.62, g, fontsize=64, fontweight='bold', ha='center', va='center', color=C_BANNER)
                fig.text(0.5, 0.52, f'{n_g} tunnels  –  {len(groups[g])} Sector2 groups',
                         fontsize=14, ha='center', va='center', color='0.35')
                fig.text(0.5, 0.46, '\n'.join(f'{name}  ({len(r)})' for name, r in groups[g].items()),
                         fontsize=10, ha='center', va='top', color='0.35', linespacing=1.5)
            else:
                ratios = [BANNER if r[0] == 'banner' else 1 for r in page]
                ratios.append(max(CAP - sum(ratios), 1e-3))   # spacer: every panel keeps one size
                fig = plt.figure(figsize=A4)
                gs = fig.add_gridspec(len(ratios), cols, height_ratios=ratios, left=0.06, right=0.98,
                                      top=0.94, bottom=0.03, hspace=0.55, wspace=0.28)
                for ri, row in enumerate(page):
                    if row[0] == 'banner':
                        ax = fig.add_subplot(gs[ri, :])
                        ax.axis('off')
                        ax.text(0, 0.5, f'{row[1]}', fontsize=20, fontweight='bold', ha='left', va='center',
                                color='white', transform=ax.transAxes,
                                bbox=dict(facecolor=C_BANNER, edgecolor='none', boxstyle='square,pad=0.35'))
                        ax.text(1, 0.5, f'{g}  –  {row[2]} tunnels', fontsize=10, ha='right', va='center',
                                color='0.35', transform=ax.transAxes)
                    else:
                        for ci, res in enumerate(row[2]):
                            draw_panel(fig.add_subplot(gs[ri, ci]), res,
                                       prices.loc[res.ticker].to_numpy(float), dates, p)
                if page[0][0] == 'panels':      # page opens mid-Sector2: say whose it is, quietly
                    fig.text(0.98, 0.972, f'{g}  –  {page[0][1]} (cont.)', fontsize=9, ha='right',
                             va='center', color='0.35')
            fig.suptitle(f'{header}   –   page {pi}/{total}', fontsize=8, x=0.06, ha='left', y=0.99)
            pdf.savefig(fig)
            if png_dir and kind == 'page':
                buf = io.BytesIO()
                fig.savefig(buf, dpi=110, format='png')
                strips.setdefault(g, []).append(Image.open(buf).convert('RGB'))
            plt.close(fig)
        _add_links(pdf, links)                  # every target page exists now
    for g, ims in strips.items():
        tall = Image.new('RGB', (ims[0].width, sum(i.height for i in ims)), 'white')
        y = 0
        for i in ims:
            tall.paste(i, (0, y))
            y += i.height
        tall.save(os.path.join(png_dir, f'{_slug(g)}_{tag}.png'), optimize=True)


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
    ap.add_argument('--universe', choices=('strategic', 'top', 'all', 'growth', 'zop', 'gics', 'flag'), default='strategic',
                    help='strategic = tickers of the newest StrategicStocks_<daynum>.csv (default); '
                         'top = the --top best of longi_rank.csv on the as-of day; '
                         'all = every longi_price ticker; '
                         'zop = tickers marked ZOP in longi_macd_Z on the as-of day; '
                         'flag = tickers whose Stamdata column --flag is true, indices left out; '
                         'gics = all, but the PDF/PNG/spread plots grouped by Stamdata GICS > Sector2; '
                         'growth = the tunnels of all tickers with S >= mean(S) + --sigma s')
    ap.add_argument('--top', type=int, default=100, help='size of --universe top (default 100)')
    ap.add_argument('--sigma', type=float, default=2.0, help='threshold of --universe growth (default 2)')
    ap.add_argument('--flag', default='SM_ejet', help='Stamdata column of --universe flag (default SM_ejet)')
    ap.add_argument('--ticker', nargs='*', help='explicit tickers, overrides --universe')
    ap.add_argument('--plot-all', action='store_true', help='also draw tickers without a tunnel')
    ap.add_argument('--rows', type=int, default=ROWS, help='plots down each A4 page (default 6)')
    ap.add_argument('--cols', type=int, default=COLS, help='plots across each A4 page (default 3)')
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
        NAMES.update(data_loader.load_stamdata()['Name'].dropna().astype(str).to_dict())
        if a.ticker:
            wanted = a.ticker
        elif universe == 'strategic':
            wanted = data_loader.load_strategic(preflight.required_files(universe)[-1])
        elif universe == 'top':
            wanted = top_ranked(a.top, prices.columns[-1])
        elif universe == 'zop':
            z = data_loader.load_longi(preflight.MACD_Z_FILE)[str(prices.columns[-1])]
            wanted = list(z.index[z == 'ZOP'])
        elif universe == 'flag':
            sd = data_loader.load_stamdata()
            if a.flag not in sd.columns:
                raise DataUnavailable(f'Stamdata.csv has no column {a.flag!r}')
            on = sd[a.flag].fillna('').str.strip().str.lower() == 'true'
            wanted = [t for t in sd.index[on] if not str(t).startswith('^') and sd.at[t, 'GICS'] != 'Index']
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
           + {'strategic': '_strat', 'top': f'_top{a.top}', 'zop': '_zop', 'gics': '_gics', 'flag': f'_{a.flag}', 'growth': f'_growth{a.sigma:g}s'}.get(universe, ''))

    t0 = time.time()
    X, dn, tk = prices.to_numpy(float), prices.columns.to_numpy(), list(prices.index)
    with Pool(max(1, a.workers), _init, (X, dn, tk, p)) as pool:
        results = pool.map(_one, range(len(tk)), chunksize=8)
    print(f'{len(results)} tickers in {time.time() - t0:.0f}s:',
          pd.Series([r.status for r in results]).value_counts().to_dict())
    if universe == 'growth':                    # same mean/s as the all-ticker histogram
        S = pd.Series([r.slope20_pct for r in results if r.status == 'tunnel'])
        cut = S.mean() + a.sigma * S.std()
        results = [r for r in results if r.status == 'tunnel' and r.slope20_pct >= cut]
        print(f'growth: S >= {S.mean():.2f} + {a.sigma:g} x {S.std():.2f} = {cut:.2f} %/20d -> {len(results)} tickers')

    # CSV: every ticker, European format like the rest of PotSystem
    tab = pd.DataFrame([asdict(r) for r in results])
    tab['close_pos'] = [r.close_pos for r in results]      # from the unrounded values
    tab.insert(9, 'start_date', [dates[list(dn).index(d)].strftime('%Y-%m-%d') if pd.notna(d) else '' for d in tab.start_daynum])
    tab.insert(10, 'end_date', [dates[list(dn).index(d)].strftime('%Y-%m-%d') if pd.notna(d) else '' for d in tab.end_daynum])
    tab[['start_daynum', 'end_daynum']] = tab[['start_daynum', 'end_daynum']].astype('Int64')
    # creation stamp in the top-left cell, the system-wide convention (PotDat, longi_*): it
    # survives an import into Sheets where file metadata does not
    # fixed decimals in the CSV only (SM, 2026-10-15): the plots are drawn from the unrounded results
    for cols, nd in ((['width_pct', 'slope20_pct'], 1),
                     (['lower_start', 'upper_start', 'lower_end', 'upper_end', 'last_close', 'close_pos'], 2)):
        for c in cols:
            tab[c] = tab[c].map(lambda v, nd=nd: '' if pd.isna(v) else f'{v:.{nd}f}'.replace('.', ','))
    if universe == 'gics':                      # the grouping, from Stamdata; blank -> '(none)'
        sd = data_loader.load_stamdata()
        for col in ('GICS', 'Sector2'):
            tab[col] = [(str(sd[col].get(t)) if pd.notna(sd[col].get(t)) else '') or '(none)' for t in tab.ticker]
    stamp = datetime.now().strftime(STAMP_FMT)   # same stamp in the CSV cell and the PDF/PNG header
    tab = tab.rename(columns={'ticker': stamp})
    tab.to_csv(os.path.join(a.out, f'tunnels_{tag}.csv'), sep=';', decimal=',', index=False)
    if universe == 'gics':                      # one hist file + one S/W file, a panel per GICS
        tunnel_spread.write_spread_grouped(os.path.join(a.out, f'tunnels_{tag}.csv'), 'GICS')
    elif not a.ticker:                          # selection-wide S histogram + S/W scatter
        tunnel_spread.write_spread(os.path.join(a.out, f'tunnels_{tag}.csv'))

    # PDF: tunnels only (or all), alphabetical by ticker
    drawn = sorted([r for r in results if a.plot_all or r.status == 'tunnel'], key=lambda r: r.ticker)
    ptxt = '  '.join(f'{k}={v}' for k, v in p.items() if v != DEFAULTS[k]) or 'default parameters'
    header = (f'Tunnels ending {dates[-1]:%Y-%m-%d}  –  created {stamp}  –  {sum(r.status == "tunnel" for r in results)} of '
              f'{len(results)} tickers ({universe})  –  {ptxt}')
    # Specialised selections (everything but `all`) also get all pages as ONE tall PNG, viewer-free
    # for a Sheet link. Undated name (tag minus the date) so the link stays stable.
    undated = tag[len(dates[-1].strftime('%Y-%m-%d')) + 1:]
    pdf_path = os.path.join(a.out, f'tunnels_{tag}.pdf')
    if universe == 'gics':
        # GICS > Sector2 sections; one tall PNG per GICS in png_GICS/ (a single one for the
        # whole selection would be ~60k px tall). Panels fit their own data, as in `all`.
        groups = {}
        for r in sorted(drawn, key=lambda r: r.ticker):
            groups.setdefault(tab.loc[tab.iloc[:, 0] == r.ticker, 'GICS'].iat[0], {}) \
                  .setdefault(tab.loc[tab.iloc[:, 0] == r.ticker, 'Sector2'].iat[0], []).append(r)
        groups = {g: dict(sorted(s.items(), key=lambda x: x[0].lower())) for g, s in sorted(groups.items(), key=lambda x: x[0].lower())}
        png_dir = os.path.join(a.out, 'png_GICS')
        os.makedirs(png_dir, exist_ok=True)
        write_pdf_grouped(pdf_path, groups, prices, dates, header, p, a.rows, png_dir=png_dir, tag=undated,
                          cols=a.cols)
    else:
        tallpng = universe != 'all' and not a.ticker
        png1 = os.path.join(a.out, 'tunnels_' + undated + '_latest.png') if tallpng else None
        write_pdf(pdf_path, drawn, prices, dates, header, p, a.rows,
                  png_all=png1, cols=a.cols,
                  common=universe != 'all')     # all: each panel its own scale (SM, 2026-10-13)
    if a.ticker:
        for r in results:
            write_single_png(os.path.join(a.out, f'tunnel_{r.ticker}_{tag}.png'), r,
                             prices.loc[r.ticker].to_numpy(float), dates, p)
    print(data_loader.load_manifest_line())
    return 0


if __name__ == '__main__':
    sys.exit(main())
