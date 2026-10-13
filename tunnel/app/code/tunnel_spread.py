#!/usr/bin/env python3
"""Selection-wide plots of one tunnel run: how the slopes S (slope20_pct) spread, and how
S relates to the width W (width_pct). Tunnel rows only; read from the run's own CSV.

    tunnels_<tag>_hist.png   S in 8 buckets centred on mean(S): <-3s, -3s..-2s, ... , >+3s
                             (s = standard deviation of S; the end buckets are the outliers)
    tunnels_<tag>_SW.png     S (x) against W (y), every tunnel; the outliers are labelled

tunnel_diag.py calls write_spread() after each run. By hand, for runs already on disk:
    python tunnel_spread.py                    # every tunnels_*.csv in app/output/all/
    python tunnel_spread.py ../output/Rank_top100 path/to/tunnels_x.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from shared import config

LABELS = ['< −3s', '−3s…−2s', '−2s…−1s', '−1s…0', '0…+1s', '+1s…+2s', '+2s…+3s', '> +3s']
C_BAR, C_OUT, C_DOT, C_MEAN = '#1f3b57', '#c0392b', '#1f3b57', '#c0392b'


def buckets(S):
    """Mean, s, bucket edges and bucket index (0..7) per value. Lower edges are inclusive."""
    m, s = S.mean(), S.std()
    edges = np.array([m + k * s for k in range(-3, 4)])
    return m, s, edges, np.searchsorted(edges, S.to_numpy(), side='right')


def write_spread(csv_path):
    """Both PNGs next to csv_path. Returns their paths, or [] when there are too few tunnels."""
    csv_path = Path(csv_path)
    tab = pd.read_csv(csv_path, sep=';', decimal=',')
    t = tab[tab.status == 'tunnel']
    if len(t) < 3:
        return []
    S, W = t.slope20_pct, t.width_pct
    m, s, edges, k = buckets(S)
    out = (k == 0) | (k == 7)
    stem = csv_path.with_suffix('')
    title = f'{csv_path.stem}  –  {len(t)} tunnels of {len(tab)} tickers  –  mean S {m:+.2f} %/20d, s {s:.2f}'

    # 1) histogram: one bar per bucket (equal widths, the end buckets are open)
    n = np.bincount(k, minlength=8)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(range(8), n, color=[C_OUT if i in (0, 7) else C_BAR for i in range(8)], width=0.8)
    for b, c in zip(bars, n):
        ax.annotate(f'{c}\n{100 * c / len(t):.1f} %', (b.get_x() + b.get_width() / 2, c),
                    xytext=(0, 2), textcoords='offset points', ha='center', va='bottom', fontsize=7)
    rng = [f'< {edges[0]:.1f}'] + [f'{a:.1f} … {b:.1f}' for a, b in zip(edges[:-1], edges[1:])] + [f'≥ {edges[-1]:.1f}']
    ax.set_xticks(range(8))
    ax.set_xticklabels([f'{l}\n{r}' for l, r in zip(LABELS, rng)], fontsize=7)
    ax.set_xlabel('S = slope20_pct (% per 20 trading days)', fontsize=8)
    ax.set_ylabel('tickers', fontsize=8)
    ax.set_ylim(0, n.max() * 1.18)
    ax.set_title(title, fontsize=8, loc='left')
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    p_hist = Path(f'{stem}_hist.png')
    fig.savefig(p_hist, dpi=130)
    plt.close(fig)

    # 2) S vs W, the sigma band limits as guides, outliers in red with their ticker
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for e, kk in zip(edges, range(-3, 4)):
        ax.axvline(e, color=C_MEAN if kk == 0 else '0.75', lw=0.8 if kk == 0 else 0.6,
                   ls='-' if kk == 0 else '--', zorder=0)
        ax.text(e, 1.005, 'mean' if kk == 0 else f'{kk:+d}s', transform=ax.get_xaxis_transform(),
                ha='center', va='bottom', fontsize=6, color='0.4')
    ax.scatter(S[~out], W[~out], s=6, color=C_DOT, alpha=0.45, lw=0)
    ax.scatter(S[out], W[out], s=14, color=C_OUT, lw=0, zorder=3)
    for i, r in enumerate(t[out].sort_values('slope20_pct').itertuples()):
        ax.annotate(r.ticker, (r.slope20_pct, r.width_pct), xytext=(3, 3 if i % 2 else -8),
                    textcoords='offset points', fontsize=6, color=C_OUT)
    ax.set_xlabel('S = slope20_pct (% per 20 trading days)', fontsize=8)
    ax.set_ylabel('W = width_pct (% lower → upper line)', fontsize=8)
    ax.set_title(title, fontsize=8, loc='left', pad=14)
    ax.grid(alpha=0.25, lw=0.4)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    p_sw = Path(f'{stem}_SW.png')
    fig.savefig(p_sw, dpi=130)
    plt.close(fig)
    return [p_hist, p_sw]


def main(args):
    targets = args or [str(config.OUTPUT_ROOT / 'all')]
    csvs = []
    for a in map(Path, targets):
        csvs += sorted(a.glob('tunnels_*.csv')) if a.is_dir() else [a]
    for c in csvs:
        written = write_spread(c)
        print(c.name, '->', ', '.join(p.name for p in written) or 'skipped (fewer than 3 tunnels)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
