"""
exp_calibration.py - Binary reliability of the stated win/loss probabilities.

Answers the decision-relevant question: when the model says p_win = x, how often
is the target actually reached (gain > 6% for 20d, > 10% for 50d)? Same for
p_loss vs the loss event (gain < 0).

Method: all historical cells where both the stated probability and the realized
gain exist are binned into fixed-width probability bins ([0.0,0.1) .. [0.9,1.0]).
Per bin: n, mean stated probability, realized event rate, gap (realized - stated).
A well-calibrated model has gap ~ 0 in every bin. Probabilities are taken AS
STATED in the files (no renormalization) - this is how a user reads them.

Event definitions come from the imported label_from_gain + TARGET_SPECS
(win event = class Win, loss event = class Loss) - threshold logic is never
duplicated here.

Flags:
--source S        'prod' or an exp suffix (Hnone, H63, ...). Repeatable. Default: prod.
--tickers-file F  optional; adds 'focus' scope rows for just those tickers,
                  alongside the 'all' scope.

Output: app/exp/output/exp_calibration_{source}.csv (European CSV, overwritten
per source per run) + printed reliability tables. Pure arithmetic, runs in seconds.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from aux_winloss_shared import (  # production helpers, read-only imports
    CLASS_NAMES,
    TARGET_SPECS,
    ensure_files_exist,
    label_from_gain,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"

N_BINS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Binary calibration of stated win/loss probabilities.")
    parser.add_argument("--source", action="append", default=None,
                        help="'prod' or exp suffix (Hnone/H63/...). Repeatable.")
    parser.add_argument("--tickers-file", type=str, default=None,
                        help="Optional focus list (one ticker per line) reported as extra scope.")
    args = parser.parse_args()
    if not args.source:
        args.source = ["prod"]
    return args


def prob_path(source: str, key: str, kind: str) -> Path:
    if source == "prod":
        return PROD_OUTPUT_DIR / f"longi_P{key}_{kind}.csv"
    return EXP_OUTPUT_DIR / f"exp_longi_P{key}_{kind}_{source}.csv"


def build_frame(source: str, spec) -> pd.DataFrame:
    """Long frame: ticker, daynum, p_win, p_loss (as stated), win_event, loss_event."""
    win_path = prob_path(source, spec.key, "win")
    loss_path = prob_path(source, spec.key, "loss")
    gain_path = PROD_OUTPUT_DIR / spec.target_file
    ensure_files_exist([win_path, loss_path, gain_path])

    p_win = stack_non_null(read_indicator_matrix(win_path)).rename("p_win")
    p_loss = stack_non_null(read_indicator_matrix(loss_path)).rename("p_loss")
    gain = stack_non_null(read_indicator_matrix(gain_path)).rename("gain")

    df = pd.concat([p_win, p_loss, gain], axis=1, join="inner").reset_index()
    df.columns = ["ticker", "daynum", "p_win", "p_loss", "gain"]

    labels = df["gain"].map(lambda g: label_from_gain(float(g), spec.win_threshold, spec.loss_threshold))
    df["win_event"] = (labels == CLASS_NAMES[2]).astype(int)   # Win
    df["loss_event"] = (labels == CLASS_NAMES[0]).astype(int)  # Loss
    return df


def reliability_rows(
    df: pd.DataFrame, source: str, horizon: str, scope: str
) -> List[Dict[str, str]]:
    """Fixed-width-bin reliability rows for p_win and p_loss."""
    rows: List[Dict[str, str]] = []
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    for prob_col, event_col, label in [("p_win", "win_event", "win"), ("p_loss", "loss_event", "loss")]:
        p = df[prob_col].to_numpy(dtype=float)
        e = df[event_col].to_numpy(dtype=int)
        bin_idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, N_BINS - 1)
        for b in range(N_BINS):
            mask = bin_idx == b
            n = int(mask.sum())
            if n == 0:
                mean_p, rate, gap = float("nan"), float("nan"), float("nan")
            else:
                mean_p = float(p[mask].mean())
                rate = float(e[mask].mean())
                gap = rate - mean_p
            rows.append({
                "source": source, "horizon": horizon, "scope": scope, "prob": label,
                "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}".replace(".", ","),
                "n": str(n),
                "mean_stated": format_cell(mean_p),
                "realized_rate": format_cell(rate),
                "gap": format_cell(gap),
            })
    return rows


def print_table(rows: List[Dict[str, str]], source: str, horizon: str, scope: str) -> None:
    for label in ["win", "loss"]:
        sub = [r for r in rows if r["prob"] == label and r["horizon"] == horizon and r["scope"] == scope]
        print(f"\n  {source} {horizon} [{scope}] - stated p_{label} vs realized {label}-event rate:")
        print(f"    {'bin':<10}{'n':<9}{'stated':<9}{'realized':<10}{'gap':<8}")
        for r in sub:
            print(f"    {r['bin']:<10}{r['n']:<9}{r['mean_stated']:<9}{r['realized_rate']:<10}{r['gap']:<8}")


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    focus: Optional[set] = None
    if args.tickers_file:
        focus = {t.strip() for t in Path(args.tickers_file).read_text().splitlines() if t.strip()}

    print("exp_calibration.py: binary reliability of stated probabilities (sandbox)")
    print(f"  Sources: {', '.join(args.source)} | bins: {N_BINS} fixed-width"
          + (f" | focus tickers: {len(focus)}" if focus else ""))

    for source in args.source:
        all_rows: List[Dict[str, str]] = []
        for spec in TARGET_SPECS:
            df = build_frame(source, spec)
            if df.empty:
                print(f"  {source} {spec.key}: no scoreable cells - skipped")
                continue
            print(f"  {source} {spec.key}: {len(df)} cells "
                  f"(win-event base rate {df['win_event'].mean():.1%}, "
                  f"loss-event base rate {df['loss_event'].mean():.1%})")
            rows = reliability_rows(df, source, spec.key, "all")
            all_rows.extend(rows)
            print_table(rows, source, spec.key, "all")
            if focus:
                fdf = df[df["ticker"].isin(focus)]
                if len(fdf) > 0:
                    frows = reliability_rows(fdf, source, spec.key, "focus")
                    all_rows.extend(frows)
                    print_table(frows, source, spec.key, "focus")

        if all_rows:
            out_path = EXP_OUTPUT_DIR / f"exp_calibration_{source}.csv"
            cols = ["source", "horizon", "scope", "prob", "bin", "n", "mean_stated", "realized_rate", "gap"]
            pd.DataFrame(all_rows)[cols].to_csv(out_path, sep=";", index=False)
            print(f"\n  Written: {out_path.name}")

    wall = time.time() - t0
    append_manifest("exp_calibration.py", " ".join(sys.argv[1:]) or "(defaults)", wall,
                    "full-history per source")
    print(f"\nSUCCESS: calibration analysis complete in {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
