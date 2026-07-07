"""
exp_indicator_lift.py - Standalone predictive power of the RAW indicators.

Step 1 of the stratification ("Bayes ladder") approach: bypass the softmax model
entirely and ask, for each of the 20 production indicators, whether ranking stocks
by the raw indicator value within a day separates future winners from losers.

Per (indicator, horizon):
- join the indicator matrix with realized events (win: gain > 6%/10% via imported
  label_from_gain; loss: gain < 0) over the FULL available history
- per daynum (>= --min-cells-per-day cells), split stocks into within-day deciles
  by indicator value (decile 10 = highest value that day)
- realized event rate per decile (averaged across days, equal day weight),
  per-day top-minus-bottom lift, share of positive-lift days
- split-half persistence: mean lift in the older vs newer half of history
  (split at the median daynum). A real indicator has the same sign and similar
  magnitude in both halves.

Note: lift sign tells the direction (negative = LOW values of the indicator are
bullish). Discrete indicators (stepup40/100) get arbitrary tie-splitting within
deciles, which dilutes but does not bias their measured lift.

Flags: --min-cells-per-day (default 100), --horizons (default 20d,50d).

Output: app/exp/output/exp_indicator_lift.csv (win AND loss events; European CSV)
+ ranked win-event tables printed per horizon. No fitting; runs in ~a minute.
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
from aux_winloss_shared import (  # production helpers, read-only imports
    CLASS_NAMES,
    FEATURE_FILES,
    TARGET_SPECS,
    ensure_files_exist,
    label_from_gain,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"
N_DECILES = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Within-day decile lift of raw indicators.")
    parser.add_argument("--min-cells-per-day", type=int, default=100)
    parser.add_argument("--horizons", type=str, default="20d,50d")
    return parser.parse_args()


def event_frame(spec) -> pd.DataFrame:
    """(ticker, daynum, win_event, loss_event) for the full history of one target."""
    gain = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / spec.target_file)).rename("gain")
    df = gain.reset_index()
    df.columns = ["ticker", "daynum", "gain"]
    labels = df["gain"].map(lambda g: label_from_gain(float(g), spec.win_threshold, spec.loss_threshold))
    df["win_event"] = (labels == CLASS_NAMES[2]).astype(int)
    df["loss_event"] = (labels == CLASS_NAMES[0]).astype(int)
    return df.drop(columns="gain")


def indicator_lift(ind_stack: pd.Series, events: pd.DataFrame, event_col: str,
                   min_cells: int) -> Dict[str, float]:
    """Vectorized within-day decile lift for one indicator and one event type."""
    df = ind_stack.rename("value").reset_index()
    df.columns = ["ticker", "daynum", "value"]
    df = df.merge(events[["ticker", "daynum", event_col]], on=["ticker", "daynum"], how="inner")
    if df.empty:
        return {}

    sizes = df.groupby("daynum")["value"].transform("size")
    df = df[sizes >= min_cells]
    if df.empty:
        return {}

    pct = df.groupby("daynum")["value"].rank(method="first", pct=True)
    df["decile"] = np.minimum(((pct - 1e-12) * N_DECILES).astype(int), N_DECILES - 1)

    rates = df.groupby(["daynum", "decile"])[event_col].mean().unstack()
    if 0 not in rates.columns or N_DECILES - 1 not in rates.columns:
        return {}
    lifts = (rates[N_DECILES - 1] - rates[0]).dropna()
    if lifts.empty:
        return {}

    split = float(np.median(lifts.index.to_numpy(dtype=float)))
    h1 = lifts[lifts.index <= split]
    h2 = lifts[lifts.index > split]
    return {
        "n_days": float(len(lifts)),
        "d1_rate": float(rates[0].mean()),
        "d10_rate": float(rates[N_DECILES - 1].mean()),
        "mean_lift": float(lifts.mean()),
        "pos_share": float((lifts > 0).mean()),
        "lift_h1": float(h1.mean()) if len(h1) else float("nan"),
        "lift_h2": float(h2.mean()) if len(h2) else float("nan"),
    }


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]
    feature_paths = [PROD_OUTPUT_DIR / f for f in FEATURE_FILES]
    ensure_files_exist(feature_paths + [PROD_OUTPUT_DIR / spec.target_file for spec in specs])

    print("exp_indicator_lift.py: standalone within-day decile lift of raw indicators")
    print(f"  Indicators: {len(FEATURE_FILES)} | horizons: {', '.join(h for h in horizons)} | "
          f"min cells/day: {args.min_cells_per_day}")
    print("  Persistence: mean lift in older half (h1) vs newer half (h2); a real indicator")
    print("  keeps sign and rough magnitude in both halves.")

    out_rows: List[Dict[str, str]] = []
    results: Dict[str, List[Dict]] = {}

    for spec in specs:
        events = event_frame(spec)
        print(f"\n  Preparing events {spec.key}: {len(events)} cells, "
              f"win base {events['win_event'].mean():.1%}, loss base {events['loss_event'].mean():.1%}")
        res_list = []
        for fname in FEATURE_FILES:
            name = Path(fname).stem.replace("longi_", "")
            ind = stack_non_null(read_indicator_matrix(PROD_OUTPUT_DIR / fname))
            row = {"indicator": name}
            for event_col, label in [("win_event", "win"), ("loss_event", "loss")]:
                stats = indicator_lift(ind, events, event_col, int(args.min_cells_per_day))
                row[label] = stats
                if stats:
                    out_rows.append({
                        "horizon": spec.key, "event": label, "indicator": name,
                        "n_days": str(int(stats["n_days"])),
                        "d1_rate": format_cell(stats["d1_rate"]),
                        "d10_rate": format_cell(stats["d10_rate"]),
                        "mean_lift": format_cell(stats["mean_lift"]),
                        "pos_share": format_cell(stats["pos_share"]),
                        "lift_h1": format_cell(stats["lift_h1"]),
                        "lift_h2": format_cell(stats["lift_h2"]),
                    })
            res_list.append(row)
        results[spec.key] = res_list

    for spec in specs:
        ranked = sorted(results[spec.key],
                        key=lambda r: abs(r["win"].get("mean_lift", 0.0)) if r["win"] else 0.0,
                        reverse=True)
        print(f"\n  {spec.key} WIN-event lift, ranked by |mean per-day top-minus-bottom lift|:")
        print(f"    {'indicator':<16}{'d1':<8}{'d10':<8}{'lift':<9}{'pos%':<7}{'h1':<9}{'h2':<9}{'days':<6}")
        for r in ranked:
            s = r["win"]
            if not s:
                continue
            print(f"    {r['indicator']:<16}{s['d1_rate']:.3f}   {s['d10_rate']:.3f}   "
                  f"{s['mean_lift']:+.3f}   {s['pos_share']:.0%}    {s['lift_h1']:+.3f}   "
                  f"{s['lift_h2']:+.3f}   {int(s['n_days'])}")

    out_path = EXP_OUTPUT_DIR / "exp_indicator_lift.csv"
    cols = ["horizon", "event", "indicator", "n_days", "d1_rate", "d10_rate",
            "mean_lift", "pos_share", "lift_h1", "lift_h2"]
    pd.DataFrame(out_rows)[cols].to_csv(out_path, sep=";", index=False)
    print(f"\n  Written: {out_path.name}")

    append_manifest("exp_indicator_lift.py", " ".join(sys.argv[1:]) or "(defaults)",
                    time.time() - t0, "full indicator history")
    print(f"\nSUCCESS: indicator lift analysis complete in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
