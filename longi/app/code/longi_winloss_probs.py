"""
Historical Win/Loss probability matrices.

Creates/updates four longi-style matrix files:
- longi_P20d_win.csv
- longi_P20d_loss.csv
- longi_P50d_win.csv
- longi_P50d_loss.csv

Cells are blank when a probability is not calculable (missing features, insufficient
train rows, caret tickers, etc.).

Default behavior updates only the newest daynum (cheap enough for daily pipeline).
Use --backfill-all to build historical columns (can be slow).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd

from aux_win_loss_shared import (
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
ACROSS_DIR = Path(__file__).parent.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"

OUTPUT_FILES = {
    ("20d", "win"): OUTPUT_DIR / "longi_P20d_win.csv",
    ("20d", "loss"): OUTPUT_DIR / "longi_P20d_loss.csv",
    ("50d", "win"): OUTPUT_DIR / "longi_P50d_win.csv",
    ("50d", "loss"): OUTPUT_DIR / "longi_P50d_loss.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create historical win/loss probability longi matrices.")
    parser.add_argument("--daynum", type=int, default=None, help="Only compute a specific daynum.")
    parser.add_argument(
        "--backfill-all",
        action="store_true",
        help="Compute all scoreable feature daynums (can be slow).",
    )
    parser.add_argument(
        "--max-daynums",
        type=int,
        default=None,
        help="Limit number of daynums processed (newest-first; mainly for staged backfills).",
    )
    parser.add_argument("--min-stock-samples", type=int, default=150, help="Min training rows per ticker.")
    parser.add_argument("--reg-lambda", type=float, default=0.01, help="L2 regularization strength.")
    parser.add_argument("--max-iter", type=int, default=250, help="Maximum optimizer iterations.")
    parser.add_argument("--prob-decimals", type=int, default=6, help="Decimals written to longi probability cells.")
    parser.add_argument(
        "--across-prune",
        action="store_true",
        help=(
            "After writing probability matrices, refresh across files for the selected daynum(s) "
            "and prune app/output/across_*.csv to those daynums."
        ),
    )
    return parser.parse_args()


def _get_feature_row(
    x_case: pd.DataFrame, ticker: str, feature_cols: List[str]
) -> np.ndarray | None:
    if ticker not in x_case.index:
        return None
    row = x_case.loc[ticker, feature_cols]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return row.to_numpy(dtype=float).reshape(1, -1)


def predict_for_target_day(
    data: pd.DataFrame,
    feature_df: pd.DataFrame,
    tickers: List[str],
    daynum_case: int,
    min_stock_samples: int,
    reg_lambda: float,
    max_iter: int,
) -> Dict[str, Tuple[float, float]]:
    """
    Predict per-ticker win/loss probabilities for one target and one daynum.

    Returns:
    ticker -> (p_win, p_loss), NaNs for non-calculable rows
    """
    feature_cols = [Path(name).stem for name in FEATURE_FILES]
    x_case = feature_df[feature_df["daynum"] == daynum_case].set_index("ticker")
    train_all = data[data["daynum"] < daynum_case]
    train_by_ticker = {ticker: grp for ticker, grp in train_all.groupby("ticker", sort=False)}

    out: Dict[str, Tuple[float, float]] = {}

    for ticker in tickers:
        x_row = _get_feature_row(x_case, ticker, feature_cols)
        if x_row is None:
            out[ticker] = (np.nan, np.nan)
            continue

        stock_train = train_by_ticker.get(ticker)
        if stock_train is None or stock_train.shape[0] < min_stock_samples:
            out[ticker] = (np.nan, np.nan)
            continue

        x_train = stock_train[feature_cols].to_numpy(dtype=float)
        y_train = stock_train["y_int"].to_numpy(dtype=int)

        mean, std = standardize_fit(x_train)
        x_train_std = (x_train - mean) / std
        x_test_std = (x_row - mean) / std

        _, probs = fit_predict_multinomial(
            x_train=x_train_std,
            y_train=y_train,
            x_test=x_test_std,
            reg_lambda=reg_lambda,
            max_iter=max_iter,
        )
        out[ticker] = (
            float(probs[0, CLASS_TO_INT["Win"]]),
            float(probs[0, CLASS_TO_INT["Loss"]]),
        )

    return out


def read_potdat_layout(potdat_path: Path) -> Tuple[List[str], List[int], List[str]]:
    """Return PotDat header row (strings), numeric daynums in header order, and ticker rows in source order."""
    with open(potdat_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        tickers = [row[0] for row in reader if row]

    daynums: List[int] = []
    for col in header[1:]:
        s = str(col).strip()
        if s.isdigit():
            daynums.append(int(s))

    return header, daynums, tickers


def read_existing_matrix_cells(path: Path) -> Dict[str, Dict[int, str]]:
    """Read existing longi matrix values keyed by ticker/daynum, preserving strings."""
    if not path.exists():
        return {}

    out: Dict[str, Dict[int, str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        if not header:
            return out

        daynum_cols: List[Tuple[int, int]] = []
        for idx, col in enumerate(header[1:], start=1):
            s = str(col).strip()
            if s.isdigit():
                daynum_cols.append((idx, int(s)))

        for row in reader:
            if not row:
                continue
            ticker = row[0]
            cells = out.setdefault(ticker, {})
            for idx, daynum in daynum_cols:
                cells[daynum] = row[idx] if idx < len(row) else ""
    return out


def format_prob(value: float, decimals: int) -> str:
    """European decimal formatting, blank for NaN/non-finite."""
    if value is None:
        return ""
    if not np.isfinite(value):
        return ""
    return f"{float(value):.{decimals}f}".replace(".", ",")


def select_daynums(
    args: argparse.Namespace,
    feature_df: pd.DataFrame,
    potdat_daynums: List[int],
) -> List[int]:
    """Select daynums to compute, always respecting PotDat header order (newest-first)."""
    if args.daynum is not None and args.backfill_all:
        raise ValueError("Use either --daynum or --backfill-all, not both.")

    if args.daynum is not None:
        return [int(args.daynum)]

    if not args.backfill_all:
        return [int(max(potdat_daynums))]

    if args.max_daynums is not None and int(args.max_daynums) <= 0:
        raise ValueError("--max-daynums must be > 0.")

    selected = list(potdat_daynums)

    if args.max_daynums is not None and args.max_daynums > 0:
        selected = selected[: int(args.max_daynums)]

    return selected


def write_probability_matrix(
    path: Path,
    ticker_header: str,
    daynums_to_write: List[int],
    ticker_rows: List[str],
    existing_cells: Dict[str, Dict[int, str]],
    overlay_cells: Dict[Tuple[str, int], str],
) -> None:
    """Write one longi matrix using PotDat layout and overlaying recomputed cells."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([ticker_header] + [str(int(d)) for d in daynums_to_write])

        for ticker in ticker_rows:
            prior = existing_cells.get(ticker, {})
            row = [ticker]
            for daynum in daynums_to_write:
                key = (ticker, daynum)
                if key in overlay_cells:
                    row.append(overlay_cells[key])
                else:
                    row.append(prior.get(daynum, ""))
            writer.writerow(row)


def get_existing_across_files() -> Dict[int, Path]:
    """Return existing across files keyed by daynum."""
    out: Dict[int, Path] = {}
    if not ACROSS_DIR.exists():
        return out

    for path in ACROSS_DIR.glob("across_*.csv"):
        name = path.name
        if not (name.startswith("across_") and name.endswith(".csv")):
            continue
        daynum_str = name[len("across_") : -4]
        if daynum_str.isdigit():
            out[int(daynum_str)] = path
    return out


def refresh_across_files_for_daynums(daynums: List[int]) -> None:
    """
    Rebuild across files for the provided daynums so they include updated prob columns.

    Imports longi_across lazily to avoid the cost when not requested.
    """
    if not daynums:
        return

    import longi_across  # local module in app/code

    print("  Refreshing across files for selected daynum(s)")
    if len(daynums) <= 10:
        print(f"  Across daynums: {', '.join(map(str, daynums))}")
    else:
        print(f"  Across daynum range: {daynums[0]} .. {daynums[-1]}")

    for idx, daynum in enumerate(daynums, start=1):
        print(f"    [{idx}/{len(daynums)}] daynum {daynum}")
        tickers, metric_data = longi_across.extract_cross_sectional_data(int(daynum), quiet=True)
        if not tickers:
            raise RuntimeError(f"Failed to extract across data for daynum {daynum} (no rows returned)")
        longi_across.write_cross_sectional_csv(int(daynum), tickers, metric_data)


def prune_across_files_to_targets(target_daynums: List[int]) -> int:
    """Delete local across files not in target set."""
    target_set: Set[int] = {int(d) for d in target_daynums}
    existing = get_existing_across_files()
    stale = sorted([d for d in existing.keys() if d not in target_set])

    if not stale:
        print("  Across prune: nothing to delete")
        return 0

    print(f"  Across prune: deleting {len(stale)} non-target file(s)")
    deleted = 0
    for daynum in stale:
        path = existing[daynum]
        path.unlink()
        print(f"    deleted {path.name}")
        deleted += 1
    return deleted


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    feature_paths = [OUTPUT_DIR / fname for fname in FEATURE_FILES]
    target_paths = [OUTPUT_DIR / spec.target_file for spec in TARGET_SPECS]
    ensure_files_exist([POTDAT_FILE] + feature_paths + target_paths)

    print("longi_winloss_probs.py: Win/Loss probability matrices")
    if args.backfill_all:
        print("  Mode: backfill-all (historical; can be slow)")
    elif args.daynum is not None:
        print(f"  Mode: single daynum ({int(args.daynum)})")
    else:
        print("  Mode: newest daynum only (daily update)")

    header, potdat_daynums, potdat_ticker_rows = read_potdat_layout(POTDAT_FILE)
    non_caret_tickers = sorted(get_non_caret_tickers_from_potdat(POTDAT_FILE))
    caret_or_other_rows = len(potdat_ticker_rows) - len(non_caret_tickers)

    print(f"  PotDat rows: {len(potdat_ticker_rows)} (non-caret scored: {len(non_caret_tickers)})")
    if caret_or_other_rows > 0:
        print(f"  Caret/other rows left blank: {caret_or_other_rows}")

    feature_df = build_feature_frame(OUTPUT_DIR)
    try:
        daynums_to_compute = select_daynums(args, feature_df, potdat_daynums)
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
    if args.across_prune:
        print("  Across files: refresh selected daynum(s) and prune non-target files")

    target_data: Dict[str, pd.DataFrame] = {}
    for spec in TARGET_SPECS:
        print(f"  Preparing target dataset {spec.key} ({spec.target_file})")
        target_data[spec.key] = build_labeled_dataset(feature_df, OUTPUT_DIR, spec)

    existing_cells_by_file = {path: read_existing_matrix_cells(path) for path in OUTPUT_FILES.values()}
    overlay_cells_by_file: Dict[Path, Dict[Tuple[str, int], str]] = {path: {} for path in OUTPUT_FILES.values()}

    all_row_tickers_set = set(potdat_ticker_rows)
    progress_every = 1 if len(daynums_to_compute) <= 20 else 10

    for idx, daynum_case in enumerate(daynums_to_compute, start=1):
        if idx == 1 or idx % progress_every == 0 or idx == len(daynums_to_compute):
            print(f"  [{idx}/{len(daynums_to_compute)}] Scoring daynum {daynum_case}")

        day_results: Dict[str, Dict[str, Tuple[float, float]]] = {}
        for spec in TARGET_SPECS:
            day_results[spec.key] = predict_for_target_day(
                data=target_data[spec.key],
                feature_df=feature_df,
                tickers=non_caret_tickers,
                daynum_case=int(daynum_case),
                min_stock_samples=int(args.min_stock_samples),
                reg_lambda=float(args.reg_lambda),
                max_iter=int(args.max_iter),
            )

        # Explicitly clear recomputed column cells so stale values do not survive rewrites.
        for file_path, overlay in overlay_cells_by_file.items():
            for ticker in all_row_tickers_set:
                overlay[(ticker, int(daynum_case))] = ""

        for ticker in non_caret_tickers:
            p20_win, p20_loss = day_results["20d"][ticker]
            p50_win, p50_loss = day_results["50d"][ticker]

            overlay_cells_by_file[OUTPUT_FILES[("20d", "win")]][(ticker, int(daynum_case))] = format_prob(
                p20_win, int(args.prob_decimals)
            )
            overlay_cells_by_file[OUTPUT_FILES[("20d", "loss")]][(ticker, int(daynum_case))] = format_prob(
                p20_loss, int(args.prob_decimals)
            )
            overlay_cells_by_file[OUTPUT_FILES[("50d", "win")]][(ticker, int(daynum_case))] = format_prob(
                p50_win, int(args.prob_decimals)
            )
            overlay_cells_by_file[OUTPUT_FILES[("50d", "loss")]][(ticker, int(daynum_case))] = format_prob(
                p50_loss, int(args.prob_decimals)
            )

    # When using capped historical backfill, write exactly the selected historical columns.
    # This makes repeated staged runs (e.g., 20 then 2) shrink the matrix as requested.
    matrix_daynums_to_write = potdat_daynums
    if args.backfill_all and args.max_daynums is not None:
        matrix_daynums_to_write = list(daynums_to_compute)

    print("  Writing probability matrices")
    for path in OUTPUT_FILES.values():
        write_probability_matrix(
            path=path,
            ticker_header=(header[0] if header else "ticker"),
            daynums_to_write=matrix_daynums_to_write,
            ticker_rows=potdat_ticker_rows,
            existing_cells=existing_cells_by_file[path],
            overlay_cells=overlay_cells_by_file[path],
        )
        print(f"    {path.name}")

    if args.across_prune:
        try:
            refresh_across_files_for_daynums(daynums_to_compute)
            prune_across_files_to_targets(daynums_to_compute)
        except Exception as e:
            print(f"ERROR: Across refresh/prune failed: {e}")
            return 1

    if not args.backfill_all and args.daynum is None:
        newest = get_max_daynum_from_potdat(POTDAT_FILE)
        print(f"SUCCESS: updated newest probability columns for daynum {newest}")
    else:
        print(f"SUCCESS: updated probability matrices for {len(daynums_to_compute)} daynum(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
