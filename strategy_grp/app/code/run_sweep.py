"""
Run a curated parameter sweep across strategies, then aggregate and compare.

Edit sweep_config.py to decide what runs. Then, from app/code/:

    python run_sweep.py            # archive old runs of the swept strategies,
                                   # rebuild them fresh, aggregate, compare
    python run_sweep.py --dry-run  # show the run plan; touch nothing
    python run_sweep.py --list     # list available strategy names and exit

What it does, in order
----------------------
1. Discover every strategy module and map its STRATEGY_NAME -> module.
2. Expand sweep_config into concrete parameter-sets (grids -> cartesian product).
3. For each swept strategy: move existing run*.xlsx + aggregated_summary.xlsx
   into <strategy>/_archive/<timestamp>/  (reversible), and drop that
   strategy's rows from the master summary.csv.
4. Run each parameter-set by overriding the module's PARAMS in place and calling
   its main(); run numbering restarts at 1 because the folder was cleared.
5. Re-aggregate the swept strategies and rebuild the combined best_strategy_<date>.xlsx
   (comparison + per-strategy extensions; still compares against strategies you did not touch).

Strategies not listed in sweep_config.STRATEGIES are never modified.
"""

import importlib
import pkgutil
import shutil
import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import csv

import strategies as strategies_pkg
import aggregate_summary
from shared.config import REPORT_ROOT, SUMMARY_CSV

import run_config
import sweep_config


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_strategies() -> dict[str, object]:
    """Import every strategies/strategy_*.py and map STRATEGY_NAME -> module."""
    found: dict[str, object] = {}
    for info in pkgutil.iter_modules(strategies_pkg.__path__):
        if not info.name.startswith("strategy_"):
            continue
        mod = importlib.import_module(f"strategies.{info.name}")
        name = getattr(mod, "STRATEGY_NAME", None)
        if name and hasattr(mod, "PARAMS") and hasattr(mod, "main"):
            found[name] = mod
    return found


# ---------------------------------------------------------------------------
# Sweep expansion
# ---------------------------------------------------------------------------

def expand_runs(base_params: dict, spec: dict, linked: dict) -> list[dict]:
    """
    Build the list of concrete parameter-sets for one strategy.

    base_params : the strategy's own PARAMS (defines which keys are valid)
    spec        : DEFAULTS overlaid with the strategy's own sweep entry
    linked      : alias -> [target keys]; one alias value is written to every
                  target the strategy actually has (keeps coupled params equal).

    List-valued params (and list-valued aliases) become grid axes; all axes are
    cartesian-producted. Keys the strategy doesn't define are ignored.

    priority_attribute (the Step-2 test-set-construction attribute — see run_config.py)
    is special-cased: sweeping it derives priority_attribute_direction from
    run_config.PRIORITY_ATTRIBUTE_DICTIONARY for each value, rather than letting it be
    swept as an independent axis — a plain cartesian product could pair an attribute
    with the wrong direction, and that mismatch is silent (see run_config.py). Setting
    priority_attribute_direction directly in spec while priority_attribute is also swept
    is a hard error, as is sweeping a name absent from that dictionary.
    """
    spec = dict(spec)
    axes: list[list[dict]] = []   # each axis is a list of partial-assignment fragments
    consumed: set[str] = set()    # base keys governed by an active alias

    # priority_attribute/priority_attribute_direction: derive the direction, never sweep
    # it independently — see run_config.PRIORITY_ATTRIBUTE_DICTIONARY.
    if "priority_attribute" in spec and "priority_attribute" in base_params:
        values = spec.pop("priority_attribute")
        if not isinstance(values, list):
            values = [values]
        if "priority_attribute_direction" in spec:
            raise SystemExit(
                "sweep_config: priority_attribute_direction must not be set while "
                "priority_attribute is being swept — its direction is derived from "
                "run_config.PRIORITY_ATTRIBUTE_DICTIONARY for each swept name."
            )
        missing = [v for v in values if v not in run_config.PRIORITY_ATTRIBUTE_DICTIONARY]
        if missing:
            raise SystemExit(
                f"sweep_config: priority_attribute value(s) {missing} have no entry in "
                "run_config.PRIORITY_ATTRIBUTE_DICTIONARY — add their direction "
                "(True = smaller wins, False = bigger wins) before sweeping them."
            )
        frags = [{"priority_attribute": v}
                 | ({"priority_attribute_direction": run_config.PRIORITY_ATTRIBUTE_DICTIONARY[v]}
                    if "priority_attribute_direction" in base_params else {})
                 for v in values]
        axes.append(frags)

    # Linked aliases first — each writes one value to all present target keys.
    for alias, targets in linked.items():
        if alias not in spec:
            continue
        present = [t for t in targets if t in base_params]
        if not present:
            continue
        values = spec.pop(alias)
        if not isinstance(values, list):
            values = [values]
        axes.append([{t: v for t in present} for v in values])
        consumed.update(present)

    # Remaining direct keys the strategy understands.
    for key, values in spec.items():
        if key not in base_params or key in consumed:
            continue
        if not isinstance(values, list):
            values = [values]
        axes.append([{key: v} for v in values])

    if not axes:
        return [dict(base_params)]

    out: list[dict] = []
    for selection in product(*axes):
        params = dict(base_params)
        for frag in selection:
            params.update(frag)
        if params not in out:                     # de-dupe identical combinations
            out.append(params)
    return out


def build_plan(modules: dict[str, object]) -> dict[str, list[dict]]:
    """Resolve sweep_config into {strategy_name: [param-set, ...]}."""
    defaults = sweep_config.DEFAULTS
    linked   = getattr(sweep_config, "LINKED", {})
    plan: dict[str, list[dict]] = {}
    unknown = [n for n in sweep_config.STRATEGIES if n not in modules]
    if unknown:
        raise SystemExit(
            "Unknown strategy name(s) in sweep_config.STRATEGIES: "
            + ", ".join(unknown)
            + "\nRun `python run_sweep.py --list` to see valid names."
        )
    non_sweepable = getattr(sweep_config, "NON_SWEEPABLE", set())
    for name, overrides in sweep_config.STRATEGIES.items():
        spec = {**defaults, **overrides}
        bad = non_sweepable & spec.keys()
        if bad:
            raise SystemExit(
                f"{name}: {sorted(bad)} must not be swept — expand_runs() would misread a "
                "fixed multi-value list as a grid axis and split it into separate runs. "
                "Remove from sweep_config.DEFAULTS/STRATEGIES; set via run_config.py instead."
            )
        plan[name] = expand_runs(dict(modules[name].PARAMS), spec, linked)
    return plan


# ---------------------------------------------------------------------------
# Clean rebuild helpers
# ---------------------------------------------------------------------------

def archive_strategy(name: str, stamp: str) -> int:
    """Move existing run*.xlsx and aggregated_summary.xlsx into _archive/<stamp>/."""
    folder = REPORT_ROOT / name
    if not folder.exists():
        return 0
    olds = list(folder.glob("run*.xlsx")) + list(folder.glob("aggregated_summary.xlsx"))
    if not olds:
        return 0
    dest = folder / "_archive" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for p in olds:
        shutil.move(str(p), str(dest / p.name))
    return len(olds)


def clean_summary_rows(names: set[str]) -> int:
    """Remove rows of the given strategies from the master summary.csv. Keeps header."""
    if not SUMMARY_CSV.exists():
        return 0
    with SUMMARY_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter=";"))
    if len(rows) <= 1:
        return 0
    header, data = rows[0], rows[1:]
    kept = [r for r in data if not (r and r[0] in names)]
    removed = len(data) - len(kept)
    if removed:
        with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(header)
            w.writerows(kept)
    return removed


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_strategy(module: object, runs: list[dict]) -> int:
    """Execute every parameter-set for one strategy. Returns number of successful runs."""
    ok = 0
    for i, params in enumerate(runs, start=1):
        print(f"\n  >>> run {i}/{len(runs)}  {module.STRATEGY_NAME}  {params}")
        module.PARAMS.clear()
        module.PARAMS.update(params)
        try:
            module.main()
            ok += 1
        except SystemExit as exc:                 # strategies sys.exit(1) on zero hops
            print(f"      (no output: strategy exited — {exc})")
        except Exception as exc:                  # keep the sweep alive on one bad config
            print(f"      (ERROR: {type(exc).__name__}: {exc})")
    return ok


def print_plan(plan: dict[str, list[dict]]) -> None:
    total = 0
    for name, runs in plan.items():
        print(f"  {name}: {len(runs)} run(s)")
        for params in runs:
            print(f"      {params}")
        total += len(runs)
    print(f"\n  Total: {total} run(s) across {len(plan)} strategy(ies)")


def main() -> None:
    args = set(sys.argv[1:])
    modules = discover_strategies()

    if "--list" in args:
        print("Available strategies (use these as keys in sweep_config.STRATEGIES):")
        for name in sorted(modules):
            print(f"  {name}")
        return

    plan = build_plan(modules)
    swept = set(plan)

    print("Sweep plan:")
    print_plan(plan)

    if "--dry-run" in args:
        print("\n--dry-run: no files touched.")
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    print(f"\nArchiving existing runs to _archive/{stamp}/ ...")
    for name in plan:
        moved = archive_strategy(name, stamp)
        print(f"  {name}: archived {moved} file(s)")
    removed = clean_summary_rows(swept)
    print(f"  summary.csv: removed {removed} stale row(s)")

    print("\nRunning sweep ...")
    for name, runs in plan.items():
        done = run_strategy(modules[name], runs)
        print(f"\n  {name}: {done}/{len(runs)} run(s) produced output")

    print("\nAggregating swept strategies ...")
    for name in plan:
        aggregate_summary.aggregate_strategy(name)

    print("\nBuilding combined best_strategy_<date>.xlsx (comparison + per-strategy extensions) ...")
    import extension                           # local import avoids an import cycle
    extension.run()

    print("\nSweep complete.")


if __name__ == "__main__":
    main()
