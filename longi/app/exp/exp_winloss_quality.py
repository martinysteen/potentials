"""
exp_winloss_quality.py - Realized prediction quality + A/B vs production.

Scores win/loss probability matrices against what actually happened
(future_gain files). Pure arithmetic on files - no fitting, runs in seconds.
Scores BOTH production matrices and any experimental variant with identical
code, enabling honest A/B comparison.

Flags:
--source S    Which probability matrices to score. 'prod' reads production
              app/output/longi_P*.csv (read-only); anything else (e.g. 'Hnone',
              'H63') reads app/exp/output/exp_longi_P*_{S}.csv.
              Repeatable: --source prod --source Hnone --source H63

Outputs per source and horizon (app/exp/output/, full longi layout):
- exp_longi_logloss_{h}_{source}.csv   per-cell -log(p_realized + 1e-12);
                                       ln 3 ~ 1.099 = "uniform ignorance" reference
- exp_longi_brier_{h}_{source}.csv     sum_k (p_k - onehot_k)^2, range [0,2]
- exp_day_summary_{source}.csv         tidy long cross-sections, one row per
                                       (daynum, horizon, metric); rows replaced
                                       by key on rerun, sorted daynum-descending

Cells are blank when the probability cell is blank or the outcome is not yet
known (the newest `horizon` columns are blank by construction - correct, not a bug).
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from exp_shared import (
    EXP_OUTPUT_DIR,
    append_manifest,
    format_cell,
    read_potdat_layout,
    write_probability_matrix,
)
from aux_winloss_shared import (  # production helpers, read-only imports
    CLASS_TO_INT,
    TARGET_SPECS,
    ensure_files_exist,
    label_from_gain,
    read_indicator_matrix,
    stack_non_null,
)

EXP_DIR = Path(__file__).resolve().parent
INPUT_DIR = EXP_DIR.parent / "input"
PROD_OUTPUT_DIR = EXP_DIR.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"

EPS = 1e-12
UNIFORM_IGNORANCE = math.log(3.0)  # ~1.099, log-loss of always predicting 1/3,1/3,1/3

SUMMARY_COLS = ["daynum", "horizon", "metric", "value"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realized quality scoring of win/loss probability matrices.")
    parser.add_argument(
        "--source", action="append", default=None,
        help="Probability source: 'prod' or an exp suffix like 'Hnone'/'H63'. Repeatable.",
    )
    args = parser.parse_args()
    if not args.source:
        args.source = ["prod"]
    return args


def prob_paths(source: str, key: str) -> Tuple[Path, Path]:
    if source == "prod":
        return (PROD_OUTPUT_DIR / f"longi_P{key}_win.csv",
                PROD_OUTPUT_DIR / f"longi_P{key}_loss.csv")
    return (EXP_OUTPUT_DIR / f"exp_longi_P{key}_win_{source}.csv",
            EXP_OUTPUT_DIR / f"exp_longi_P{key}_loss_{source}.csv")


def read_string_matrix_stacked(path: Path) -> pd.Series:
    """Stack a longi matrix of strings (driver cells) to a (ticker, daynum) series."""
    df = pd.read_csv(path, sep=";", dtype=str)
    df = df.set_index(df.columns[0])
    day_cols = [c for c in df.columns if str(c).strip().isdigit()]
    mat = df[day_cols]
    mat.columns = [int(c) for c in mat.columns]
    s = mat.stack().dropna()
    return s[s != ""]


def build_scored_frame(source: str, spec) -> pd.DataFrame:
    """
    Long frame of all scoreable cells for one source and horizon:
    ticker, daynum, p_win, p_loss, p_noloss, y_int, logloss, brier.

    A cell is scoreable when both probabilities and the realized gain exist.
    """
    win_path, loss_path = prob_paths(source, spec.key)
    gain_path = PROD_OUTPUT_DIR / spec.target_file
    ensure_files_exist([win_path, loss_path, gain_path])

    p_win = stack_non_null(read_indicator_matrix(win_path)).rename("p_win")
    p_loss = stack_non_null(read_indicator_matrix(loss_path)).rename("p_loss")
    gain = stack_non_null(read_indicator_matrix(gain_path)).rename("gain")

    df = pd.concat([p_win, p_loss, gain], axis=1, join="inner").reset_index()
    df.columns = ["ticker", "daynum", "p_win", "p_loss", "gain"]
    df["daynum"] = df["daynum"].astype(int)

    # Realized class via imported label_from_gain - threshold logic is never duplicated here.
    df["y_int"] = df["gain"].map(
        lambda g: CLASS_TO_INT[label_from_gain(float(g), spec.win_threshold, spec.loss_threshold)]
    ).astype(int)

    # Reconstruct p_noloss; clamp tiny negative rounding artifacts to 0 and renormalize.
    p_no = (1.0 - df["p_win"] - df["p_loss"]).clip(lower=0.0)
    total = df["p_win"] + df["p_loss"] + p_no
    df["p_win"] = df["p_win"] / total
    df["p_loss"] = df["p_loss"] / total
    df["p_noloss"] = p_no / total

    probs = df[["p_loss", "p_noloss", "p_win"]].to_numpy(dtype=float)  # column order = class ints 0,1,2
    y = df["y_int"].to_numpy(dtype=int)
    p_realized = probs[np.arange(len(df)), y]
    df["logloss"] = -np.log(p_realized + EPS)
    df["brier"] = ((probs - np.eye(3)[y]) ** 2).sum(axis=1)
    return df


def write_metric_matrix(
    path: Path,
    df: pd.DataFrame,
    value_col: str,
    header0: str,
    potdat_daynums: List[int],
    potdat_ticker_rows: List[str],
) -> None:
    """Write one full-history metric matrix in longi layout (blank = not scoreable)."""
    cells: Dict[str, Dict[int, str]] = {}
    for ticker, daynum, value in zip(df["ticker"], df["daynum"], df[value_col]):
        cells.setdefault(str(ticker), {})[int(daynum)] = format_cell(float(value))
    write_probability_matrix(
        path=path,
        ticker_header=header0,
        daynums_to_write=potdat_daynums,
        ticker_rows=potdat_ticker_rows,
        existing_cells=cells,
        overlay_cells={},
    )


def summary_rows_for(source: str, spec, df: pd.DataFrame) -> List[Tuple[str, str, str, str]]:
    """Tidy long rows (daynum, horizon, metric, value) for one source and horizon."""
    agg = df.groupby("daynum").agg(
        n_scored=("logloss", "size"),
        median_p_win=("p_win", "median"),
        median_p_loss=("p_loss", "median"),
        mean_logloss=("logloss", "mean"),
        mean_brier=("brier", "mean"),
    )

    fitr2_by_day: Optional[pd.Series] = None
    drivers_by_day: Dict[int, List[str]] = {}
    if source != "prod":
        fitr2_path = EXP_OUTPUT_DIR / f"exp_longi_fitR2_{spec.key}_{source}.csv"
        if fitr2_path.exists():
            s = stack_non_null(read_indicator_matrix(fitr2_path))
            fitr2_by_day = s.groupby(level=1).median()
        drivers_path = EXP_OUTPUT_DIR / f"exp_longi_drivers{spec.key}_win_{source}.csv"
        if drivers_path.exists():
            drv = read_string_matrix_stacked(drivers_path)
            first_tokens = drv.str.split("|").str[0]
            for daynum, grp in first_tokens.groupby(level=1):
                top = grp.value_counts().head(3)
                drivers_by_day[int(daynum)] = [f"{name}:{int(cnt)}" for name, cnt in top.items()]

    rows: List[Tuple[str, str, str, str]] = []
    for daynum, r in agg.iterrows():
        dn = str(int(daynum))
        rows.append((dn, spec.key, "n_scored", str(int(r["n_scored"]))))
        rows.append((dn, spec.key, "median_p_win", format_cell(float(r["median_p_win"]))))
        rows.append((dn, spec.key, "median_p_loss", format_cell(float(r["median_p_loss"]))))
        rows.append((dn, spec.key, "mean_logloss", format_cell(float(r["mean_logloss"]))))
        rows.append((dn, spec.key, "mean_brier", format_cell(float(r["mean_brier"]))))
        if fitr2_by_day is not None and int(daynum) in fitr2_by_day.index:
            rows.append((dn, spec.key, "median_fitR2", format_cell(float(fitr2_by_day.loc[int(daynum)]))))
        for i, token_count in enumerate(drivers_by_day.get(int(daynum), []), start=1):
            rows.append((dn, spec.key, f"top_driver_{i}", token_count))
    return rows


def update_day_summary(source: str, new_rows: List[Tuple[str, str, str, str]]) -> Path:
    """Replace rows by (daynum, horizon, metric) key; keep sorted daynum-descending."""
    path = EXP_OUTPUT_DIR / f"exp_day_summary_{source}.csv"
    new_df = pd.DataFrame(new_rows, columns=SUMMARY_COLS).astype(str)

    if path.exists():
        old = pd.read_csv(path, sep=";", dtype=str)
        old_keys = old.set_index(["daynum", "horizon", "metric"]).index
        new_keys = new_df.set_index(["daynum", "horizon", "metric"]).index
        out = pd.concat([old[~old_keys.isin(new_keys)], new_df], ignore_index=True)
    else:
        out = new_df

    out["_dn"] = out["daynum"].astype(int)
    out = out.sort_values(["_dn", "horizon", "metric"], ascending=[False, True, True]).drop(columns="_dn")
    out.to_csv(path, sep=";", index=False)
    return path


def main() -> int:
    args = parse_args()
    t0 = time.time()
    EXP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("exp_winloss_quality.py: realized quality scoring (sandbox)")
    print(f"  Sources: {', '.join(args.source)}")
    print(f"  Uniform-ignorance log-loss reference: ln 3 = {UNIFORM_IGNORANCE:.3f}")

    header, potdat_daynums, potdat_ticker_rows = read_potdat_layout(POTDAT_FILE)
    header0 = header[0] if header else "ticker"

    # (source, horizon) -> stats for the end-of-run comparison table
    stats: Dict[Tuple[str, str], Dict[str, float]] = {}

    for source in args.source:
        t_src = time.time()
        for spec in TARGET_SPECS:
            df = build_scored_frame(source, spec)
            if df.empty:
                print(f"  {source} {spec.key}: no scoreable cells - skipped")
                continue

            logloss_path = EXP_OUTPUT_DIR / f"exp_longi_logloss_{spec.key}_{source}.csv"
            brier_path = EXP_OUTPUT_DIR / f"exp_longi_brier_{spec.key}_{source}.csv"
            write_metric_matrix(logloss_path, df, "logloss", header0, potdat_daynums, potdat_ticker_rows)
            write_metric_matrix(brier_path, df, "brier", header0, potdat_daynums, potdat_ticker_rows)

            rows = summary_rows_for(source, spec, df)
            summary_path = update_day_summary(source, rows)

            mean_ll = float(df["logloss"].mean())
            mean_br = float(df["brier"].mean())
            median_fitr2 = float("nan")
            fitr2_path = EXP_OUTPUT_DIR / f"exp_longi_fitR2_{spec.key}_{source}.csv"
            if source != "prod" and fitr2_path.exists():
                s = stack_non_null(read_indicator_matrix(fitr2_path))
                # Compare like-for-like: fitR2 only on cells that were realized-scored.
                scored_idx = pd.MultiIndex.from_frame(df[["ticker", "daynum"]])
                s = s[s.index.isin(scored_idx)]
                if len(s) > 0:
                    median_fitr2 = float(s.median())
            stats[(source, spec.key)] = {
                "n": len(df),
                "daynums": df["daynum"].nunique(),
                "mean_logloss": mean_ll,
                "mean_brier": mean_br,
                "median_fitR2": median_fitr2,
            }
            print(f"  {source} {spec.key}: scored {len(df)} cells over {df['daynum'].nunique()} daynums | "
                  f"mean logloss={mean_ll:.3f} mean brier={mean_br:.3f}")
            print(f"    {logloss_path.name}, {brier_path.name}, {summary_path.name}")
        print(f"  {source}: {time.time() - t_src:.1f}s")

    if len(args.source) > 1:
        print("\n  A/B comparison (mean log-loss per source; lower is better):")
        for spec in TARGET_SPECS:
            cells = []
            for source in args.source:
                st = stats.get((source, spec.key))
                cells.append(f"{source}={st['mean_logloss']:.3f}" if st else f"{source}=n/a")
            print(f"    {spec.key}: " + "  ".join(cells))
        print("\n  Overfitting signal per source (proxy gap = median_fitR2 - (1 - mean_logloss/ln3);")
        print("  fitR2 is in-sample, the proxy is realized - a large positive gap = fits look better than they predict):")
        for spec in TARGET_SPECS:
            for source in args.source:
                st = stats.get((source, spec.key))
                if not st:
                    continue
                if np.isfinite(st["median_fitR2"]):
                    realized_proxy = 1.0 - st["mean_logloss"] / UNIFORM_IGNORANCE
                    gap = st["median_fitR2"] - realized_proxy
                    print(f"    {spec.key} {source}: fitR2={st['median_fitR2']:.3f} "
                          f"realized-proxy={realized_proxy:.3f} gap={gap:+.3f}")
                else:
                    print(f"    {spec.key} {source}: no fitR2 available (production or missing file)")

    wall = time.time() - t0
    append_manifest("exp_winloss_quality.py", " ".join(sys.argv[1:]) or "(defaults)", wall,
                    "full-history per source")
    print(f"\nSUCCESS: quality scoring complete in {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
