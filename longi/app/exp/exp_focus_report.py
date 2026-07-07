"""
exp_focus_report.py - Snapshot + historical reliability for a focus ticker list.

For each ticker in the list, per horizon (20d, 50d):
- newest experimental probabilities (p_win, p_loss), fit quality (fitR2) and
  top win/loss drivers for the given source variant (default Hnone)
- historical realized quality of the production model on that ticker
  (from the Phase 3 matrices): cells scored, mean/median log-loss, mean Brier,
  and the share of cells where the realized class had been given probability 0.000

Flags:
--tickers-file F   one ticker per line (required)
--source S         exp variant for the snapshot columns (default: Hnone)

Output: app/exp/output/exp_focus_report_{source}.csv (European CSV) + printed table.
Requires: exp_winloss_probs.py has been run for the source (snapshot columns) and
exp_winloss_quality.py --source prod (historical columns).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from exp_shared import EXP_OUTPUT_DIR, append_manifest, format_cell
from aux_winloss_shared import TARGET_SPECS, ensure_files_exist, read_indicator_matrix

EXP_DIR = Path(__file__).resolve().parent
ZERO_PENALTY_THRESHOLD = 27.0  # -ln(0 + 1e-12) = 27.63: realized class had probability 0.000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Focus-ticker report from sandbox artifacts.")
    parser.add_argument("--tickers-file", type=str, required=True, help="File with one ticker per line.")
    parser.add_argument("--source", type=str, default="Hnone", help="Exp variant for snapshot columns.")
    return parser.parse_args()


def read_string_matrix(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype=str)
    df = df.set_index(df.columns[0])
    day_cols = [c for c in df.columns if str(c).strip().isdigit()]
    return df[day_cols]


def newest_filled_daynum(mat: pd.DataFrame) -> Optional[str]:
    for c in mat.columns:  # header order is newest-first
        if mat[c].notna().any():
            return c
    return None


def main() -> int:
    args = parse_args()
    t0 = time.time()

    tickers = [t.strip() for t in Path(args.tickers_file).read_text().splitlines() if t.strip()]
    print(f"exp_focus_report.py: {len(tickers)} focus tickers, snapshot source _{args.source}")

    rows: List[Dict[str, str]] = []
    for spec in TARGET_SPECS:
        h = spec.key
        p_win_path = EXP_OUTPUT_DIR / f"exp_longi_P{h}_win_{args.source}.csv"
        p_loss_path = EXP_OUTPUT_DIR / f"exp_longi_P{h}_loss_{args.source}.csv"
        fitr2_path = EXP_OUTPUT_DIR / f"exp_longi_fitR2_{h}_{args.source}.csv"
        drv_win_path = EXP_OUTPUT_DIR / f"exp_longi_drivers{h}_win_{args.source}.csv"
        drv_loss_path = EXP_OUTPUT_DIR / f"exp_longi_drivers{h}_loss_{args.source}.csv"
        ll_path = EXP_OUTPUT_DIR / f"exp_longi_logloss_{h}_prod.csv"
        br_path = EXP_OUTPUT_DIR / f"exp_longi_brier_{h}_prod.csv"
        ensure_files_exist([p_win_path, p_loss_path, fitr2_path, drv_win_path, drv_loss_path, ll_path, br_path])

        p_win = read_indicator_matrix(p_win_path)
        p_loss = read_indicator_matrix(p_loss_path)
        fitr2 = read_indicator_matrix(fitr2_path)
        drv_win = read_string_matrix(drv_win_path)
        drv_loss = read_string_matrix(drv_loss_path)
        logloss = read_indicator_matrix(ll_path)
        brier = read_indicator_matrix(br_path)

        snap_col = newest_filled_daynum(p_win.astype(float))
        snap_daynum = int(snap_col) if snap_col is not None else None
        print(f"  {h}: snapshot daynum {snap_daynum}")

        for ticker in tickers:
            row: Dict[str, str] = {"ticker": ticker, "horizon": h,
                                   "snap_daynum": str(snap_daynum) if snap_daynum else ""}
            if snap_daynum is not None and ticker in p_win.index:
                row["p_win"] = format_cell(float(p_win.at[ticker, snap_daynum]))
                row["p_loss"] = format_cell(float(p_loss.at[ticker, snap_daynum]))
                row["fitR2"] = format_cell(float(fitr2.at[ticker, snap_daynum])) if ticker in fitr2.index else ""
                snap_str = str(snap_daynum)  # string matrices keep string column names

                def _drv(mat: pd.DataFrame) -> str:
                    if ticker not in mat.index or snap_str not in mat.columns:
                        return ""
                    v = mat.at[ticker, snap_str]
                    return v if isinstance(v, str) else ""

                row["drivers_win"] = _drv(drv_win)
                row["drivers_loss"] = _drv(drv_loss)
                if pd.isna(p_win.at[ticker, snap_daynum]):
                    row["p_win"] = row["p_loss"] = ""
            else:
                row.update({"p_win": "", "p_loss": "", "fitR2": "", "drivers_win": "", "drivers_loss": ""})

            if ticker in logloss.index:
                ll = logloss.loc[ticker].astype(float).dropna()
                br = brier.loc[ticker].astype(float).dropna()
                row["hist_n"] = str(len(ll))
                if len(ll) > 0:
                    row["hist_mean_logloss"] = format_cell(float(ll.mean()))
                    row["hist_median_logloss"] = format_cell(float(ll.median()))
                    row["hist_mean_brier"] = format_cell(float(br.mean()))
                    row["hist_pct_zeroprob"] = format_cell(float((ll > ZERO_PENALTY_THRESHOLD).mean() * 100), 1)
                else:
                    row.update({"hist_mean_logloss": "", "hist_median_logloss": "",
                                "hist_mean_brier": "", "hist_pct_zeroprob": ""})
            else:
                row.update({"hist_n": "0", "hist_mean_logloss": "", "hist_median_logloss": "",
                            "hist_mean_brier": "", "hist_pct_zeroprob": ""})
            rows.append(row)

    cols = ["ticker", "horizon", "snap_daynum", "p_win", "p_loss", "fitR2", "drivers_win", "drivers_loss",
            "hist_n", "hist_mean_logloss", "hist_median_logloss", "hist_mean_brier", "hist_pct_zeroprob"]
    out_df = pd.DataFrame(rows)[cols]
    out_path = EXP_OUTPUT_DIR / f"exp_focus_report_{args.source}.csv"
    out_df.to_csv(out_path, sep=";", index=False)
    print(f"  Written: {out_path.name}")

    for h in [spec.key for spec in TARGET_SPECS]:
        sub = out_df[out_df["horizon"] == h]
        print(f"\n  {h} snapshot (source _{args.source}) + production history:")
        print(f"    {'ticker':<12}{'p_win':<8}{'p_loss':<8}{'fitR2':<8}{'drivers_win':<28}"
              f"{'n':<6}{'mean_ll':<9}{'med_ll':<8}{'%zero':<6}")
        for _, r in sub.iterrows():
            print(f"    {r['ticker']:<12}{r['p_win']:<8}{r['p_loss']:<8}{r['fitR2']:<8}"
                  f"{(r['drivers_win'] or '')[:26]:<28}{r['hist_n']:<6}"
                  f"{r['hist_mean_logloss']:<9}{r['hist_median_logloss']:<8}{r['hist_pct_zeroprob']:<6}")

    append_manifest("exp_focus_report.py", " ".join(sys.argv[1:]), time.time() - t0, "snapshot + full history")
    print(f"\nSUCCESS: focus report complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
