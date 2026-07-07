"""
exp_screen_today.py - Daily candidate list from the joint-strata corner cell.

Selects the stocks that sit TODAY (newest daynum) in the best cell of the
within-day stratification: top bin of indicator A (default beta3m) x bottom bin
of indicator B (default median_30d, where low = strong momentum rank). With
--bins 10 this yields roughly 15-30 names - a sample small enough to examine
one by one.

Before listing, the script measures the corner cell's FULL historical record so
the list comes with honest expectations:
- win rate (gain > threshold), loss rate (gain < 0)
- "losing much" tail: share of outcomes below -5% and -10%, median and
  10th/90th percentile of realized gains
- persistence (older half vs newer half win rate)

Flags: --ind-a (default beta3m), --ind-b (default median_30d), --bins (default 10),
--min-cells-per-day (default 100), --focus-file (optional; marks those tickers).

Output: app/exp/output/exp_screen_{daynum}_{ind_a}{binA}_x_{ind_b}1.csv + printed list.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from exp_joint_strata import load_indicator, within_day_bins
from aux_winloss_shared import (
    TARGET_SPECS,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Today's corner-cell candidate list with honest historical stats.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--focus-file", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    K = int(args.bins)

    focus: set = set()
    if args.focus_file:
        focus = {t.strip() for t in Path(args.focus_file).read_text().splitlines() if t.strip()}

    a = load_indicator(args.ind_a).rename("val_a")
    b = load_indicator(args.ind_b).rename("val_b")
    ab = pd.concat([a, b], axis=1, join="inner").reset_index()
    ab.columns = ["ticker", "daynum", "val_a", "val_b"]
    sizes = ab.groupby("daynum")["val_a"].transform("size")
    ab = ab[sizes >= int(args.min_cells_per_day)].copy()
    ab["bin_a"] = within_day_bins(ab, "val_a", K)
    ab["bin_b"] = within_day_bins(ab, "val_b", K)
    corner = ab[(ab["bin_a"] == K) & (ab["bin_b"] == 1)]

    newest = int(ab["daynum"].max())
    print(f"exp_screen_today.py: corner cell = top-{K} bin of {args.ind_a} x bottom bin of {args.ind_b}")
    print(f"  Newest daynum: {newest}")

    # ---- Historical record of the corner cell -------------------------------
    print("\n  Historical record of this corner cell (what to expect):")
    for spec in TARGET_SPECS:
        gain = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / spec.target_file)).rename("gain")
        g = gain.reset_index()
        g.columns = ["ticker", "daynum", "gain"]
        hist = corner.merge(g, on=["ticker", "daynum"], how="inner")
        if hist.empty:
            continue
        split = float(np.median(hist["daynum"].unique()))
        win = (hist["gain"] > spec.win_threshold).mean()
        loss = (hist["gain"] < spec.loss_threshold).mean()
        h1 = hist[hist["daynum"] <= split]
        h2 = hist[hist["daynum"] > split]
        print(f"    {spec.key}: n={len(hist)} | win(> {spec.win_threshold:.0f}%)={win:.1%} "
              f"loss(<0)={loss:.1%} | gain<-5%: {(hist['gain'] < -5).mean():.1%}  "
              f"gain<-10%: {(hist['gain'] < -10).mean():.1%}")
        print(f"         gain distribution: p10={hist['gain'].quantile(0.1):+.1f}%  "
              f"median={hist['gain'].median():+.1f}%  p90={hist['gain'].quantile(0.9):+.1f}%  "
              f"mean={hist['gain'].mean():+.1f}%")
        print(f"         persistence: win rate h1={(h1['gain'] > spec.win_threshold).mean():.1%} "
              f"-> h2={(h2['gain'] > spec.win_threshold).mean():.1%}")

    # ---- Today's members ----------------------------------------------------
    today = corner[corner["daynum"] == newest].copy()
    vola = load_indicator("vola100d").rename("vola100d").reset_index()
    vola.columns = ["ticker", "daynum", "vola100d"]
    today = today.merge(vola, on=["ticker", "daynum"], how="left")
    today["focus"] = today["ticker"].map(lambda t: "1" if t in focus else "0")
    today = today.sort_values("val_a", ascending=False)

    print(f"\n  TODAY'S LIST (daynum {newest}): {len(today)} tickers in the corner cell")
    print(f"    {'ticker':<14}{args.ind_a:<10}{args.ind_b:<12}{'vola100d':<10}{'focus':<6}")
    for _, r in today.iterrows():
        print(f"    {r['ticker']:<14}{r['val_a']:<10.2f}{r['val_b']:<12.2f}"
              f"{(r['vola100d'] if pd.notna(r['vola100d']) else float('nan')):<10.2f}{r['focus']:<6}")

    focus_in = today[today["focus"] == "1"]["ticker"].tolist()
    print(f"\n  Focus tickers in today's list: {', '.join(focus_in) if focus_in else 'none'}")

    out_path = EXP_OUTPUT_DIR / f"exp_screen_{newest}_{args.ind_a}{K}_x_{args.ind_b}1.csv"
    out = today[["ticker", "focus", "val_a", "val_b", "vola100d"]].rename(
        columns={"val_a": args.ind_a, "val_b": args.ind_b})
    for col in [args.ind_a, args.ind_b, "vola100d"]:
        out[col] = out[col].map(lambda v: format_cell(float(v)) if pd.notna(v) else "")
    out.to_csv(out_path, sep=";", index=False)
    print(f"  Written: {out_path.name}")

    append_manifest("exp_screen_today.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, str(newest))
    print(f"\nSUCCESS: screen complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
