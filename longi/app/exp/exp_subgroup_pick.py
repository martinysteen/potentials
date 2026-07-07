"""
exp_subgroup_pick.py - Small-purse sub-selection: if an investor can only buy
K of the day's survivors, does picking by an indicator beat picking blind?
Which chooser indicator picks best?

Motivation (SM): the win/loss label describes the group; investors who cannot
buy the whole list must pick 1-5 names. The procedure mirrors the strategy
work: build a promising group in steps (here 3: beta3m x median_30d corner +
vola100d trim), then prioritize within it.

Choosers (--choosers, comma-separated):
  rank        longi_rank, LOW = good (RankNow)
  median_*    rolling rank medians, LOW = good
  quotXXYY    speed indicator ma{XX}/ma{YY} computed on the fly from
              longi_ma{XX}.csv / longi_ma{YY}.csv, HIGH = good
              (e.g. quot1020, quot2050; SM's "Cross1020/2050" as a quotient) -
              candidate for a production longi_quot1020.csv module if it wins
  rsi         longi_rsi (RSI14), HIGH = good (momentum convention); the
              "bottom" rows double as the low-RSI pullback-entry reading
  other       any longi_{name}.csv, assumed LOW = good (a note is printed)

Method: full survivor history (build_trimmed_corner). Per chooser, day and K
in --pick-ks: "top" = best K by the chooser's direction, "bottom" = worst K;
days with fewer than K survivors contribute all members (no day skipped).
Shared baselines: the whole group and random-K (seed 42) - random-K is the
honest benchmark for a K-picker (group pooling over-weights fat days).
Realized win/loss/tail stats + h1 -> h2 persistence, both horizons.

Output: app/exp/output/exp_subgroup_pick.csv + printed comparison tables.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from exp_joint_strata import build_trimmed_corner, load_indicator
from exp_corner_trim import segment_stats
from aux_winloss_shared import (
    TARGET_SPECS,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"

MA_WINDOWS = ("10", "20", "50", "200")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Top/bottom/random K-pick from the daily survivor list.")
    parser.add_argument("--ind-a", type=str, default="beta3m")
    parser.add_argument("--ind-b", type=str, default="median_30d")
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--trim-ind", type=str, default="vola100d")
    parser.add_argument("--keep-frac", type=float, default=0.5)
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--choosers", type=str, default="rank,quot1020,quot2050,rsi")
    parser.add_argument("--pick-ks", type=str, default="1,3,5")
    parser.add_argument("--horizons", type=str, default="20d,50d")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def load_chooser(name: str) -> Tuple[pd.Series, bool]:
    """Return (values indexed by (ticker, daynum), low_is_good)."""
    if name.startswith("quot"):
        digits = name[4:]
        for i in range(1, len(digits)):
            wa, wb = digits[:i], digits[i:]
            if wa in MA_WINDOWS and wb in MA_WINDOWS:
                ma_a = load_indicator(f"ma{wa}").rename("ma_a")
                ma_b = load_indicator(f"ma{wb}").rename("ma_b")
                both = pd.concat([ma_a, ma_b], axis=1, join="inner")
                both = both[both["ma_b"] != 0]
                return (both["ma_a"] / both["ma_b"]).rename(name), False  # HIGH = good
        raise ValueError(f"cannot parse quotient chooser '{name}' into two MA windows {MA_WINDOWS}")
    if name == "rsi":
        return load_indicator(name), False  # HIGH = good (momentum convention)
    if name != "rank" and not name.startswith("median_"):
        print(f"  note: chooser '{name}' has no known direction - assuming LOW = good")
    return load_indicator(name), True  # rank / medians: LOW = good


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]
    pick_ks = [int(k) for k in args.pick_ks.split(",") if k.strip()]
    choosers = [c.strip() for c in args.choosers.split(",") if c.strip()]
    rng = np.random.default_rng(int(args.seed))

    print(f"exp_subgroup_pick.py: choosers = {choosers}, K in {pick_ks}, "
          f"days thinner than K contribute all members")

    survivors = build_trimmed_corner(args.ind_a, args.ind_b, args.bins,
                                     args.trim_ind, args.keep_frac, args.min_cells_per_day)
    survivors["rnd"] = rng.random(len(survivors))

    chooser_dir: Dict[str, bool] = {}
    for name in choosers:
        vals, low_is_good = load_chooser(name)
        col = vals.rename(f"ch_{name}").reset_index()
        col.columns = ["ticker", "daynum", f"ch_{name}"]
        survivors = survivors.merge(col, on=["ticker", "daynum"], how="left")
        chooser_dir[name] = low_is_good
        n_missing = int(survivors[f"ch_{name}"].isna().sum())
        if n_missing:
            print(f"  note: {n_missing} survivor rows lack a {name} value - "
                  f"excluded from {name} picks, kept in group/random")

    out_rows: List[Dict[str, str]] = []
    for spec in specs:
        gain = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / spec.target_file)).rename("gain")
        g = gain.reset_index()
        g.columns = ["ticker", "daynum", "gain"]
        hist = survivors.merge(g, on=["ticker", "daynum"], how="inner")
        if hist.empty:
            print(f"  {spec.key}: no realized history - skipped")
            continue

        rules: List[tuple] = [("(baseline)", "group", None, hist)]
        for K in pick_ks:
            rules.append(("(baseline)", f"random{K}", K, hist.sort_values("rnd").groupby("daynum").head(K)))
        for name in choosers:
            ranked = hist.dropna(subset=[f"ch_{name}"])
            best_first = ranked.sort_values(f"ch_{name}", ascending=chooser_dir[name])
            for K in pick_ks:
                rules.append((name, f"top{K}", K, best_first.groupby("daynum").head(K)))
                rules.append((name, f"bottom{K}", K, best_first[::-1].groupby("daynum").head(K)))

        n_days = hist["daynum"].nunique()
        print(f"\n  {spec.key} (win > {spec.win_threshold:.0f}%), {n_days} days:")
        print(f"    {'chooser':<12}{'rule':<10}{'n':>7}{'win%':>7}{'loss%':>7}{'<-10%':>7}"
              f"{'p10':>8}{'med':>7}{'mean':>7}  {'win h1->h2':<12}")
        for chooser, rule, K, seg in rules:
            s = segment_stats(seg, spec)
            print(f"    {chooser:<12}{rule:<10}{s['n']:>7}{s['win_rate']*100:>7.1f}{s['loss_rate']*100:>7.1f}"
                  f"{s['tail_10']*100:>7.1f}{s['p10']:>8.1f}{s['median']:>7.1f}{s['mean']:>7.1f}  "
                  f"{s['win_h1']*100:4.1f}->{s['win_h2']*100:4.1f}")
            out_rows.append({
                "horizon": spec.key, "chooser": chooser, "rule": rule,
                "K": str(K) if K else "", "n": str(s["n"]),
                "win_rate": format_cell(s["win_rate"]), "loss_rate": format_cell(s["loss_rate"]),
                "tail_10": format_cell(s["tail_10"]), "p10": format_cell(s["p10"]),
                "median": format_cell(s["median"]), "mean": format_cell(s["mean"]),
                "win_h1": format_cell(s["win_h1"]), "win_h2": format_cell(s["win_h2"]),
            })

    out_path = EXP_OUTPUT_DIR / "exp_subgroup_pick.csv"
    cols = ["horizon", "chooser", "rule", "K", "n", "win_rate", "loss_rate",
            "tail_10", "p10", "median", "mean", "win_h1", "win_h2"]
    pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
    print(f"\n  Written: {out_path.name}")

    append_manifest("exp_subgroup_pick.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "full survivor history")
    print(f"\nSUCCESS: subgroup pick complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
