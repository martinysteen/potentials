"""
Compare strategies by best run per strategy and overall, for each criterion.

For each criterion the output shows:
  - One row per strategy (its best run for that criterion), sorted best→worst
  - One final "Best overall" row

Criteria:
  1. Best avg_gain20d  — highest avg_gain20d, tiebreaker: highest Worst_20d
  2. Best avg_gain50d  — highest avg_gain50d, tiebreaker: highest Worst_50d
  3. Best Worst_20d    — highest Worst_20d (least negative), tiebreaker: avg_gain20d
  4. Best Worst_50d    — highest Worst_50d (least negative), tiebreaker: avg_gain50d

Output:
  app/report/best_strategy.xlsx  — one section per criterion

Usage (from app/code/):
  python best_strategy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from shared.config import REPORT_ROOT

# (label, primary sort column, tiebreaker column)
CRITERIA: list[tuple[str, str, str]] = [
    ("Best avg_gain20d", "avg_gain20d", "Worst_20d"),
    ("Best avg_gain50d", "avg_gain50d", "Worst_50d"),
    ("Best Worst_20d",   "Worst_20d",   "avg_gain20d"),
    ("Best Worst_50d",   "Worst_50d",   "avg_gain50d"),
]

OUTPUT_XLSX = REPORT_ROOT / "best_strategy.xlsx"

# Columns shown first (in this order), then any remaining cols
_KEY_COLS = [
    "StrategyName", "Run#",
    "avg_gain20d", "avg_gain50d",
    "chain_cagr20d", "chain_cagr50d", "chain_ret20d", "chain_ret50d",
    "chain_n20d", "chain_n50d",
    "Worst_20d", "Worst_50d",
    "N_20d_loss", "N_50d_loss",
    "N_hops", "N_hops_active",
    "focusset_size", "step", "No_go_GSPC_rsi",
    "source_file",
]
_GAIN_COLS = {"avg_gain20d", "avg_gain50d", "Worst_20d", "Worst_50d"}


def _is_gain_col(col: str) -> bool:
    return col in _GAIN_COLS or "gain" in col or col.startswith(("chain_ret", "chain_cagr"))

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
_BOLD       = Font(bold=True)
_SMALL      = Font(size=9)
_HDR_FILL   = PatternFill("solid", fgColor="BDD7EE")   # blue header row
_SECT_FILL  = PatternFill("solid", fgColor="D6DCE4")   # grey section header
_GRN_FILL   = PatternFill("solid", fgColor="C6EFCE")   # green
_RED_FILL   = PatternFill("solid", fgColor="FFC7CE")   # red
_BEST_FILL  = PatternFill("solid", fgColor="FFE599")   # amber for "Best overall" row
_PARAM_FILL = PatternFill("solid", fgColor="FFFF99")   # yellow for simulation parameter headers
_PCT_FMT    = '+0.00;-0.00;"-"'
_CTR        = Alignment(horizontal="center")

_PARAM_COLS = {"focusset_size", "step", "No_go_GSPC_rsi", "p20d_win_min", "p50d_win_min",
               "q10_20_min", "q20_50_min"}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_all_runs() -> pd.DataFrame:
    """Read every aggregated_summary.xlsx under REPORT_ROOT and combine."""
    frames: list[pd.DataFrame] = []
    for folder in sorted(REPORT_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        agg = folder / "aggregated_summary.xlsx"
        if not agg.exists():
            print(f"  skip {folder.name}: no aggregated_summary.xlsx")
            continue
        try:
            df = pd.read_excel(agg, sheet_name="Aggregated Summary")
            frames.append(df)
            print(f"  loaded {folder.name}: {len(df)} run(s)")
        except Exception as exc:
            print(f"  skip {folder.name}: {exc}")
    if not frames:
        raise ValueError("No aggregated_summary.xlsx files found under " + str(REPORT_ROOT))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _sort_cols(df: pd.DataFrame, primary: str, tiebreaker: str) -> list[str]:
    return [c for c in [primary, tiebreaker] if c in df.columns]


def best_by(df: pd.DataFrame, primary: str, tiebreaker: str) -> pd.Series:
    """Best run across all strategies."""
    cols  = _sort_cols(df, primary, tiebreaker)
    valid = df.dropna(subset=cols[:1])
    if valid.empty:
        raise ValueError(f"No rows with a valid '{primary}' value")
    return valid.sort_values(cols, ascending=False).iloc[0]


def best_by_strategy(df: pd.DataFrame, primary: str, tiebreaker: str) -> list[tuple[str, pd.Series]]:
    """Best run per strategy, sorted by primary value descending."""
    if "StrategyName" not in df.columns:
        return []
    cols    = _sort_cols(df, primary, tiebreaker)
    results = []
    for strat_name, group in df.groupby("StrategyName", sort=False):
        valid = group.dropna(subset=cols[:1])
        if valid.empty:
            continue
        best = valid.sort_values(cols, ascending=False).iloc[0]
        results.append((str(strat_name), best))
    results.sort(
        key=lambda t: t[1].get(primary) if pd.notna(t[1].get(primary)) else float("-inf"),
        reverse=True,
    )
    return results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _cell_val(row: pd.Series, col: str):
    v = row.get(col)
    return None if pd.isna(v) else v


def _style_gain_cell(cell, val, col: str) -> None:
    cell.alignment = _CTR
    if _is_gain_col(col) and isinstance(val, (int, float)):
        cell.number_format = _PCT_FMT
        cell.fill = _GRN_FILL if val >= 0 else _RED_FILL


# ---------------------------------------------------------------------------
# Excel writer
# ---------------------------------------------------------------------------

def write_xlsx(sections: list[dict], data_cols: list[str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Best Strategy"

    n_data = len(data_cols)

    # One fixed header row at the top
    ws.cell(1, 1, "").fill = _HDR_FILL
    for j, col in enumerate(data_cols, start=2):
        c = ws.cell(1, j, col)
        c.font      = _BOLD
        c.fill      = _PARAM_FILL if col in _PARAM_COLS else _HDR_FILL
        c.alignment = _CTR

    cur_row = 2

    for section in sections:
        # ---- section header (criterion label) ----
        c = ws.cell(cur_row, 1, section["label"])
        c.font = Font(bold=True)
        for j in range(1, n_data + 2):
            ws.cell(cur_row, j).fill = _SECT_FILL
        cur_row += 1

        # ---- one row per strategy, sorted best→worst ----
        for strat_name, strat_row in section["per_strategy"]:
            c = ws.cell(cur_row, 1, strat_name)
            c.font = _SMALL
            for j, col in enumerate(data_cols, start=2):
                val  = _cell_val(strat_row, col)
                cell = ws.cell(cur_row, j, val)
                _style_gain_cell(cell, val, col)
            cur_row += 1

        # ---- overall best row ----
        c = ws.cell(cur_row, 1, "Best overall")
        c.font, c.fill = _BOLD, _BEST_FILL
        for j, col in enumerate(data_cols, start=2):
            val  = _cell_val(section["overall"], col)
            cell = ws.cell(cur_row, j, val)
            cell.fill = _BEST_FILL
            _style_gain_cell(cell, val, col)
            if _is_gain_col(col) and isinstance(val, (int, float)):
                cell.fill = _BEST_FILL   # amber overrides green/red on this row
        cur_row += 1

        # ---- blank separator ----
        cur_row += 1

    # Column widths
    ws.column_dimensions["A"].width = 22
    for j, col in enumerate(data_cols, start=2):
        ws.column_dimensions[get_column_letter(j)].width = max(len(str(col)) + 2, 12)
    ws.freeze_panes = "B2"

    wb.save(OUTPUT_XLSX)
    print(f"Written: {OUTPUT_XLSX}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading aggregated summaries...")
    df = load_all_runs()
    print(f"Total runs across all strategies: {len(df)}")
    print()

    all_cols = list(df.columns)
    ordered  = [c for c in _KEY_COLS if c in all_cols]
    ordered += [c for c in all_cols if c not in ordered]

    sections: list[dict] = []
    for label, primary, tiebreaker in CRITERIA:
        try:
            per_strategy = best_by_strategy(df, primary, tiebreaker)
            overall      = best_by(df, primary, tiebreaker)
            strat        = overall.get("StrategyName", "?")
            val          = overall.get(primary)
            print(f"{label}: best overall = {strat}  ({primary}={val:+.4f})")
            sections.append({"label": label, "per_strategy": per_strategy, "overall": overall})
        except (ValueError, TypeError) as exc:
            print(f"{label}: ERROR — {exc}")
    print()

    write_xlsx(sections, ordered)
    print("Done.")


if __name__ == "__main__":
    main()
