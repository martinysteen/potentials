"""
Extension of the single best strategy.

Flow:
  1. best_strategy ranks every strategy by chain_annual (common-span, phase-averaged)
     exactly as best_strategy.py does — reusing its select_best_runs().
  2. The winner's name picks its report folder (report/<name>/); the extension is
     computed there, and only there, on that winner's best-run params.
  3. The produced extension_*.xlsx is moved up beside best_strategy.xlsx
     (report/), renamed to carry the strategy name: extension_<name>_<YYYYMMDD>.xlsx.

Standalone daily tool — reads the existing aggregated_summary.xlsx reports; no sweep
is required (the sweep is for development). run_sweep.py also calls run() after it
rebuilds best_strategy.xlsx.

Usage (from app/code/):
  python extension_of_best_strategy.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

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


def run() -> Path | None:
    """Pick the best strategy, extend it in its folder, move the result to report/."""
    columns, _all_cols, _floor, _cap, _period = best_strategy.select_best_runs(verbose=True)
    if not columns:
        print("No comparable runs — cannot pick a best strategy.")
        return None

    best = columns[0]                       # strongest chain_annual is leftmost
    name, row = best["strategy"], best["row"]
    annual = row.get("chain_annual") if row is not None else None
    print(f"\nBest strategy: {name}  (chain_annual={best_strategy._fmt(annual)})")

    # --- unambiguous-winner guards ------------------------------------------
    if annual is None or pd.isna(annual):
        print(f"ERROR: '{name}' has no valid chain_annual — no clear winner to extend.")
        return None
    if len(columns) > 1 and columns[1]["row"] is not None:
        runner = columns[1]
        annual2 = runner["row"].get("chain_annual")
        ret1   = row.get("chain_ret")
        ret2   = runner["row"].get("chain_ret")
        tie_annual = annual2 is not None and not pd.isna(annual2) and float(annual2) == float(annual)
        tie_ret  = (ret1 is not None and ret2 is not None
                    and not pd.isna(ret1) and not pd.isna(ret2)
                    and float(ret1) == float(ret2))
        if tie_annual and tie_ret:
            print(f"ERROR: ambiguous winner — '{name}' and '{runner['strategy']}' tie on "
                  f"both chain_annual ({best_strategy._fmt(annual)}) and chain_ret. "
                  "Resolve before extending.")
            return None
        if tie_annual:
            print(f"  NOTE: '{name}' ties '{runner['strategy']}' on chain_annual "
                  f"({best_strategy._fmt(annual)}); broken by chain_ret "
                  f"({ret1} vs {ret2}).")

    modules = discover_strategies()
    module = modules.get(name)
    if module is None:
        print(f"ERROR: winning strategy '{name}' not found among strategy modules.")
        return None
    if not hasattr(module, "build_extension"):
        print(f"ERROR: strategy '{name}' has no build_extension(); cannot extend it.")
        return None

    # Run the extension on the winner's best-run params (faithful to what won).
    params = _params_from_row(module, row)
    module.PARAMS.clear()
    module.PARAMS.update(params)
    print(f"Running extension with winning params: {params}\n")

    xlsx_path = module.build_extension()
    if not xlsx_path:
        print("Extension produced no file (empty window or no qualifying hops).")
        return None

    # Clear any prior extension beside best_strategy.xlsx — keep only the current one.
    for old in REPORT_ROOT.glob("extension_*.xlsx"):
        old.unlink()
        print(f"  removed older extension: {old.name}")

    # Move the new one up beside best_strategy.xlsx, tagging it with the strategy.
    src   = Path(xlsx_path)
    stamp = src.stem.replace("extension_", "")        # "YYYYMMDD"
    dest  = REPORT_ROOT / f"extension_{name}_{stamp}.xlsx"
    shutil.move(str(src), str(dest))
    print(f"** Best-strategy extension ({name}) moved to: {dest} **")
    return dest


if __name__ == "__main__":
    run()
