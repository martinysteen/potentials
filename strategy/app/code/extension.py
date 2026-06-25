"""
Extensions of the strategies in best_strategy.xlsx.

Extends EVERY strategy, best-first, into one workbook report/extension_all_<YYYYMMDD>.xlsx —
one sheet per strategy. So the recent "known future" of whichever strategy you actually follow
is always there, not just the day's top pick (which flips as the ranking moves).

  python extension.py        # also what run_sweep.py auto-calls

Each strategy is extended on ITS OWN best-run params, taken from best_strategy.select_best_runs()
(the same ranking best_strategy.py uses). The prior report/extension_*.xlsx is cleared only once
there is new output, so a run that extends nothing never wipes a good existing extension.

Standalone daily tool — reads the existing aggregated_summary.xlsx reports; no sweep is required
(the sweep is for development). run_sweep.py also calls run() after rebuilding best_strategy.xlsx.
"""

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


def run() -> Path | None:
    """Extend every strategy in best_strategy.xlsx (best-first) into one workbook
    report/extension_all_<date>.xlsx, one sheet each — each on its own best-run params.
    Returns the workbook path, or None when nothing could be extended."""
    columns, _all_cols, _floor, _cap, _period = best_strategy.select_best_runs(verbose=True)
    if not columns:
        print("No comparable runs — nothing to extend.")
        return None
    modules = discover_strategies()

    wb = Workbook()
    wb.remove(wb.active)            # drop the default empty sheet; add one per strategy
    n_written = 0
    for col in columns:
        name = col["strategy"]
        print(f"\n=== {name} ===")
        if _extend_one(modules, name, col["row"], wb):
            n_written += 1
    if n_written == 0:
        print("No strategy produced an extension (windows empty).")
        return None

    # Replace the prior extension(s) only now that we have output.
    for old in REPORT_ROOT.glob("extension_*.xlsx"):
        old.unlink()
        print(f"  removed older extension: {old.name}")

    dest = REPORT_ROOT / f"extension_all_{date.today().strftime('%Y%m%d')}.xlsx"
    wb.save(dest)
    print(f"\n** All-strategy extension ({n_written} sheet(s)) written: {dest} **")
    return dest


if __name__ == "__main__":
    run()
