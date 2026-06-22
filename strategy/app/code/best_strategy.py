"""
Compare strategies side by side — one column per strategy, metrics down the rows.

Each strategy's column is its best run by chain_cagr (phase-averaged and re-clamped
to the span every strategy shares), with chain_ret as tiebreaker. All runs must share
the same forward horizon (the `period` param); a mismatch is reported and aborts.

Output:
  app/report/best_strategy.xlsx  — transposed, strategies as columns, sorted by chain_cagr

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

from shared.chain import realizable_chain
from shared.config import REPORT_ROOT

# Decision metric is chain CAGR (phase-averaged, common-span); chain_ret breaks
# ties. Per-strategy columns are defined by _SUBCOLS near main().
OUTPUT_XLSX = REPORT_ROOT / "best_strategy.xlsx"

# Metric row order in the transposed table (these first, then any remaining cols).
_KEY_COLS = [
    "StrategyName", "Run#", "period",
    "chain_cagr", "chain_ret", "chain_n", "chain_floor", "chain_cap",
    "avg_gain", "Worst", "N_loss",
    "N_hops", "N_hops_active",
    "focusset_size", "step", "No_go_GSPC_rsi",
    "source_file",
]
_GAIN_COLS = {"avg_gain", "Worst"}


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

_PARAM_COLS = {"focusset_size", "step", "period", "No_go_GSPC_rsi",
               "p20d_win_min", "p50d_win_min", "q10_20_min", "q20_50_min"}


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
# Common-span chain reclamp
# ---------------------------------------------------------------------------
# chain_ret/cagr/n are written per run over that run's OWN span, so they are not
# comparable across strategies (a strategy that only covers recent daynums shows a
# bigger chain return than one spanning a longer, choppier history). Recompute them
# here over the span every compared strategy shares: [max(EndDaynum), min(StartDaynum)].

def _load_hopdata(strategy_name, source_file) -> list[tuple[int, float, float]] | None:
    """Read a run's HopData sheet -> [(daynum, gain, gspc_rsi_prev), ...]."""
    if not strategy_name or not source_file or pd.isna(source_file):
        return None
    path = REPORT_ROOT / str(strategy_name) / str(source_file)
    if not path.exists():
        return None
    try:
        hd = pd.read_excel(path, sheet_name="HopData")
    except Exception:
        return None
    out = []
    for _, r in hd.iterrows():
        out.append((
            int(r["daynum"]),
            float(r["gain"]) if pd.notna(r.get("gain")) else float("nan"),
            float(r["gspc_rsi_prev"]) if pd.notna(r.get("gspc_rsi_prev")) else float("nan"),
        ))
    return out


def reclamp_chains(df: pd.DataFrame) -> tuple[pd.DataFrame, int | None, int | None]:
    """Recompute chain_ret/cagr/n over the span shared by every compared run.

    Each run's hold horizon is its own `period`; the chain is phase-averaged.
    """
    needed = {"EndDaynum", "StartDaynum", "StrategyName", "source_file", "period"}
    if not needed.issubset(df.columns):
        print("  chain reclamp skipped: missing columns "
              f"{sorted(needed - set(df.columns))}")
        return df, None, None
    ends   = pd.to_numeric(df["EndDaynum"], errors="coerce").dropna()
    starts = pd.to_numeric(df["StartDaynum"], errors="coerce").dropna()
    if ends.empty or starts.empty:
        return df, None, None

    floor, cap = int(ends.max()), int(starts.min())
    df = df.copy()
    df["chain_floor"], df["chain_cap"] = floor, cap

    n_done = n_missing = 0
    for idx, row in df.iterrows():
        rows = _load_hopdata(row.get("StrategyName"), row.get("source_file"))
        if rows is None:
            n_missing += 1
            continue
        thr  = row.get("No_go_GSPC_rsi")
        thr  = None if pd.isna(thr) else float(thr)
        hold = int(row["period"])
        ret, cagr, ntr = realizable_chain(
            ((r[0], r[1], r[2]) for r in rows), hold, thr, floor, cap,
            phase_average=True)
        df.at[idx, "chain_ret"]  = round(ret, 4)  if pd.notna(ret)  else None
        df.at[idx, "chain_cagr"] = round(cagr, 4) if pd.notna(cagr) else None
        df.at[idx, "chain_n"]    = ntr
        n_done += 1

    print(f"  chain reclamped to common span [{floor}, {cap}] for {n_done} run(s)"
          + (f"; {n_missing} run(s) lacked HopData (kept original)" if n_missing else ""))
    return df, floor, cap


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _sort_cols(df: pd.DataFrame, primary: str, tiebreaker: str) -> list[str]:
    return [c for c in [primary, tiebreaker] if c in df.columns]


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

def best_run(group: pd.DataFrame, primary: str, tiebreaker: str) -> pd.Series | None:
    """That strategy's best run for one criterion (primary desc, tiebreaker desc)."""
    cols  = _sort_cols(group, primary, tiebreaker)
    if not cols:
        return None
    valid = group.dropna(subset=cols[:1])
    if valid.empty:
        return None
    return valid.sort_values(cols, ascending=False).iloc[0]


def write_xlsx(columns: list[dict], metric_rows: list[str]) -> None:
    """
    Transposed report: metrics down the rows, one column per strategy.

    columns: [{"strategy", "row"}], one per strategy (its best run by chain_cagr).
    metric_rows: metric names in display order (the table's row labels).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Best Strategy"

    # ---- header row: corner + one column per strategy ----
    corner = ws.cell(1, 1, "metric"); corner.font, corner.fill = _BOLD, _HDR_FILL
    for j, col in enumerate(columns, start=2):
        h = ws.cell(1, j, col["strategy"])
        h.font, h.fill, h.alignment = _BOLD, _SECT_FILL, _CTR

    # ---- one row per metric ----
    for i, metric in enumerate(metric_rows, start=2):
        lbl = ws.cell(i, 1, metric)
        lbl.font = _BOLD
        lbl.fill = _PARAM_FILL if metric in _PARAM_COLS else _HDR_FILL
        for j, col in enumerate(columns, start=2):
            val  = _cell_val(col["row"], metric) if col["row"] is not None else None
            cell = ws.cell(i, j, val)
            _style_gain_cell(cell, val, metric)
            if metric == "chain_cagr":          # the ranking criterion
                cell.font = _BOLD

    # ---- widths / freeze ----
    ws.column_dimensions["A"].width = 16
    for j in range(2, len(columns) + 2):
        ws.column_dimensions[get_column_letter(j)].width = 16
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
    df, _floor, _cap = reclamp_chains(df)
    print()

    if "StrategyName" not in df.columns:
        print("No StrategyName column — nothing to report.")
        return

    # Guard: every compared run must share the same forward horizon.
    if "period" in df.columns:
        periods = sorted(pd.to_numeric(df["period"], errors="coerce").dropna().unique())
        if len(periods) > 1:
            print(f"ERROR: mixed periods across runs {periods} — re-run the sweep at a "
                  "single period before comparing. Aborting.")
            return

    all_cols    = list(df.columns)
    metric_rows = [c for c in _KEY_COLS if c in all_cols]
    metric_rows += [c for c in all_cols if c not in metric_rows]

    groups = {str(name): g for name, g in df.groupby("StrategyName", sort=False)}

    def _rank(name: str) -> float:
        r = best_run(groups[name], "chain_cagr", "chain_ret")
        v = r.get("chain_cagr") if r is not None else None
        return float(v) if v is not None and pd.notna(v) else float("-inf")
    order = sorted(groups, key=_rank, reverse=True)   # strongest chain_cagr leftmost

    columns: list[dict] = []
    for name in order:
        row = best_run(groups[name], "chain_cagr", "chain_ret")
        columns.append({"strategy": name, "row": row})
        c = row.get("chain_cagr") if row is not None else None
        print(f"  {name:18} best chain_cagr={_fmt(c)}")
    print()

    write_xlsx(columns, metric_rows)
    print("Done.")


def _fmt(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{float(v):+.1f}"


if __name__ == "__main__":
    main()
