"""
exp_winloss_probs.py - Experimental twin of the production Win/Loss scorer.

Same per-cell semantics as longi_winloss_probs.py, plus:
- optional exponential recency weighting of training rows (--half-life)
- per-cell fit quality (McFadden pseudo-R2) from the same single fit
- per-cell model composition (top driving indicators, win and loss)

Writes parameter-stamped experimental matrices to app/exp/output/ (production
directories are read-only inputs):
- exp_longi_P{20d,50d}_{win,loss}_{suffix}.csv
- exp_longi_fitR2_{20d,50d}_{suffix}.csv
- exp_longi_drivers{20d,50d}_{win,loss}_{suffix}.csv
where suffix = H{int(half_life)} or Hnone (equal weighting).

Flags:
--half-life H        Exponential half-life in daynum units (omitted = equal weighting)
--daynum N           Only compute a specific daynum (mutually exclusive with --backfill-all)
--backfill-all       Compute all scoreable feature daynums (can be slow)
--max-daynums N      Limit number of daynums processed, newest-first (with --backfill-all)
--min-stock-samples  Min effective training samples per ticker (default: 150)
--reg-lambda         L2 regularization strength (default: 0.01)
--max-iter           Maximum optimizer iterations (default: 1000)

Default mode (no daynum flags) = newest daynum only, mirroring production.
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
    mcfadden_r2,
    read_existing_matrix_cells,
    read_potdat_layout,
    top_drivers,
    write_probability_matrix,
)
from aux_winloss_shared import (  # production helpers, read-only imports
    CLASS_TO_INT,
    FEATURE_FILES,
    TARGET_SPECS,
    build_feature_frame,
    build_labeled_dataset,
    ensure_files_exist,
    get_non_caret_tickers_from_potdat,
)

EXP_DIR = Path(__file__).resolve().parent
INPUT_DIR = EXP_DIR.parent / "input"
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"

# Guard against classes that are effectively absent under recency weighting:
# a class whose rows carry < this share of total training weight cannot be
# estimated stably (its few effective samples whipsaw the fit). Its rows are
# dropped for that cell; the class then flows through the standard
# missing-class probability expansion (probability 0 for the absent class).
MIN_CLASS_WEIGHT_SHARE = 0.01

# One blank per-cell result: (p_win, p_loss, fit_r2, drivers_win, drivers_loss)
BLANK_CELL: Tuple[float, float, float, Optional[str], Optional[str]] = (
    np.nan, np.nan, np.nan, None, None,
)

MATRIX_KINDS = ["win", "loss", "fitR2", "drv_win", "drv_loss"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experimental win/loss probability matrices (sandbox).")
    parser.add_argument("--half-life", type=float, default=None,
                        help="Exponential recency half-life in daynum units (omit = equal weighting).")
    parser.add_argument("--daynum", type=int, default=None, help="Only compute a specific daynum.")
    parser.add_argument("--backfill-all", action="store_true",
                        help="Compute all scoreable feature daynums (can be slow).")
    parser.add_argument("--max-daynums", type=int, default=None,
                        help="Limit number of daynums processed (newest-first; with --backfill-all).")
    parser.add_argument("--min-stock-samples", type=int, default=150,
                        help="Min effective training samples per ticker.")
    parser.add_argument("--reg-lambda", type=float, default=0.01, help="L2 regularization strength.")
    parser.add_argument("--max-iter", type=int, default=1000, help="Maximum optimizer iterations.")
    return parser.parse_args()


def suffix_for(half_life: Optional[float]) -> str:
    return f"H{int(half_life)}" if half_life is not None else "Hnone"


def output_files_for(suffix: str) -> Dict[Tuple[str, str], Path]:
    out: Dict[Tuple[str, str], Path] = {}
    for spec in TARGET_SPECS:
        key = spec.key
        out[(key, "win")] = EXP_OUTPUT_DIR / f"exp_longi_P{key}_win_{suffix}.csv"
        out[(key, "loss")] = EXP_OUTPUT_DIR / f"exp_longi_P{key}_loss_{suffix}.csv"
        out[(key, "fitR2")] = EXP_OUTPUT_DIR / f"exp_longi_fitR2_{key}_{suffix}.csv"
        out[(key, "drv_win")] = EXP_OUTPUT_DIR / f"exp_longi_drivers{key}_win_{suffix}.csv"
        out[(key, "drv_loss")] = EXP_OUTPUT_DIR / f"exp_longi_drivers{key}_loss_{suffix}.csv"
    return out


def select_daynums(args: argparse.Namespace, potdat_daynums: List[int]) -> List[int]:
    # copied selection semantics from longi_winloss_probs.py (PotDat header order, newest-first)
    if args.daynum is not None and args.backfill_all:
        raise ValueError("Use either --daynum or --backfill-all, not both.")
    if args.daynum is not None:
        return [int(args.daynum)]
    if not args.backfill_all:
        return [int(max(potdat_daynums))]
    if args.max_daynums is not None and int(args.max_daynums) <= 0:
        raise ValueError("--max-daynums must be > 0.")
    selected = list(potdat_daynums)
    if args.max_daynums is not None:
        selected = selected[: int(args.max_daynums)]
    return selected


def _get_feature_row(x_case: pd.DataFrame, ticker: str, feature_cols: List[str]) -> Optional[np.ndarray]:
    # copied from longi_winloss_probs.py
    if ticker not in x_case.index:
        return None
    row = x_case.loc[ticker, feature_cols]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return row.to_numpy(dtype=float).reshape(1, -1)


def predict_for_target_day_ext(
    data: pd.DataFrame,
    feature_df: pd.DataFrame,
    tickers: List[str],
    daynum_case: int,
    min_stock_samples: int,
    reg_lambda: float,
    max_iter: int,
    horizon_days: int,
    half_life: Optional[float],
    counters: Dict[str, int],
) -> Dict[str, Tuple[float, float, float, Optional[str], Optional[str]]]:
    """
    Per-ticker (p_win, p_loss, fit_r2, drivers_win, drivers_loss) for one
    target and one daynum. One fit per cell feeds all five outputs.

    Embargo matches production exactly (strict <): training rows must satisfy
    daynum < daynum_case - horizon_days, so no label window overlaps the
    scoring day.
    """
    feature_cols = [Path(name).stem for name in FEATURE_FILES]
    x_case = feature_df[feature_df["daynum"] == daynum_case].set_index("ticker")
    train_all = data[data["daynum"] < daynum_case - horizon_days]
    train_by_ticker = {t: g for t, g in train_all.groupby("ticker", sort=False)}

    out: Dict[str, Tuple[float, float, float, Optional[str], Optional[str]]] = {}

    for ticker in tickers:
        x_row = _get_feature_row(x_case, ticker, feature_cols)
        if x_row is None:
            out[ticker] = BLANK_CELL
            counters["no_features"] += 1
            continue

        stock_train = train_by_ticker.get(ticker)
        if stock_train is None or stock_train.shape[0] < min_stock_samples:
            out[ticker] = BLANK_CELL
            counters["raw_count_blanked"] += 1
            continue

        train_daynums = stock_train["daynum"].to_numpy(dtype=float)
        ages = float(daynum_case) - train_daynums
        w = exp_weights(ages, half_life)

        # Effective-sample gate (reduces to the raw-count gate when w is None).
        if w is not None and effective_n(w) < min_stock_samples:
            out[ticker] = BLANK_CELL
            counters["effective_gate_blanked"] += 1
            continue

        x_train = stock_train[feature_cols].to_numpy(dtype=float)
        y_train = stock_train["y_int"].to_numpy(dtype=int)

        # Class-starvation guard (see MIN_CLASS_WEIGHT_SHARE above).
        total_w = float(w.sum()) if w is not None else float(len(y_train))
        keep = np.ones(len(y_train), dtype=bool)
        starved = False
        for cls in np.unique(y_train):
            cls_mask = y_train == cls
            cls_w = float(w[cls_mask].sum()) if w is not None else float(cls_mask.sum())
            if cls_w / total_w < MIN_CLASS_WEIGHT_SHARE:
                keep &= ~cls_mask
                starved = True
        if starved:
            counters["class_starved_cells"] += 1
            x_train = x_train[keep]
            y_train = y_train[keep]
            w = w[keep] if w is not None else None

        _, probs, diag = fit_predict_multinomial_ext(
            x_train=x_train,
            y_train=y_train,
            x_test=x_row,
            reg_lambda=reg_lambda,
            max_iter=max_iter,
            sample_weight=w,
        )

        p_win = float(probs[0, CLASS_TO_INT["Win"]])
        p_loss = float(probs[0, CLASS_TO_INT["Loss"]])
        r2 = mcfadden_r2(y_train, diag.train_probs, sample_weight=w)
        drv_win = top_drivers(diag.pipeline, x_row[0], CLASS_TO_INT["Win"], feature_cols)
        drv_loss = top_drivers(diag.pipeline, x_row[0], CLASS_TO_INT["Loss"], feature_cols)

        if diag.pipeline is not None and len(diag.pipeline.named_steps["clf"].classes_) == 2:
            counters["binary_fit_driver_blanks"] += 1

        counters["scored"] += 1
        out[ticker] = (p_win, p_loss, r2, drv_win, drv_loss)

    return out


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    feature_paths = [PROD_OUTPUT_DIR / fname for fname in FEATURE_FILES]
    target_paths = [PROD_OUTPUT_DIR / spec.target_file for spec in TARGET_SPECS]
    ensure_files_exist([POTDAT_FILE] + feature_paths + target_paths)

    half_life = args.half_life
    suffix = suffix_for(half_life)
    out_files = output_files_for(suffix)

    print("exp_winloss_probs.py: EXPERIMENTAL win/loss matrices (sandbox)")
    print(f"  Half-life: {half_life if half_life is not None else 'none (equal weighting)'}  ->  suffix _{suffix}")
    if args.backfill_all:
        print("  Mode: backfill-all (historical; can be slow)")
    elif args.daynum is not None:
        print(f"  Mode: single daynum ({int(args.daynum)})")
    else:
        print("  Mode: newest daynum only")
    print(f"  Gates: min effective samples per ticker = {int(args.min_stock_samples)}; "
          f"class weight share floor = {MIN_CLASS_WEIGHT_SHARE}")
    print(f"  Embargo: train daynum < case daynum - horizon (production semantics)")

    header, potdat_daynums, potdat_ticker_rows = read_potdat_layout(POTDAT_FILE)
    non_caret_tickers = sorted(get_non_caret_tickers_from_potdat(POTDAT_FILE))
    print(f"  PotDat rows: {len(potdat_ticker_rows)} (non-caret scored: {len(non_caret_tickers)})")

    feature_df = build_feature_frame(PROD_OUTPUT_DIR)
    try:
        daynums_to_compute = select_daynums(args, potdat_daynums)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    if not daynums_to_compute:
        print("ERROR: No daynums selected for computation")
        return 1

    print(f"  Daynums to compute: {len(daynums_to_compute)}")
    if len(daynums_to_compute) <= 10:
        print(f"  Daynum list: {', '.join(map(str, daynums_to_compute))}")
    else:
        print(f"  Range: {daynums_to_compute[0]} .. {daynums_to_compute[-1]}")

    target_data: Dict[str, pd.DataFrame] = {}
    for spec in TARGET_SPECS:
        print(f"  Preparing target dataset {spec.key} ({spec.target_file})")
        target_data[spec.key] = build_labeled_dataset(feature_df, PROD_OUTPUT_DIR, spec)

    existing_cells_by_file = {path: read_existing_matrix_cells(path) for path in out_files.values()}
    overlay_by_file: Dict[Path, Dict[Tuple[str, int], str]] = {path: {} for path in out_files.values()}

    counters_by_key: Dict[str, Dict[str, int]] = {
        spec.key: {
            "scored": 0,
            "no_features": 0,
            "raw_count_blanked": 0,
            "effective_gate_blanked": 0,
            "class_starved_cells": 0,
            "binary_fit_driver_blanks": 0,
        }
        for spec in TARGET_SPECS
    }

    all_row_tickers = set(potdat_ticker_rows)
    progress_every = 1 if len(daynums_to_compute) <= 20 else 10

    for idx, daynum_case in enumerate(daynums_to_compute, start=1):
        if idx == 1 or idx % progress_every == 0 or idx == len(daynums_to_compute):
            print(f"  [{idx}/{len(daynums_to_compute)}] Scoring daynum {daynum_case}")

        for spec in TARGET_SPECS:
            results = predict_for_target_day_ext(
                data=target_data[spec.key],
                feature_df=feature_df,
                tickers=non_caret_tickers,
                daynum_case=int(daynum_case),
                min_stock_samples=int(args.min_stock_samples),
                reg_lambda=float(args.reg_lambda),
                max_iter=int(args.max_iter),
                horizon_days=spec.horizon_days,
                half_life=half_life,
                counters=counters_by_key[spec.key],
            )

            # Clear the recomputed column in all five matrices so stale cells cannot survive.
            for kind in MATRIX_KINDS:
                overlay = overlay_by_file[out_files[(spec.key, kind)]]
                for ticker in all_row_tickers:
                    overlay[(ticker, int(daynum_case))] = ""

            for ticker in non_caret_tickers:
                p_win, p_loss, r2, drv_win, drv_loss = results[ticker]
                dn = int(daynum_case)
                overlay_by_file[out_files[(spec.key, "win")]][(ticker, dn)] = format_cell(p_win)
                overlay_by_file[out_files[(spec.key, "loss")]][(ticker, dn)] = format_cell(p_loss)
                overlay_by_file[out_files[(spec.key, "fitR2")]][(ticker, dn)] = format_cell(r2)
                overlay_by_file[out_files[(spec.key, "drv_win")]][(ticker, dn)] = drv_win or ""
                overlay_by_file[out_files[(spec.key, "drv_loss")]][(ticker, dn)] = drv_loss or ""

    matrix_daynums_to_write = potdat_daynums
    if args.backfill_all and args.max_daynums is not None:
        matrix_daynums_to_write = list(daynums_to_compute)

    print("  Writing experimental matrices")
    for path in out_files.values():
        write_probability_matrix(
            path=path,
            ticker_header=(header[0] if header else "ticker"),
            daynums_to_write=matrix_daynums_to_write,
            ticker_rows=potdat_ticker_rows,
            existing_cells=existing_cells_by_file[path],
            overlay_cells=overlay_by_file[path],
        )
        print(f"    {path.name}")

    wall = time.time() - t0
    print("  Cell summary per horizon:")
    for key, c in counters_by_key.items():
        print(f"    {key}: scored={c['scored']}  raw-count-blanked={c['raw_count_blanked']}  "
              f"effective-gate-blanked={c['effective_gate_blanked']}  no-features={c['no_features']}  "
              f"class-starved={c['class_starved_cells']}  binary-fit-driver-blanks={c['binary_fit_driver_blanks']}")
    print(f"  Wall clock: {wall:.1f}s ({wall / max(len(daynums_to_compute), 1):.1f}s per daynum)")

    daynums_str = (f"{daynums_to_compute[0]}..{daynums_to_compute[-1]}"
                   if len(daynums_to_compute) > 1 else str(daynums_to_compute[0]))
    append_manifest("exp_winloss_probs.py", " ".join(sys.argv[1:]) or "(defaults)", wall, daynums_str)

    print(f"SUCCESS: wrote experimental matrices for {len(daynums_to_compute)} daynum(s), suffix _{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
