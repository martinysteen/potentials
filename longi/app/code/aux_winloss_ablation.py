"""
Ablation diagnostic for the Win/Loss probability model.

Decision tool for "is it safe to remove feature(s) X?" — e.g. the long-lookback
indicators (vola100d, spr100d, stepup100) whose ~100-daynum warm-up shortens the
usable backtest span. The production scorer fits a *separate* per-ticker model, so
the only honest answer is a per-ticker, out-of-sample, head-to-head comparison
whose result is read from the *tail*, not the mean: a feature can be useless on
average yet decisive for a handful of tickers.

Method
------
For each target horizon (20d / 50d):
  1. Build two feature frames: FULL and ABLATED (FULL minus the drop-set).
  2. Pick test daynums from the realized region (rows whose future-gain label is
     already known — i.e. present in the labeled dataset).
  3. Evaluate both models on the SAME test points (the ones FULL can score), so
     the span-extension upside of removing features is NOT conflated with the
     prediction-quality question measured here. Each model trains on its own
     natural training set (the ablated one legitimately gets more rows, since
     dropping a feature un-drops rows the inner-join previously deleted on NaN).
  4. Predict via the exact production path (fit_predict_multinomial) and score
     each point with multiclass log-loss against the realized label.

Output
------
  - Per-ticker Δlog-loss = ablated - full  (positive => removal HURTS that ticker)
    summarised as a distribution: n_worse / n_better / neutral, median, p90, p95,
    max, and the worst-hurt tickers.
  - Aggregate: total mean log-loss full vs ablated, and the project's
    first/second-order error counts full vs ablated.

Usage (from app/code/, on the server env that has scikit-learn):
  python aux_winloss_ablation.py                       # drop the 100d trio, 50d
  python aux_winloss_ablation.py --target both
  python aux_winloss_ablation.py --drop longi_vola100d,longi_spr100d
  python aux_winloss_ablation.py --test-daynums 12 --csv ablation.csv
  python aux_winloss_ablation.py --max-tickers 100     # fast smoke test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# scikit-learn-dependent imports (aux_winloss_shared) are loaded lazily in main()
# so this module's pure helpers can be imported/tested without the ML stack.

DEFAULT_DROP = ["longi_vola100d", "longi_spr100d", "longi_stepup100"]
_EPS = 1e-12


# ---------------------------------------------------------------------------
# Pure helpers (no scikit-learn — unit-testable anywhere)
# ---------------------------------------------------------------------------

def point_log_loss(probs_full_row: Sequence[float], y_true_int: int) -> float:
    """Negative log-likelihood of the realized class for one prediction.

    `probs_full_row` is the full 3-class probability vector (Loss, NoLoss, Win)
    as returned by fit_predict_multinomial; missing/zero classes are clipped so a
    confidently-wrong prediction is penalised rather than producing -inf.
    """
    p = float(probs_full_row[int(y_true_int)])
    return float(-np.log(min(max(p, _EPS), 1.0)))


def summarize_distribution(deltas: np.ndarray, neutral_eps: float,
                           harm_threshold: float) -> Dict[str, float]:
    """Summarise per-ticker Δlog-loss (ablated - full). Positive => removal hurt."""
    d = np.asarray(deltas, dtype=float)
    d = d[np.isfinite(d)]
    n = d.size
    if n == 0:
        return {"n_tickers": 0}
    worse = d[d > neutral_eps]
    better = d[d < -neutral_eps]
    return {
        "n_tickers": int(n),
        "n_worse": int(worse.size),
        "n_better": int(better.size),
        "n_neutral": int(n - worse.size - better.size),
        "n_harmed": int(np.sum(d > harm_threshold)),
        "mean_delta": float(np.mean(d)),
        "median_delta": float(np.median(d)),
        "p90_delta": float(np.percentile(d, 90)),
        "p95_delta": float(np.percentile(d, 95)),
        "max_delta": float(np.max(d)),
        "min_delta": float(np.min(d)),
    }


# ---------------------------------------------------------------------------
# Feature-frame construction for an arbitrary feature subset
# ---------------------------------------------------------------------------

def build_feature_frame_subset(output_dir: Path, feature_files: List[str]) -> pd.DataFrame:
    """Inner-join the given feature files into a (ticker, daynum, *features) frame.

    Mirrors aux_winloss_shared.build_feature_frame but for an arbitrary subset, so
    the ablated frame is built exactly like production would build it.
    """
    from aux_winloss_shared import read_indicator_matrix, stack_non_null  # lazy

    series_list = []
    for fname in feature_files:
        mat = read_indicator_matrix(output_dir / fname)
        series_list.append(stack_non_null(mat).rename(Path(fname).stem))
    x_df = pd.concat(series_list, axis=1, join="inner").reset_index()
    x_df.columns = ["ticker", "daynum"] + [Path(f).stem for f in feature_files]
    x_df["ticker"] = x_df["ticker"].astype(str)
    x_df["daynum"] = x_df["daynum"].astype(int)
    return x_df


# ---------------------------------------------------------------------------
# Evaluation for one target horizon
# ---------------------------------------------------------------------------

def _feature_row(x_case: pd.DataFrame, ticker: str, cols: List[str]) -> Optional[np.ndarray]:
    if ticker not in x_case.index:
        return None
    row = x_case.loc[ticker, cols]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return row.to_numpy(dtype=float).reshape(1, -1)


def evaluate_target(spec, feature_files_full: List[str], drop: List[str],
                    output_dir: Path, tickers: List[str], n_test_daynums: int,
                    min_stock_samples: int, reg_lambda: float, max_iter: int,
                    max_tickers: Optional[int]) -> dict:
    """Run the full-vs-ablated head-to-head for one TargetSpec."""
    from aux_winloss_shared import (  # lazy
        build_labeled_dataset, compute_error_counts, fit_predict_multinomial,
    )

    cols_full = [Path(f).stem for f in feature_files_full]
    files_abl = [f for f in feature_files_full if Path(f).stem not in drop]
    cols_abl = [Path(f).stem for f in files_abl]

    fdf_full = build_feature_frame_subset(output_dir, feature_files_full)
    fdf_abl = build_feature_frame_subset(output_dir, files_abl)
    data_full = build_labeled_dataset(fdf_full, output_dir, spec)
    data_abl = build_labeled_dataset(fdf_abl, output_dir, spec)

    # Realized test daynums = those present in the labeled (full) dataset; newest N.
    realized = sorted(int(d) for d in data_full["daynum"].unique())
    test_daynums = realized[-n_test_daynums:][::-1]  # newest-first

    if max_tickers is not None:
        tickers = tickers[:max_tickers]
    ticker_set = set(tickers)

    # Per-ticker accumulators of point log-losses.
    ll_full: Dict[str, List[float]] = {}
    ll_abl: Dict[str, List[float]] = {}
    # Aggregate error-count inputs.
    yt_full: List[int] = []; yp_full: List[int] = []
    yt_abl: List[int] = []; yp_abl: List[int] = []
    n_points = 0

    for di, daynum in enumerate(test_daynums, start=1):
        xcase_full = fdf_full[fdf_full["daynum"] == daynum].set_index("ticker")
        xcase_abl = fdf_abl[fdf_abl["daynum"] == daynum].set_index("ticker")
        test_rows = data_full[data_full["daynum"] == daynum]
        tr_full = {t: g for t, g in data_full[data_full["daynum"] < daynum].groupby("ticker", sort=False)}
        tr_abl = {t: g for t, g in data_abl[data_abl["daynum"] < daynum].groupby("ticker", sort=False)}

        print(f"    [{di}/{len(test_daynums)}] daynum {daynum}: {len(test_rows)} candidate test rows")

        for ticker, y_true in zip(test_rows["ticker"], test_rows["y_int"]):
            if ticker not in ticker_set:
                continue
            gf = tr_full.get(ticker); ga = tr_abl.get(ticker)
            if gf is None or ga is None:
                continue
            if gf.shape[0] < min_stock_samples or ga.shape[0] < min_stock_samples:
                continue
            xtf = _feature_row(xcase_full, ticker, cols_full)
            xta = _feature_row(xcase_abl, ticker, cols_abl)
            if xtf is None or xta is None:
                continue

            yt = int(y_true)
            _, pf = fit_predict_multinomial(
                gf[cols_full].to_numpy(float), gf["y_int"].to_numpy(int),
                xtf, reg_lambda, max_iter)
            _, pa = fit_predict_multinomial(
                ga[cols_abl].to_numpy(float), ga["y_int"].to_numpy(int),
                xta, reg_lambda, max_iter)

            ll_full.setdefault(ticker, []).append(point_log_loss(pf[0], yt))
            ll_abl.setdefault(ticker, []).append(point_log_loss(pa[0], yt))
            yt_full.append(yt); yp_full.append(int(np.argmax(pf[0])))
            yt_abl.append(yt); yp_abl.append(int(np.argmax(pa[0])))
            n_points += 1

    return {
        "test_daynums": test_daynums,
        "ll_full": ll_full,
        "ll_abl": ll_abl,
        "n_points": n_points,
        "errors_full": compute_error_counts(np.array(yt_full), np.array(yp_full)) if yt_full else {},
        "errors_abl": compute_error_counts(np.array(yt_abl), np.array(yp_abl)) if yt_abl else {},
        "cols_full": cols_full,
        "cols_abl": cols_abl,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _per_ticker_table(res: dict, min_points: int) -> pd.DataFrame:
    rows = []
    for ticker, lf in res["ll_full"].items():
        la = res["ll_abl"].get(ticker, [])
        if len(lf) < min_points or len(la) < min_points:
            continue
        mf, ma = float(np.mean(lf)), float(np.mean(la))
        rows.append({"ticker": ticker, "n_points": len(lf),
                     "logloss_full": round(mf, 4), "logloss_abl": round(ma, 4),
                     "delta": round(ma - mf, 4)})
    df = pd.DataFrame(rows)
    return df.sort_values("delta", ascending=False, ignore_index=True) if len(df) else df


def report_target(key: str, res: dict, min_points: int,
                  neutral_eps: float, harm_threshold: float, worst_k: int) -> pd.DataFrame:
    print(f"\n=== target={key} ===")
    print(f"  features: full={len(res['cols_full'])}  ablated={len(res['cols_abl'])}  "
          f"(dropped: {sorted(set(res['cols_full']) - set(res['cols_abl']))})")
    print(f"  test daynums: {res['test_daynums']}")
    print(f"  evaluated points: {res['n_points']}")

    df = _per_ticker_table(res, min_points)
    if df.empty:
        print(f"  No tickers with >= {min_points} test points — widen --test-daynums.")
        return df

    # Micro (point-weighted) aggregate.
    all_full = [v for vs in res["ll_full"].values() for v in vs]
    all_abl = [v for vs in res["ll_abl"].values() for v in vs]
    mfull, mabl = float(np.mean(all_full)), float(np.mean(all_abl))
    pct = (mabl - mfull) / mfull * 100 if mfull else float("nan")
    print(f"\n  Aggregate mean log-loss:  full={mfull:.4f}  ablated={mabl:.4f}  "
          f"({pct:+.2f}%   {'WORSE' if mabl > mfull else 'BETTER'} when ablated)")
    if res["errors_full"] and res["errors_abl"]:
        print(f"  Error counts (full -> ablated):")
        for k in res["errors_full"]:
            print(f"    {k:24}: {res['errors_full'][k]:6d} -> {res['errors_abl'][k]:6d}")

    s = summarize_distribution(df["delta"].to_numpy(), neutral_eps, harm_threshold)
    print(f"\n  Per-ticker Δlog-loss (ablated - full; + => removal hurts):")
    print(f"    tickers={s['n_tickers']}  worse={s['n_worse']}  better={s['n_better']}  "
          f"neutral={s['n_neutral']}  (|Δ|<{neutral_eps})")
    print(f"    harmed (Δ>{harm_threshold}): {s['n_harmed']}")
    print(f"    mean={s['mean_delta']:+.4f}  median={s['median_delta']:+.4f}  "
          f"p90={s['p90_delta']:+.4f}  p95={s['p95_delta']:+.4f}  "
          f"max={s['max_delta']:+.4f}  min={s['min_delta']:+.4f}")

    worst = df.head(worst_k)
    if len(worst):
        print(f"\n  Worst-hurt tickers (top {len(worst)} by Δ):")
        print(worst.to_string(index=False))

    verdict = ("LIKELY SAFE to drop" if s["n_harmed"] == 0 and mabl <= mfull
               else "CAUTION" if s["n_harmed"] > 0 else "MIXED (avg better, no harmed tickers)")
    print(f"\n  VERDICT (target={key}): {verdict}")
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Per-ticker ablation for Win/Loss features.")
    p.add_argument("--target", choices=["20d", "50d", "both"], default="50d")
    p.add_argument("--drop", type=str, default=",".join(DEFAULT_DROP),
                   help="Comma-separated feature stems to remove (default: 100d trio).")
    p.add_argument("--test-daynums", type=int, default=8,
                   help="How many newest realized daynums to evaluate on.")
    p.add_argument("--min-points", type=int, default=3,
                   help="Min test points for a ticker to enter the distribution.")
    p.add_argument("--min-stock-samples", type=int, default=150,
                   help="Min prior training rows per ticker (match production).")
    p.add_argument("--reg-lambda", type=float, default=0.01)
    p.add_argument("--max-iter", type=int, default=1000)
    p.add_argument("--neutral-eps", type=float, default=0.002,
                   help="|Δlog-loss| below this counts as neutral.")
    p.add_argument("--harm-threshold", type=float, default=0.02,
                   help="Δlog-loss above this flags a ticker as harmed.")
    p.add_argument("--worst-k", type=int, default=15)
    p.add_argument("--max-tickers", type=int, default=None,
                   help="Limit tickers for a fast smoke test.")
    p.add_argument("--csv", type=str, default=None,
                   help="Write per-ticker tables to this CSV path.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    from aux_winloss_shared import FEATURE_FILES, TARGET_SPECS, get_non_caret_tickers_from_potdat  # lazy
    import longi_winloss_probs as prod

    drop = [s.strip() for s in args.drop.split(",") if s.strip()]
    unknown = [d for d in drop if d not in {Path(f).stem for f in FEATURE_FILES}]
    if unknown:
        print(f"ERROR: --drop names not in FEATURE_FILES: {unknown}")
        return 1
    if len(drop) >= len(FEATURE_FILES):
        print("ERROR: --drop would remove every feature.")
        return 1

    spec_by_key = {s.key: s for s in TARGET_SPECS}
    targets = ["20d", "50d"] if args.target == "both" else [args.target]
    tickers = sorted(get_non_caret_tickers_from_potdat(prod.POTDAT_FILE))

    print("aux_winloss_ablation.py — Win/Loss feature ablation")
    print(f"  drop={drop}")
    print(f"  targets={targets}  test_daynums={args.test_daynums}  "
          f"min_stock_samples={args.min_stock_samples}  tickers={len(tickers)}"
          + (f" (capped {args.max_tickers})" if args.max_tickers else ""))

    csv_frames: List[pd.DataFrame] = []
    for key in targets:
        print(f"\n  Evaluating target {key} ...")
        res = evaluate_target(
            spec_by_key[key], list(FEATURE_FILES), drop, prod.OUTPUT_DIR, tickers,
            args.test_daynums, args.min_stock_samples, args.reg_lambda,
            args.max_iter, args.max_tickers)
        df = report_target(key, res, args.min_points, args.neutral_eps,
                           args.harm_threshold, args.worst_k)
        if args.csv and len(df):
            t = df.copy(); t.insert(0, "target", key); csv_frames.append(t)

    if args.csv and csv_frames:
        pd.concat(csv_frames, ignore_index=True).to_csv(
            args.csv, sep=";", decimal=",", index=False)
        print(f"\nWritten: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
