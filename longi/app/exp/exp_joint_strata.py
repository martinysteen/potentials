"""
exp_joint_strata.py - Step 2 of the stratification ("Bayes ladder") approach:
joint conditioning on two raw indicators.

Per day, stocks are split into within-day bins (default terciles) of indicator A
and independently of indicator B. For each (bin_A, bin_B) cell: empirical win
rate and loss rate (averaged across days, equal day weight) and total
observation count. Persistence: win rates recomputed separately on the older /
newer half of history (split at median daynum) — a real pattern keeps its
gradient in both halves.

These are honestly calibrated conditional probabilities by construction:
"P(win | A-bin, B-bin)" measured on thousands of embargo-free historical cells
(events are realized outcomes; indicators are same-day values — no look-ahead).

Bin direction: bin 1 = lowest raw values that day, bin K = highest. Remember
median_* files hold rank medians where LOW = strong momentum.

Flags: --ind-a (default beta3m), --ind-b (default median_30d),
--bins (default 3), --min-cells-per-day (default 100), --horizons (default 20d,50d).

Output: app/exp/output/exp_joint_strata_{ind_a}_x_{ind_b}.csv + printed tables.
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
from exp_indicator_lift import event_frame
from aux_winloss_shared import (
    TARGET_SPECS,
    ensure_files_exist,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint within-day stratification of two raw indicators.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=3)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--horizons", type=str, default="20d,50d")
    return parser.parse_args()


def load_indicator(name: str) -> pd.Series:
    path = PROD_OUTPUT_DIR / f"longi_{name}.csv"
    ensure_files_exist([path])
    return stack_non_null(read_indicator_matrix(path))


def within_day_bins(df: pd.DataFrame, col: str, n_bins: int) -> pd.Series:
    pct = df.groupby("daynum")[col].rank(method="first", pct=True)
    return np.minimum(((pct - 1e-12) * n_bins).astype(int), n_bins - 1) + 1  # bins 1..K


def build_trimmed_corner(ind_a: str = "beta3m", ind_b: str = "median_30d", bins: int = 10,
                         trim_ind: str = "vola100d", keep_frac: float = 0.5,
                         min_cells_per_day: int = 100) -> pd.DataFrame:
    """The survivor sample of the advice screen (see report 6g/6h): within-day
    top ind_a bin x bottom ind_b bin, then the lowest keep_frac of trim_ind
    ranked within each day's corner membership. Columns: ticker, daynum,
    val_a, val_b, trim_val."""
    a = load_indicator(ind_a).rename("val_a")
    b = load_indicator(ind_b).rename("val_b")
    ab = pd.concat([a, b], axis=1, join="inner").reset_index()
    ab.columns = ["ticker", "daynum", "val_a", "val_b"]
    sizes = ab.groupby("daynum")["val_a"].transform("size")
    ab = ab[sizes >= int(min_cells_per_day)].copy()
    ab["bin_a"] = within_day_bins(ab, "val_a", int(bins))
    ab["bin_b"] = within_day_bins(ab, "val_b", int(bins))
    corner = ab[(ab["bin_a"] == int(bins)) & (ab["bin_b"] == 1)].copy()

    trim = load_indicator(trim_ind).rename("trim_val").reset_index()
    trim.columns = ["ticker", "daynum", "trim_val"]
    corner = corner.merge(trim, on=["ticker", "daynum"], how="inner")
    corner["trim_pct"] = corner.groupby("daynum")["trim_val"].rank(method="first", pct=True)
    return corner[corner["trim_pct"] <= float(keep_frac)].drop(columns=["bin_a", "bin_b", "trim_pct"])


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]
    K = int(args.bins)

    print(f"exp_joint_strata.py: within-day {K}x{K} stratification of "
          f"{args.ind_a} (A) x {args.ind_b} (B)")
    print("  bin 1 = lowest raw values that day, bin "
          f"{K} = highest (median_* files: LOW = strong momentum rank)")

    a = load_indicator(args.ind_a).rename("val_a")
    b = load_indicator(args.ind_b).rename("val_b")
    ab = pd.concat([a, b], axis=1, join="inner").reset_index()
    ab.columns = ["ticker", "daynum", "val_a", "val_b"]

    out_rows: List[Dict[str, str]] = []
    for spec in specs:
        events = event_frame(spec)
        df = ab.merge(events, on=["ticker", "daynum"], how="inner")
        sizes = df.groupby("daynum")["val_a"].transform("size")
        df = df[sizes >= int(args.min_cells_per_day)].copy()
        if df.empty:
            print(f"  {spec.key}: no usable days - skipped")
            continue

        df["bin_a"] = within_day_bins(df, "val_a", K)
        df["bin_b"] = within_day_bins(df, "val_b", K)
        split = float(np.median(df["daynum"].unique()))
        df["half"] = np.where(df["daynum"] <= split, "h1", "h2")

        day_cell = df.groupby(["daynum", "bin_a", "bin_b"]).agg(
            win=("win_event", "mean"), loss=("loss_event", "mean")).reset_index()
        cell = day_cell.groupby(["bin_a", "bin_b"]).agg(
            win_rate=("win", "mean"), loss_rate=("loss", "mean")).reset_index()
        counts = df.groupby(["bin_a", "bin_b"]).size().rename("n").reset_index()
        cell = cell.merge(counts, on=["bin_a", "bin_b"])

        half_cell = df.groupby(["half", "bin_a", "bin_b", "daynum"])["win_event"].mean() \
                      .groupby(["half", "bin_a", "bin_b"]).mean().rename("win_rate").reset_index()

        n_days = df["daynum"].nunique()
        print(f"\n  {spec.key}: {len(df)} cells over {n_days} days "
              f"(win base {df['win_event'].mean():.1%}, loss base {df['loss_event'].mean():.1%})")
        print(f"    win% / loss% (n) - rows: {args.ind_a} bins, cols: {args.ind_b} bins")
        header = "      " + "".join(f"{'B' + str(bb):<22}" for bb in range(1, K + 1))
        print(header)
        for ba in range(1, K + 1):
            parts = []
            for bb in range(1, K + 1):
                r = cell[(cell["bin_a"] == ba) & (cell["bin_b"] == bb)]
                if r.empty:
                    parts.append(f"{'-':<22}")
                else:
                    r = r.iloc[0]
                    parts.append(f"{r['win_rate'] * 100:4.1f}/{r['loss_rate'] * 100:4.1f} ({int(r['n'])})".ljust(22))
            print(f"    A{ba}: " + "".join(parts))

        print(f"    persistence of win% (h1 -> h2) per cell:")
        for ba in range(1, K + 1):
            parts = []
            for bb in range(1, K + 1):
                r1 = half_cell[(half_cell["half"] == "h1") & (half_cell["bin_a"] == ba) & (half_cell["bin_b"] == bb)]
                r2 = half_cell[(half_cell["half"] == "h2") & (half_cell["bin_a"] == ba) & (half_cell["bin_b"] == bb)]
                v1 = r1["win_rate"].iloc[0] * 100 if not r1.empty else float("nan")
                v2 = r2["win_rate"].iloc[0] * 100 if not r2.empty else float("nan")
                parts.append(f"{v1:4.1f}->{v2:4.1f}".ljust(22))
            print(f"    A{ba}: " + "".join(parts))

        for _, r in cell.iterrows():
            h1r = half_cell[(half_cell["half"] == "h1") & (half_cell["bin_a"] == r["bin_a"]) & (half_cell["bin_b"] == r["bin_b"])]
            h2r = half_cell[(half_cell["half"] == "h2") & (half_cell["bin_a"] == r["bin_a"]) & (half_cell["bin_b"] == r["bin_b"])]
            out_rows.append({
                "horizon": spec.key, "ind_a": args.ind_a, "bin_a": str(int(r["bin_a"])),
                "ind_b": args.ind_b, "bin_b": str(int(r["bin_b"])), "n": str(int(r["n"])),
                "win_rate": format_cell(float(r["win_rate"])),
                "loss_rate": format_cell(float(r["loss_rate"])),
                "win_h1": format_cell(float(h1r["win_rate"].iloc[0]) if not h1r.empty else float("nan")),
                "win_h2": format_cell(float(h2r["win_rate"].iloc[0]) if not h2r.empty else float("nan")),
            })

    if out_rows:
        out_path = EXP_OUTPUT_DIR / f"exp_joint_strata_{args.ind_a}_x_{args.ind_b}.csv"
        cols = ["horizon", "ind_a", "bin_a", "ind_b", "bin_b", "n", "win_rate", "loss_rate", "win_h1", "win_h2"]
        pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
        print(f"\n  Written: {out_path.name}")

    append_manifest("exp_joint_strata.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "full joint history")
    print(f"\nSUCCESS: joint stratification complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
