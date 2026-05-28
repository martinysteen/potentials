"""
Daily Win/Loss production scorer.

Creates app/output/aux_win-loss.csv with one row per non-caret ticker and
side-by-side 20d/50d model outputs for the newest available daynum.

Output columns:
- daynum_in_case
- ticker
- pred_label_20d
- P_win_20d
- P_loss_20d
- pred_label_50d
- P_win_50d
- P_Loss_50d
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from aux_win_loss_shared import (
    CLASS_NAMES,
    CLASS_TO_INT,
    FEATURE_FILES,
    TARGET_SPECS,
    build_feature_frame,
    build_labeled_dataset,
    ensure_files_exist,
    fit_predict_multinomial,
    get_max_daynum_from_potdat,
    get_non_caret_tickers_from_potdat,
    standardize_fit,
)


INPUT_DIR = Path(__file__).parent.parent / "input"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create daily Win/Loss production output.")
    parser.add_argument("--daynum", type=int, default=None, help="Daynum to score (default: newest from PotDat).")
    parser.add_argument("--min-stock-samples", type=int, default=150, help="Min training rows per ticker.")
    parser.add_argument("--reg-lambda", type=float, default=0.01, help="L2 regularization strength.")
    parser.add_argument("--max-iter", type=int, default=250, help="Maximum optimizer iterations.")
    return parser.parse_args()


def _get_feature_row(
    x_case: pd.DataFrame, ticker: str, feature_cols: List[str]
) -> np.ndarray | None:
    """Return feature row vector for ticker at case daynum, if available."""
    if ticker not in x_case.index:
        return None
    row = x_case.loc[ticker, feature_cols]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return row.to_numpy(dtype=float).reshape(1, -1)


def predict_for_target(
    data: pd.DataFrame,
    feature_df: pd.DataFrame,
    tickers: List[str],
    daynum_case: int,
    min_stock_samples: int,
    reg_lambda: float,
    max_iter: int,
) -> Dict[str, Tuple[str, float, float]]:
    """
    Predict per ticker for one target configuration.

    Returns mapping:
    ticker -> (pred_label, p_win, p_loss)
    """
    feature_cols = [Path(name).stem for name in FEATURE_FILES]
    x_case = feature_df[feature_df["daynum"] == daynum_case].set_index("ticker")
    train_all = data[data["daynum"] < daynum_case]
    train_by_ticker = {ticker: grp for ticker, grp in train_all.groupby("ticker", sort=False)}

    out: Dict[str, Tuple[str, float, float]] = {}

    for ticker in tickers:
        x_row = _get_feature_row(x_case, ticker, feature_cols)
        if x_row is None:
            out[ticker] = ("NoData", np.nan, np.nan)
            continue

        stock_train = train_by_ticker.get(ticker)
        if stock_train is None or stock_train.shape[0] < min_stock_samples:
            out[ticker] = ("NoModel", np.nan, np.nan)
            continue

        x_train = stock_train[feature_cols].to_numpy(dtype=float)
        y_train = stock_train["y_int"].to_numpy(dtype=int)

        mean, std = standardize_fit(x_train)
        x_train_std = (x_train - mean) / std
        x_test_std = (x_row - mean) / std

        y_pred, probs = fit_predict_multinomial(
            x_train=x_train_std,
            y_train=y_train,
            x_test=x_test_std,
            reg_lambda=reg_lambda,
            max_iter=max_iter,
        )
        out[ticker] = (
            CLASS_NAMES[int(y_pred[0])],
            float(probs[0, CLASS_TO_INT["Win"]]),
            float(probs[0, CLASS_TO_INT["Loss"]]),
        )

    return out


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    feature_paths = [OUTPUT_DIR / fname for fname in FEATURE_FILES]
    target_paths = [OUTPUT_DIR / spec.target_file for spec in TARGET_SPECS]
    ensure_files_exist([POTDAT_FILE] + feature_paths + target_paths)

    daynum_case = int(args.daynum) if args.daynum is not None else get_max_daynum_from_potdat(POTDAT_FILE)
    tickers = sorted(get_non_caret_tickers_from_potdat(POTDAT_FILE))

    print("aux_win-loss.py: Daily Win/Loss production scoring")
    print(f"  Daynum in case: {daynum_case}")
    print(f"  Tickers (non-caret): {len(tickers)}")

    feature_df = build_feature_frame(OUTPUT_DIR)

    target_results: Dict[str, Dict[str, Tuple[str, float, float]]] = {}
    for spec in TARGET_SPECS:
        print(
            f"  Training per-ticker {spec.key} model: "
            f"target={spec.target_file}, win>{spec.win_threshold}, loss<{spec.loss_threshold}"
        )
        data = build_labeled_dataset(feature_df, OUTPUT_DIR, spec)
        target_results[spec.key] = predict_for_target(
            data=data,
            feature_df=feature_df,
            tickers=tickers,
            daynum_case=daynum_case,
            min_stock_samples=int(args.min_stock_samples),
            reg_lambda=float(args.reg_lambda),
            max_iter=int(args.max_iter),
        )

    rows = []
    for ticker in tickers:
        label_20d, pwin_20d, ploss_20d = target_results["20d"][ticker]
        label_50d, pwin_50d, ploss_50d = target_results["50d"][ticker]
        rows.append(
            {
                "daynum_in_case": daynum_case,
                "ticker": ticker,
                "pred_label_20d": label_20d,
                "P_win_20d": pwin_20d,
                "P_loss_20d": ploss_20d,
                "pred_label_50d": label_50d,
                "P_win_50d": pwin_50d,
                "P_Loss_50d": ploss_50d,
            }
        )

    out_df = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    output_file = OUTPUT_DIR / "aux_win-loss.csv"
    out_df.to_csv(output_file, sep=";", decimal=",", index=False)

    model_20d = int(out_df["pred_label_20d"].isin(CLASS_NAMES).sum())
    model_50d = int(out_df["pred_label_50d"].isin(CLASS_NAMES).sum())
    nodata = int((out_df["pred_label_20d"] == "NoData").sum())
    nomodel = int((out_df["pred_label_20d"] == "NoModel").sum())

    print("SUCCESS: aux_win-loss.csv created")
    print(f"  Output: {output_file}")
    print(f"  Usable models - 20d: {model_20d}, 50d: {model_50d}")
    print(f"  NoData rows: {nodata}, NoModel rows: {nomodel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

