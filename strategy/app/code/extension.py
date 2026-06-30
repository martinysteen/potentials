"""
Builds the single combined report workbook report/best_strategy_<YYYYMMDD>.xlsx:

  Sheet 1     : the cross-strategy comparison (from best_strategy.fill_best_sheet)
  Sheets 2…N  : one extension sheet per strategy, best-first — the recent "known future"
                (partial realised gain) of each strategy's picks.

So the comparison and the extension of whichever strategy you actually follow live in one
file, not two. Each strategy is extended on ITS OWN best-run params, taken from
best_strategy.select_best_runs() (the same ranking the comparison uses).

  python extension.py        # builds the combined file; also what run_sweep.py auto-calls
  python best_strategy.py    # delegates here — same combined file

The prior workbook is moved to report/_archive/ only once there is new output, so a run never
wipes a good existing report. Standalone daily tool — reads the existing aggregated_summary.xlsx
reports; no sweep is required (the sweep is for development).
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from openpyxl import Workbook

import best_strategy
from run_sweep import discover_strategies
from shared.config import REPORT_ROOT

# Params a run row may carry that a strategy consumes; others keep module defaults.
# Integer-valued keys are rounded to int; the rest are taken as floats.
_INT_PARAMS   = {"focusset_size", "step", "period", "No_go_GSPC_rsi", "from_rank"}
_FLOAT_PARAMS = {"p20d_win_min", "p50d_win_min", "q10_20_min", "q20_50_min"}


def _params_from_row(module, row: pd.Series) -> dict:
    """Overlay the winning run's recorded params onto the module's default PARAMS."""
    params = dict(module.PARAMS)
    for key in _INT_PARAMS | _FLOAT_PARAMS:
        if key in row.index and pd.notna(row[key]):
            params[key] = (int(round(float(row[key]))) if key in _INT_PARAMS
                           else float(row[key]))
    return params


def _extend_one(modules: dict, name: str, row, workbook) -> bool:
    """Bind a strategy's winning-run params onto its module and add its extension sheet to
    `workbook`. Returns True if a sheet was written, False when the strategy is unknown, has no
    build_extension(), or produced nothing (empty window / no qualifying hops)."""
    module = modules.get(name)
    if module is None:
        print(f"  skip '{name}': not among strategy modules.")
        return False
    if not hasattr(module, "build_extension"):
        print(f"  skip '{name}': no build_extension().")
        return False
    params = _params_from_row(module, row)
    module.PARAMS.clear()
    module.PARAMS.update(params)
    return bool(module.build_extension(workbook=workbook))


def _archive_prior_outputs() -> None:
    """Move any prior report workbook into report/_archive/ before today's is written.

    Only the auto-generated outputs are archived: the dated combined file
    best_strategy_<8 digits>.xlsx, plus the now-legacy undated best_strategy.xlsx and
    extension_all_*.xlsx. User-named keepsakes (e.g. best_strategy_top.xlsx) are matched by
    neither pattern and left untouched. Moving is reversible; an archived file of the same
    name is overwritten (os.replace is atomic on one volume)."""
    archive = REPORT_ROOT / "_archive"
    dated = [p for p in REPORT_ROOT.glob("best_strategy_*.xlsx")
             if re.fullmatch(r"best_strategy_\d{8}", p.stem)]
    priors = (sorted(dated)
              + sorted(REPORT_ROOT.glob("best_strategy.xlsx"))
              + sorted(REPORT_ROOT.glob("extension_all_*.xlsx")))
    if not priors:
        return
    archive.mkdir(parents=True, exist_ok=True)
    for p in priors:
        os.replace(str(p), str(archive / p.name))   # overwrites a same-named archived copy
        print(f"  archived prior output: {p.name} -> _archive/")


def run() -> Path | None:
    """Build the single combined workbook report/best_strategy_<date>.xlsx:
    sheet 1 = the cross-strategy comparison, then one extension sheet per strategy
    (best-first), each on its own best-run params. The prior workbook is moved to
    report/_archive/ first. Returns the workbook path, or None when there is nothing
    comparable to report."""
    columns, all_cols, floor, cap, period = best_strategy.select_best_runs(verbose=True)
    if not columns:
        print("No comparable runs — nothing to report.")
        return None
    modules = discover_strategies()

    # Sheet 1: the comparison (created as the active sheet so it stays first; the
    # per-strategy extension sheets below are appended after it).
    wb = Workbook()
    chained_rows = best_strategy.chained_rows_for(all_cols)
    best_strategy.fill_best_sheet(wb.active, columns, chained_rows, floor, cap, period)

    n_ext = 0
    for col in columns:
        name = col["strategy"]
        print(f"\n=== {name} ===")
        if _extend_one(modules, name, col["row"], wb):
            n_ext += 1
    if n_ext == 0:
        print("No strategy produced an extension window (data fully up to date); "
              "writing the comparison sheet only.")

    # Replace the prior workbook only now that we have output to write.
    _archive_prior_outputs()
    dest = REPORT_ROOT / f"best_strategy_{date.today().strftime('%Y%m%d')}.xlsx"
    wb.save(dest)
    print(f"\n** Combined report (comparison + {n_ext} extension sheet(s)) written: {dest} **")
    return dest


if __name__ == "__main__":
    run()
