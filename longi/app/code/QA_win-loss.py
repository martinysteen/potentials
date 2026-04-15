"""
Quality assurance runner for Win/Loss per-stock models.

Focus:
- validation quality
- error rates
- ticker-level model reliability metrics

Outputs go to app/output/QA/
"""

from __future__ import annotations

import argparse
import json
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
    compute_error_counts,
    ensure_files_exist,
    fit_predict_multinomial,
    standardize_fit,
)


OUTPUT_DIR = Path(__file__).parent.parent / "output"
QA_DIR = OUTPUT_DIR / "QA"
EPS = 1e-12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QA for per-stock Win/Loss models.")
    parser.add_argument("--n-test-days", type=int, default=10, help="Newest test daynums for walk-forward QA.")
    parser.add_argument("--min-train-daynums", type=int, default=120, help="Minimum train daynums per split.")
    parser.add_argument("--min-stock-samples", type=int, default=150, help="Minimum train rows per ticker.")
    parser.add_argument("--reg-lambda", type=float, default=0.01, help="L2 regularization strength.")
    parser.add_argument("--max-iter", type=int, default=250, help="Maximum optimizer iterations.")
    parser.add_argument(
        "--skip-predictions",
        action="store_true",
        help="Skip writing raw per-row predictions files.",
    )
    return parser.parse_args()


def aggregate_summary(metrics_df: pd.DataFrame, predictions_df: pd.DataFrame) -> Dict[str, float]:
    """Aggregate split-level and row-level predictions into one summary."""
    predicted = predictions_df[predictions_df["pred_label"] != "NoPred"].copy()
    if predicted.empty:
        return {
            "n_splits": int(metrics_df.shape[0]),
            "n_test_rows_total": int(metrics_df["n_test_rows"].sum()) if not metrics_df.empty else 0,
            "n_pred_rows_total": 0,
            "n_no_pred_rows_total": int(metrics_df["n_no_pred_rows"].sum()) if not metrics_df.empty else 0,
            "first_order_error_total": 0,
            "second_order_error_total": 0,
            "signal_vs_nothing_error_total": 0,
            "accuracy_pred_rows_overall": np.nan,
        }

    y_true = predicted["y_int"].to_numpy(dtype=int)
    y_pred = predicted["pred_label"].map(CLASS_TO_INT).to_numpy(dtype=int)
    errors = compute_error_counts(y_true=y_true, y_pred=y_pred)
    acc = float(np.mean(y_true == y_pred))

    return {
        "n_splits": int(metrics_df.shape[0]),
        "n_test_rows_total": int(metrics_df["n_test_rows"].sum()),
        "n_pred_rows_total": int(predicted.shape[0]),
        "n_no_pred_rows_total": int(metrics_df["n_no_pred_rows"].sum()),
        "first_order_error_total": int(errors["first_order_error"]),
        "second_order_error_total": int(errors["second_order_error"]),
        "signal_vs_nothing_error_total": int(errors["signal_vs_nothing_error"]),
        "accuracy_pred_rows_overall": acc,
    }


def compute_ticker_quality(pred_df: pd.DataFrame) -> pd.DataFrame:
    """Compute ticker-level QA metrics from predicted rows."""
    predicted = pred_df[pred_df["pred_label"] != "NoPred"].copy()
    if predicted.empty:
        return pd.DataFrame()

    rows: List[Dict[str, float]] = []
    for ticker, g in predicted.groupby("ticker", sort=True):
        y_true = g["y_int"].to_numpy(dtype=int)
        y_pred = g["pred_label"].map(CLASS_TO_INT).to_numpy(dtype=int)
        errors = compute_error_counts(y_true=y_true, y_pred=y_pred)
        n = int(g.shape[0])

        y_label = g["y_label"].astype(str)
        p_win = pd.to_numeric(g["p_Win"], errors="coerce").to_numpy(dtype=float)
        p_loss = pd.to_numeric(g["p_Loss"], errors="coerce").to_numpy(dtype=float)
        y_win = (y_label == "Win").astype(float).to_numpy()
        y_loss = (y_label == "Loss").astype(float).to_numpy()

        brier_win = float(np.mean((p_win - y_win) ** 2))
        brier_loss = float(np.mean((p_loss - y_loss) ** 2))

        p_win_c = np.clip(p_win, EPS, 1.0 - EPS)
        p_loss_c = np.clip(p_loss, EPS, 1.0 - EPS)
        ll_win = float(-np.mean(y_win * np.log(p_win_c) + (1.0 - y_win) * np.log(1.0 - p_win_c)))
        ll_loss = float(-np.mean(y_loss * np.log(p_loss_c) + (1.0 - y_loss) * np.log(1.0 - p_loss_c)))

        signal_mask = g["pred_label"].isin(["Win", "Loss"])
        if signal_mask.any():
            sig = g.loc[signal_mask]
            blunt = ((sig["pred_label"] == "Win") & (sig["y_label"] == "Loss")) | (
                (sig["pred_label"] == "Loss") & (sig["y_label"] == "Win")
            )
            first_order_rate_signal = float(blunt.mean())
        else:
            first_order_rate_signal = np.nan

        win_mask = g["pred_label"] == "Win"
        loss_mask = g["pred_label"] == "Loss"
        precision_pred_win = float((g.loc[win_mask, "y_label"] == "Win").mean()) if win_mask.any() else np.nan
        precision_pred_loss = (
            float((g.loc[loss_mask, "y_label"] == "Loss").mean()) if loss_mask.any() else np.nan
        )

        rows.append(
            {
                "ticker": ticker,
                "n_pred_rows": n,
                "accuracy_pred_rows": float(np.mean(y_true == y_pred)),
                "first_order_error_count": int(errors["first_order_error"]),
                "second_order_error_count": int(errors["second_order_error"]),
                "signal_vs_nothing_error_count": int(errors["signal_vs_nothing_error"]),
                "first_order_error_rate_pred_rows": float(errors["first_order_error"] / n),
                "second_order_error_rate_pred_rows": float(errors["second_order_error"] / n),
                "signal_vs_nothing_error_rate_pred_rows": float(errors["signal_vs_nothing_error"] / n),
                "first_order_error_rate_signal_rows": first_order_rate_signal,
                "precision_when_pred_Win": precision_pred_win,
                "precision_when_pred_Loss": precision_pred_loss,
                "validity_win_brier": float(1.0 - brier_win),
                "validity_loss_brier": float(1.0 - brier_loss),
                "validity_win_logscore": float(np.exp(-ll_win)),
                "validity_loss_logscore": float(np.exp(-ll_loss)),
            }
        )

    return pd.DataFrame(rows)


def run_per_stock_walkforward(
    data: pd.DataFrame,
    n_test_days: int,
    min_train_daynums: int,
    min_stock_samples: int,
    reg_lambda: float,
    max_iter: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    """Run per-stock walk-forward validation for one target."""
    feature_cols = [Path(name).stem for name in FEATURE_FILES]
    daynums_desc = sorted(data["daynum"].unique(), reverse=True)
    test_days = daynums_desc[:n_test_days]

    split_rows: List[Dict[str, float]] = []
    pred_rows: List[pd.DataFrame] = []

    for split_id, test_day in enumerate(test_days, start=1):
        train_df_all = data[data["daynum"] < test_day]
        if train_df_all["daynum"].nunique() < min_train_daynums:
            continue

        test_df = data[data["daynum"] == test_day].copy()
        if test_df.empty:
            continue

        test_df["split_id"] = split_id
        test_df["test_daynum"] = test_day
        test_df["pred_label"] = "NoPred"
        test_df["p_Loss"] = np.nan
        test_df["p_Nothing"] = np.nan
        test_df["p_Win"] = np.nan

        n_pred_rows = 0
        train_by_ticker = {ticker: grp for ticker, grp in train_df_all.groupby("ticker", sort=False)}
        for row_idx, row in test_df.iterrows():
            ticker = str(row["ticker"])
            stock_train = train_by_ticker.get(ticker)
            if stock_train is None or stock_train.shape[0] < min_stock_samples:
                continue

            x_train = stock_train[feature_cols].to_numpy(dtype=float)
            y_train = stock_train["y_int"].to_numpy(dtype=int)
            x_test = row[feature_cols].to_numpy(dtype=float).reshape(1, -1)

            mean, std = standardize_fit(x_train)
            x_train_std = (x_train - mean) / std
            x_test_std = (x_test - mean) / std

            y_pred, probs = fit_predict_multinomial(
                x_train=x_train_std,
                y_train=y_train,
                x_test=x_test_std,
                reg_lambda=reg_lambda,
                max_iter=max_iter,
            )

            test_df.at[row_idx, "pred_label"] = CLASS_NAMES[int(y_pred[0])]
            test_df.at[row_idx, "p_Loss"] = float(probs[0, CLASS_TO_INT["Loss"]])
            test_df.at[row_idx, "p_Nothing"] = float(probs[0, CLASS_TO_INT["Nothing"]])
            test_df.at[row_idx, "p_Win"] = float(probs[0, CLASS_TO_INT["Win"]])
            n_pred_rows += 1

        predicted = test_df[test_df["pred_label"] != "NoPred"]
        if predicted.empty:
            split_rows.append(
                {
                    "split_id": split_id,
                    "test_daynum": test_day,
                    "n_train_rows": int(train_df_all.shape[0]),
                    "n_test_rows": int(test_df.shape[0]),
                    "n_pred_rows": 0,
                    "n_no_pred_rows": int(test_df.shape[0]),
                    "first_order_error": 0,
                    "second_order_error": 0,
                    "signal_vs_nothing_error": 0,
                    "accuracy_pred_rows": np.nan,
                }
            )
        else:
            y_true = predicted["y_int"].to_numpy(dtype=int)
            y_pred = predicted["pred_label"].map(CLASS_TO_INT).to_numpy(dtype=int)
            errors = compute_error_counts(y_true=y_true, y_pred=y_pred)
            split_rows.append(
                {
                    "split_id": split_id,
                    "test_daynum": test_day,
                    "n_train_rows": int(train_df_all.shape[0]),
                    "n_test_rows": int(test_df.shape[0]),
                    "n_pred_rows": int(n_pred_rows),
                    "n_no_pred_rows": int(test_df.shape[0] - n_pred_rows),
                    "first_order_error": int(errors["first_order_error"]),
                    "second_order_error": int(errors["second_order_error"]),
                    "signal_vs_nothing_error": int(errors["signal_vs_nothing_error"]),
                    "accuracy_pred_rows": float(np.mean(y_true == y_pred)),
                }
            )

        pred_rows.append(test_df)

    metrics_df = pd.DataFrame(split_rows)
    pred_df = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    summary = aggregate_summary(metrics_df, pred_df) if not metrics_df.empty else {}
    return metrics_df, pred_df, summary


def main() -> int:
    args = parse_args()
    QA_DIR.mkdir(parents=True, exist_ok=True)

    feature_paths = [OUTPUT_DIR / fname for fname in FEATURE_FILES]
    target_paths = [OUTPUT_DIR / spec.target_file for spec in TARGET_SPECS]
    ensure_files_exist(feature_paths + target_paths)

    print("QA_win-loss.py: Running per-stock QA")
    print(
        f"  n_test_days={args.n_test_days}, min_train_daynums={args.min_train_daynums}, "
        f"min_stock_samples={args.min_stock_samples}"
    )

    feature_df = build_feature_frame(OUTPUT_DIR)

    summary_rows: List[Dict[str, float]] = []
    for spec in TARGET_SPECS:
        print(
            f"  QA target {spec.key}: {spec.target_file}, "
            f"win>{spec.win_threshold}, loss<{spec.loss_threshold}"
        )
        data = build_labeled_dataset(feature_df, OUTPUT_DIR, spec)

        metrics_df, pred_df, summary = run_per_stock_walkforward(
            data=data,
            n_test_days=int(args.n_test_days),
            min_train_daynums=int(args.min_train_daynums),
            min_stock_samples=int(args.min_stock_samples),
            reg_lambda=float(args.reg_lambda),
            max_iter=int(args.max_iter),
        )

        if metrics_df.empty or pred_df.empty:
            print(f"    WARNING: No QA output for {spec.key}")
            continue

        metrics_file = QA_DIR / f"qa_win-loss_{spec.key}_metrics_by_split.csv"
        metrics_df.to_csv(metrics_file, sep=";", decimal=",", index=False)

        if not args.skip_predictions:
            pred_file = QA_DIR / f"qa_win-loss_{spec.key}_predictions.csv"
            pred_df.to_csv(pred_file, sep=";", decimal=",", index=False)

        quality_df = compute_ticker_quality(pred_df)
        quality_file = QA_DIR / f"qa_win-loss_{spec.key}_ticker_quality.csv"
        quality_df.to_csv(quality_file, sep=";", decimal=",", index=False)

        summary_file = QA_DIR / f"qa_win-loss_{spec.key}_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        summary_rows.append(
            {
                "target_key": spec.key,
                "target_file": spec.target_file,
                "win_threshold": spec.win_threshold,
                "loss_threshold": spec.loss_threshold,
                **summary,
            }
        )
        print(
            f"    summary: pred={summary['n_pred_rows_total']} "
            f"no_pred={summary['n_no_pred_rows_total']} "
            f"acc={summary['accuracy_pred_rows_overall']:.4f}"
        )

    if summary_rows:
        summary_targets = pd.DataFrame(summary_rows)
        summary_targets.to_csv(QA_DIR / "qa_win-loss_summary_targets.csv", sep=";", decimal=",", index=False)

    print("SUCCESS: QA outputs written")
    print(f"  Output dir: {QA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

