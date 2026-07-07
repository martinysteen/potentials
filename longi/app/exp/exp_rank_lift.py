"""
exp_rank_lift.py - Within-day cross-sectional rank lift of the win/loss probabilities.

The decisive follow-up to exp_calibration.py: pooled calibration was flat, but the
strategy layer consumes the probability files as *rankings within a day*. This script
tests exactly that: per daynum, rank all scoreable stocks by stated p_win (resp. p_loss),
split into within-day deciles (decile 10 = highest stated probability that day), and
compare realized event rates across deciles. If decile 10 wins no more often than
decile 1, the model has no cross-sectional signal either.

Per (source, horizon, prob): a decile table (rates averaged across days, each day equal
weight) and a paired per-day top-minus-bottom lift summary (mean, median, share of days
positive - a sign test).

Flags:
--source S             'prod' or exp suffix. Repeatable. Default: prod.
--min-cells-per-day N  skip daynums with fewer scoreable cells (default: 100)

Output: app/exp/output/exp_rank_lift_{source}.csv + printed tables. Seconds, no fitting.
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
from exp_calibration import build_frame  # same cell semantics as the calibration test
from aux_winloss_shared import TARGET_SPECS

N_DECILES = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Within-day rank lift of stated probabilities.")
    parser.add_argument("--source", action="append", default=None,
                        help="'prod' or exp suffix (Hnone/H63/...). Repeatable.")
    parser.add_argument("--min-cells-per-day", type=int, default=100,
                        help="Skip daynums with fewer scoreable cells.")
    args = parser.parse_args()
    if not args.source:
        args.source = ["prod"]
    return args


def day_decile_rates(df: pd.DataFrame, prob_col: str, event_col: str, min_cells: int):
    """
    Per-day within-day decile split by stated probability.

    Returns (decile_frame, lift_series):
    - decile_frame: one row per decile - mean stated prob and realized rate,
      averaged across days with equal day weight
    - lift_series: per-day (top decile rate - bottom decile rate)
    """
    stated_by_decile: List[List[float]] = [[] for _ in range(N_DECILES)]
    rate_by_decile: List[List[float]] = [[] for _ in range(N_DECILES)]
    lifts: List[float] = []

    for _, day in df.groupby("daynum", sort=False):
        n = len(day)
        if n < min_cells:
            continue
        # method='first' gives a deterministic split despite heavy ties at 0.000/1.000;
        # rank pct is in (0,1], mapped to deciles 0..9
        pct = day[prob_col].rank(method="first", pct=True)
        decile = np.minimum(((pct - 1e-12) * N_DECILES).astype(int), N_DECILES - 1)

        rates = np.full(N_DECILES, np.nan)
        for d in range(N_DECILES):
            mask = decile == d
            if mask.sum() == 0:
                continue
            stated_by_decile[d].append(float(day.loc[mask.values, prob_col].mean()))
            r = float(day.loc[mask.values, event_col].mean())
            rate_by_decile[d].append(r)
            rates[d] = r
        if np.isfinite(rates[0]) and np.isfinite(rates[-1]):
            lifts.append(rates[-1] - rates[0])

    rows = []
    for d in range(N_DECILES):
        rows.append({
            "decile": d + 1,
            "mean_stated": float(np.mean(stated_by_decile[d])) if stated_by_decile[d] else float("nan"),
            "realized_rate": float(np.mean(rate_by_decile[d])) if rate_by_decile[d] else float("nan"),
        })
    return pd.DataFrame(rows), pd.Series(lifts, dtype=float)


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("exp_rank_lift.py: within-day cross-sectional rank lift (sandbox)")
    print(f"  Sources: {', '.join(args.source)} | min cells/day: {args.min_cells_per_day}")

    for source in args.source:
        out_rows: List[Dict[str, str]] = []
        for spec in TARGET_SPECS:
            df = build_frame(source, spec)
            if df.empty:
                print(f"  {source} {spec.key}: no scoreable cells - skipped")
                continue
            n_days = df.groupby("daynum").size()
            used_days = int((n_days >= args.min_cells_per_day).sum())
            print(f"\n  {source} {spec.key}: {len(df)} cells, {used_days} daynums used "
                  f"(base win rate {df['win_event'].mean():.1%}, base loss rate {df['loss_event'].mean():.1%})")

            for prob_col, event_col, label in [("p_win", "win_event", "win"), ("p_loss", "loss_event", "loss")]:
                table, lifts = day_decile_rates(df, prob_col, event_col, int(args.min_cells_per_day))
                print(f"    p_{label} deciles (within-day; decile 10 = highest stated that day):")
                print(f"      {'decile':<8}{'stated':<9}{'realized':<9}")
                for _, r in table.iterrows():
                    print(f"      {int(r['decile']):<8}{format_cell(r['mean_stated']):<9}"
                          f"{format_cell(r['realized_rate']):<9}")
                mean_lift = float(lifts.mean()) if len(lifts) else float("nan")
                med_lift = float(lifts.median()) if len(lifts) else float("nan")
                pos_share = float((lifts > 0).mean()) if len(lifts) else float("nan")
                print(f"      top-minus-bottom per-day lift: mean={mean_lift:+.3f} "
                      f"median={med_lift:+.3f} positive on {pos_share:.1%} of {len(lifts)} days")

                for _, r in table.iterrows():
                    out_rows.append({
                        "source": source, "horizon": spec.key, "prob": label,
                        "decile": str(int(r["decile"])),
                        "mean_stated": format_cell(r["mean_stated"]),
                        "realized_rate": format_cell(r["realized_rate"]),
                    })
                out_rows.append({
                    "source": source, "horizon": spec.key, "prob": label, "decile": "lift_top_minus_bottom",
                    "mean_stated": format_cell(mean_lift),
                    "realized_rate": format_cell(pos_share),
                })

        if out_rows:
            out_path = EXP_OUTPUT_DIR / f"exp_rank_lift_{source}.csv"
            pd.DataFrame(out_rows).to_csv(out_path, sep=";", index=False)
            print(f"\n  Written: {out_path.name} "
                  f"(lift row: mean_stated=mean lift, realized_rate=share of positive days)")

    wall = time.time() - t0
    append_manifest("exp_rank_lift.py", " ".join(sys.argv[1:]) or "(defaults)", wall,
                    "full-history per source")
    print(f"\nSUCCESS: rank-lift analysis complete in {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
