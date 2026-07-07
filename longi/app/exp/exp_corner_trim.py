"""
exp_corner_trim.py - Step 3 of the stratification ladder: trim the corner cell
by a third indicator (default vola100d) to attack the fat downside tail.

The decile corner (top beta3m bin x strongest median_30d bin) wins often
(44-48% vs ~28% base) but "loses much" too often (22-32% of outcomes < -10%).
Hypothesis: within the corner, the high-vola members supply the tail; keeping
the lower-vola part shrinks the tail faster than the win rate.

Method: rebuild the corner over full history, rank members by the trim
indicator WITHIN each day's corner, split at --keep-frac (default 0.5).
Compare three segments - full corner / kept (low trim-ind) / dropped (high
trim-ind) - on win rate, loss rate, tail shares (<-5%, <-10%), gain
percentiles, and h1 -> h2 persistence. Finally prints which of TODAY's corner
members survive the trim.

Flags: --ind-a (beta3m), --ind-b (median_30d), --bins (10),
--trim-ind (vola100d), --keep-frac (0.5), --min-cells-per-day (100),
--horizons (20d,50d), --focus-file (optional).

Output: app/exp/output/exp_corner_trim_{ind_a}{K}_x_{ind_b}1_by_{trim_ind}.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

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
    parser = argparse.ArgumentParser(description="Trim the joint-strata corner cell by a third indicator.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--trim-ind", type=str, default="vola100d")
    parser.add_argument("--keep-frac", type=float, default=0.5)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--horizons", type=str, default="20d,50d")
    parser.add_argument("--focus-file", type=str, default=None)
    return parser.parse_args()


def segment_stats(seg: pd.DataFrame, spec) -> Dict[str, float]:
    split = float(np.median(seg["daynum"].unique()))
    h1 = seg[seg["daynum"] <= split]
    h2 = seg[seg["daynum"] > split]
    return {
        "n": len(seg),
        "win_rate": (seg["gain"] > spec.win_threshold).mean(),
        "loss_rate": (seg["gain"] < spec.loss_threshold).mean(),
        "tail_5": (seg["gain"] < -5).mean(),
        "tail_10": (seg["gain"] < -10).mean(),
        "p10": seg["gain"].quantile(0.1),
        "median": seg["gain"].median(),
        "p90": seg["gain"].quantile(0.9),
        "mean": seg["gain"].mean(),
        "win_h1": (h1["gain"] > spec.win_threshold).mean(),
        "win_h2": (h2["gain"] > spec.win_threshold).mean(),
        "tail10_h1": (h1["gain"] < -10).mean(),
        "tail10_h2": (h2["gain"] < -10).mean(),
    }


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    K = int(args.bins)

    focus: set = set()
    if args.focus_file:
        focus = {t.strip() for t in Path(args.focus_file).read_text().splitlines() if t.strip()}

    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]

    print(f"exp_corner_trim.py: corner = top-{K} {args.ind_a} x bottom {args.ind_b}, "
          f"trimmed by within-corner {args.trim_ind} (keep lowest {args.keep_frac:.0%})")

    a = load_indicator(args.ind_a).rename("val_a")
    b = load_indicator(args.ind_b).rename("val_b")
    ab = pd.concat([a, b], axis=1, join="inner").reset_index()
    ab.columns = ["ticker", "daynum", "val_a", "val_b"]
    sizes = ab.groupby("daynum")["val_a"].transform("size")
    ab = ab[sizes >= int(args.min_cells_per_day)].copy()
    ab["bin_a"] = within_day_bins(ab, "val_a", K)
    ab["bin_b"] = within_day_bins(ab, "val_b", K)
    corner = ab[(ab["bin_a"] == K) & (ab["bin_b"] == 1)].copy()

    trim = load_indicator(args.trim_ind).rename("trim_val").reset_index()
    trim.columns = ["ticker", "daynum", "trim_val"]
    corner = corner.merge(trim, on=["ticker", "daynum"], how="inner")
    # rank the trim indicator WITHIN each day's corner membership
    corner["trim_pct"] = corner.groupby("daynum")["trim_val"].rank(method="first", pct=True)
    corner["kept"] = corner["trim_pct"] <= float(args.keep_frac)

    newest = int(corner["daynum"].max())
    out_rows: List[Dict[str, str]] = []

    for spec in specs:
        gain = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / spec.target_file)).rename("gain")
        g = gain.reset_index()
        g.columns = ["ticker", "daynum", "gain"]
        hist = corner.merge(g, on=["ticker", "daynum"], how="inner")
        if hist.empty:
            print(f"  {spec.key}: no history - skipped")
            continue

        segments = [("full", hist), ("kept", hist[hist["kept"]]), ("dropped", hist[~hist["kept"]])]
        print(f"\n  {spec.key} (win > {spec.win_threshold:.0f}%):")
        print(f"    {'segment':<9}{'n':>7}{'win%':>7}{'loss%':>7}{'<-5%':>7}{'<-10%':>7}"
              f"{'p10':>8}{'med':>7}{'p90':>7}{'mean':>7}  {'win h1->h2':<12}{'tail10 h1->h2':<14}")
        for name, seg in segments:
            s = segment_stats(seg, spec)
            print(f"    {name:<9}{s['n']:>7}{s['win_rate']*100:>7.1f}{s['loss_rate']*100:>7.1f}"
                  f"{s['tail_5']*100:>7.1f}{s['tail_10']*100:>7.1f}{s['p10']:>8.1f}{s['median']:>7.1f}"
                  f"{s['p90']:>7.1f}{s['mean']:>7.1f}  "
                  f"{s['win_h1']*100:4.1f}->{s['win_h2']*100:4.1f}   "
                  f"{s['tail10_h1']*100:4.1f}->{s['tail10_h2']*100:4.1f}")
            out_rows.append({
                "horizon": spec.key, "segment": name, "keep_frac": format_cell(float(args.keep_frac)),
                "n": str(s["n"]),
                "win_rate": format_cell(s["win_rate"]), "loss_rate": format_cell(s["loss_rate"]),
                "tail_5": format_cell(s["tail_5"]), "tail_10": format_cell(s["tail_10"]),
                "p10": format_cell(s["p10"]), "median": format_cell(s["median"]),
                "p90": format_cell(s["p90"]), "mean": format_cell(s["mean"]),
                "win_h1": format_cell(s["win_h1"]), "win_h2": format_cell(s["win_h2"]),
                "tail10_h1": format_cell(s["tail10_h1"]), "tail10_h2": format_cell(s["tail10_h2"]),
            })

    # ---- Today's survivors ---------------------------------------------------
    today = corner[corner["daynum"] == newest].sort_values("val_a", ascending=False)
    kept_today = today[today["kept"]]
    print(f"\n  TODAY (daynum {newest}): corner has {len(today)} members, "
          f"{len(kept_today)} survive the {args.trim_ind} trim")
    print(f"    {'ticker':<14}{args.ind_a:<10}{args.ind_b:<12}{args.trim_ind:<10}{'kept':<6}{'focus':<6}")
    for _, r in today.iterrows():
        print(f"    {r['ticker']:<14}{r['val_a']:<10.2f}{r['val_b']:<12.2f}{r['trim_val']:<10.2f}"
              f"{'1' if r['kept'] else '0':<6}{'1' if r['ticker'] in focus else '0':<6}")
    focus_kept = [t for t in kept_today["ticker"] if t in focus]
    print(f"\n  Focus tickers surviving the trim: {', '.join(focus_kept) if focus_kept else 'none'}")

    if out_rows:
        out_path = EXP_OUTPUT_DIR / f"exp_corner_trim_{args.ind_a}{K}_x_{args.ind_b}1_by_{args.trim_ind}.csv"
        cols = ["horizon", "segment", "keep_frac", "n", "win_rate", "loss_rate", "tail_5", "tail_10",
                "p10", "median", "p90", "mean", "win_h1", "win_h2", "tail10_h1", "tail10_h2"]
        pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
        print(f"  Written: {out_path.name}")

    append_manifest("exp_corner_trim.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "full corner history")
    print(f"\nSUCCESS: corner trim complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
