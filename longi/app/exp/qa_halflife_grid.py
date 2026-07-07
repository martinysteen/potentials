"""
qa_halflife_grid.py - Choose the recency half-life with data, not taste.

Walk-forward evaluation over recent history comparing half-lives
H in {63, 126, 252, none}: for each H, each scoreable daynum in the window,
each ticker - embargoed training, weighted fit, predict the held-out day,
accumulate production error counts and realized log-loss.

!! COMPUTE WARNING !!
The full default grid (4 half-lives x 250 daynums x ~1200 tickers x 2 horizons)
costs roughly 4x a full probability backfill - hours of wall-clock. Recommended
procedure: smoke run first (--tickers with ~5 names, --last-daynums 20), then
per-horizon full runs (--horizons 20d, then --horizons 50d). NEVER wire this
script into cron.

Flags:
--grid           Comma list of half-lives, 'none' = equal weighting (default: 63,126,252,none)
--last-daynums   Newest N scoreable daynums per horizon to walk forward over (default: 250)
--tickers        Comma list of tickers (optional; for smoke runs)
--horizons       Comma list from {20d,50d} (default: 20d,50d)
--min-stock-samples / --reg-lambda / --max-iter   as in exp_winloss_probs.py

Output: app/exp/output/exp_qa_halflife_results.csv - one row per (H, horizon):
error totals (first/second/signal-vs-nothing), mean log-loss, cells scored,
wall-clock. Rows replaced by (half_life, horizon) key on rerun. A ranked table
(by mean log-loss) is printed per horizon.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from exp_shared import (
    EXP_OUTPUT_DIR,
    append_manifest,
    effective_n,
    exp_weights,
    fit_predict_multinomial_ext,
    format_cell,
)
from exp_winloss_probs import MIN_CLASS_WEIGHT_SHARE, _get_feature_row
from aux_winloss_shared import (  # production helpers, read-only imports
    CLASS_TO_INT,
    FEATURE_FILES,
    TARGET_SPECS,
    build_feature_frame,
    build_labeled_dataset,
    compute_error_counts,
    ensure_files_exist,
    get_non_caret_tickers_from_potdat,
)

EXP_DIR = Path(__file__).resolve().parent
INPUT_DIR = EXP_DIR.parent / "input"
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"

EPS = 1e-12
RESULTS_FILE = EXP_OUTPUT_DIR / "exp_qa_halflife_results.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward half-life grid for the win/loss model.")
    parser.add_argument("--grid", type=str, default="63,126,252,none",
                        help="Comma list of half-lives; 'none' = equal weighting.")
    parser.add_argument("--last-daynums", type=int, default=250,
                        help="Newest N scoreable daynums per horizon.")
    parser.add_argument("--tickers", type=str, default=None,
                        help="Comma list of tickers (smoke runs).")
    parser.add_argument("--horizons", type=str, default="20d,50d",
                        help="Comma list from {20d,50d}.")
    parser.add_argument("--min-stock-samples", type=int, default=150)
    parser.add_argument("--reg-lambda", type=float, default=0.01)
    parser.add_argument("--max-iter", type=int, default=1000)
    return parser.parse_args()


def parse_grid(grid_str: str) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for tok in grid_str.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        out.append(None if tok == "none" else float(tok))
    if not out:
        raise ValueError("--grid produced an empty half-life list")
    return out


def h_label(half_life: Optional[float]) -> str:
    return "none" if half_life is None else str(int(half_life))


def update_results_csv(new_rows: List[Dict[str, str]]) -> None:
    """Replace rows by (half_life, horizon) key; European CSV format."""
    cols = ["half_life", "horizon", "cells_scored", "first_order_error", "second_order_error",
            "signal_vs_nothing_error", "mean_logloss", "wall_clock_s", "last_daynums", "n_tickers"]
    new_df = pd.DataFrame(new_rows)[cols].astype(str)
    if RESULTS_FILE.exists():
        old = pd.read_csv(RESULTS_FILE, sep=";", dtype=str)
        old_keys = old.set_index(["half_life", "horizon"]).index
        new_keys = new_df.set_index(["half_life", "horizon"]).index
        out = pd.concat([old[~old_keys.isin(new_keys)], new_df], ignore_index=True)
    else:
        out = new_df
    out = out.sort_values(["horizon", "half_life"])
    out.to_csv(RESULTS_FILE, sep=";", index=False)


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        grid = parse_grid(args.grid)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    specs = [spec for spec in TARGET_SPECS if spec.key in horizons]
    if not specs:
        print(f"ERROR: no valid horizons in '{args.horizons}'")
        return 1

    feature_paths = [PROD_OUTPUT_DIR / fname for fname in FEATURE_FILES]
    target_paths = [PROD_OUTPUT_DIR / spec.target_file for spec in specs]
    ensure_files_exist([POTDAT_FILE] + feature_paths + target_paths)

    all_tickers = sorted(get_non_caret_tickers_from_potdat(POTDAT_FILE))
    if args.tickers:
        requested = [t.strip() for t in args.tickers.split(",") if t.strip()]
        unknown = [t for t in requested if t not in set(all_tickers)]
        if unknown:
            print(f"ERROR: unknown tickers: {', '.join(unknown)}")
            return 1
        tickers = requested
    else:
        tickers = all_tickers

    print("qa_halflife_grid.py: walk-forward half-life experiment (sandbox)")
    print(f"  Grid: {', '.join(h_label(h) for h in grid)}")
    print(f"  Horizons: {', '.join(spec.key for spec in specs)}")
    print(f"  Window: newest {args.last_daynums} scoreable daynums per horizon")
    print(f"  Tickers: {len(tickers)}" + (" (smoke subset)" if args.tickers else " (all non-caret)"))
    print(f"  Gates: min effective samples = {args.min_stock_samples}; "
          f"class weight share floor = {MIN_CLASS_WEIGHT_SHARE}")
    print("  Embargo: train daynum < case daynum - horizon (production semantics)")

    feature_cols = [Path(name).stem for name in FEATURE_FILES]
    feature_df = build_feature_frame(PROD_OUTPUT_DIR)

    # Accumulators per (H label, horizon key)
    acc: Dict[Tuple[str, str], Dict[str, list]] = {
        (h_label(h), spec.key): {"y_true": [], "y_pred": [], "logloss": [], "fit_seconds": 0.0}
        for h in grid for spec in specs
    }
    equal_weight_probe_done = False

    for spec in specs:
        print(f"  Preparing target dataset {spec.key} ({spec.target_file})")
        data = build_labeled_dataset(feature_df, PROD_OUTPUT_DIR, spec)
        scoreable = sorted(data["daynum"].unique().tolist(), reverse=True)[: int(args.last_daynums)]
        print(f"  {spec.key}: walking {len(scoreable)} daynums ({scoreable[0]} .. {scoreable[-1]})")

        for idx, daynum_case in enumerate(scoreable, start=1):
            if idx == 1 or idx % 10 == 0 or idx == len(scoreable):
                print(f"    [{idx}/{len(scoreable)}] daynum {daynum_case}")

            x_case = feature_df[feature_df["daynum"] == daynum_case].set_index("ticker")
            case_labels = data[data["daynum"] == daynum_case].set_index("ticker")["y_int"]
            train_all = data[data["daynum"] < daynum_case - spec.horizon_days]
            train_by_ticker = {t: g for t, g in train_all.groupby("ticker", sort=False)}

            for ticker in tickers:
                if ticker not in case_labels.index:
                    continue  # outcome (or features) not available for this held-out day
                y_true = int(case_labels.loc[ticker] if not isinstance(case_labels.loc[ticker], pd.Series)
                             else case_labels.loc[ticker].iloc[0])

                x_row = _get_feature_row(x_case, ticker, feature_cols)
                if x_row is None:
                    continue
                stock_train = train_by_ticker.get(ticker)
                if stock_train is None or stock_train.shape[0] < int(args.min_stock_samples):
                    continue

                train_daynums = stock_train["daynum"].to_numpy(dtype=float)
                ages = float(daynum_case) - train_daynums
                x_train_full = stock_train[feature_cols].to_numpy(dtype=float)
                y_train_full = stock_train["y_int"].to_numpy(dtype=int)

                for h in grid:
                    w = exp_weights(ages, h)
                    if w is not None and effective_n(w) < int(args.min_stock_samples):
                        continue

                    # Class-starvation guard (same semantics as exp_winloss_probs.py)
                    total_w = float(w.sum()) if w is not None else float(len(y_train_full))
                    keep = np.ones(len(y_train_full), dtype=bool)
                    for cls in np.unique(y_train_full):
                        cls_mask = y_train_full == cls
                        cls_w = float(w[cls_mask].sum()) if w is not None else float(cls_mask.sum())
                        if cls_w / total_w < MIN_CLASS_WEIGHT_SHARE:
                            keep &= ~cls_mask
                    x_train = x_train_full[keep]
                    y_train = y_train_full[keep]
                    w_kept = w[keep] if w is not None else None

                    t_fit = time.time()
                    y_pred, probs, _ = fit_predict_multinomial_ext(
                        x_train=x_train, y_train=y_train, x_test=x_row,
                        reg_lambda=float(args.reg_lambda), max_iter=int(args.max_iter),
                        sample_weight=w_kept,
                    )
                    a = acc[(h_label(h), spec.key)]
                    a["fit_seconds"] += time.time() - t_fit
                    a["y_true"].append(y_true)
                    a["y_pred"].append(int(y_pred[0]))
                    a["logloss"].append(float(-np.log(probs[0, y_true] + EPS)))

                    # One-off probe: 'none' must reproduce equal-weight behavior exactly.
                    if h is None and not equal_weight_probe_done:
                        _, probs_ones, _ = fit_predict_multinomial_ext(
                            x_train=x_train, y_train=y_train, x_test=x_row,
                            reg_lambda=float(args.reg_lambda), max_iter=int(args.max_iter),
                            sample_weight=np.ones(len(y_train)),
                        )
                        dev = float(np.max(np.abs(probs - probs_ones)))
                        print(f"    equal-weight probe ({ticker}, daynum {daynum_case}): "
                              f"none vs ones max prob dev = {dev:.2e}")
                        equal_weight_probe_done = True

    # ---- Results table -----------------------------------------------------
    new_rows: List[Dict[str, str]] = []
    for spec in specs:
        for h in grid:
            a = acc[(h_label(h), spec.key)]
            n = len(a["y_true"])
            if n == 0:
                counts = {"first_order_error": 0, "second_order_error": 0, "signal_vs_nothing_error": 0}
                mean_ll = float("nan")
            else:
                counts = compute_error_counts(np.array(a["y_true"]), np.array(a["y_pred"]))
                mean_ll = float(np.mean(a["logloss"]))
            new_rows.append({
                "half_life": h_label(h),
                "horizon": spec.key,
                "cells_scored": str(n),
                "first_order_error": str(counts["first_order_error"]),
                "second_order_error": str(counts["second_order_error"]),
                "signal_vs_nothing_error": str(counts["signal_vs_nothing_error"]),
                "mean_logloss": format_cell(mean_ll),
                "wall_clock_s": format_cell(a["fit_seconds"], 1),
                "last_daynums": str(int(args.last_daynums)),
                "n_tickers": str(len(tickers)),
            })
    update_results_csv(new_rows)
    print(f"\n  Results written/updated: {RESULTS_FILE.name}")

    for spec in specs:
        rows = [r for r in new_rows if r["horizon"] == spec.key]
        rows.sort(key=lambda r: float(r["mean_logloss"].replace(",", ".")) if r["mean_logloss"] else float("inf"))
        print(f"\n  Ranking {spec.key} (by mean log-loss; ln 3 = 1,099 = uniform ignorance):")
        print(f"    {'rank':<5}{'H':<7}{'mean_ll':<9}{'1st-ord':<9}{'2nd-ord':<9}{'sig-vs-no':<10}{'cells':<7}{'fit-s':<7}")
        for rank, r in enumerate(rows, start=1):
            print(f"    {rank:<5}{r['half_life']:<7}{r['mean_logloss']:<9}{r['first_order_error']:<9}"
                  f"{r['second_order_error']:<9}{r['signal_vs_nothing_error']:<10}{r['cells_scored']:<7}{r['wall_clock_s']:<7}")

    wall = time.time() - t0
    append_manifest("qa_halflife_grid.py", " ".join(sys.argv[1:]) or "(defaults)", wall,
                    f"newest {args.last_daynums} scoreable daynums per horizon")
    print(f"\nSUCCESS: grid complete in {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
