"""
Which input files this project's runs actually need — and the one call every entry point
makes before it reads anything.

    python preflight.py            # print the input table for the live repository, run nothing
    python preflight.py --manifest # just list the files a run requires

The mechanics (present / non-empty / parseable / not mid-write / all one vintage, then
freeze into app/data/input/) live in shared/datacheck.py, which is deliberately generic.
This module holds the project-specific half: assembling the file list from run_config,
sweep_config and the strategy modules, so adding a strategy or retargeting an attribute
never leaves the guard checking a stale list.

Why the list is a SUPERSET
--------------------------
It unions what every configured run *could* touch — every entry in
PRIORITY_ATTRIBUTE_DICTIONARY, every DOMINANCE_ATTRIBUTE_OVERRIDES entry, every
informational attribute, both horizons a strategy declares — rather than what one
particular entry point will touch. A superset can only ever make the guard stricter, and
the alternative (each entry point deriving its own list) is exactly the kind of drift that
lets a file go unchecked until it is missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import config, datacheck
from shared.datacheck import DataUnavailable          # re-exported for callers

import run_config as cfg

# Read by shared/engine.py and shared/report.py for every strategy, whatever it selects on:
# the No_go gate's RSI, the market benchmark, the ticker metadata and the daynum calendar.
_ALWAYS_REQUIRED: list[str] = [
    "PotDat.csv",
    "Stamdata.csv",
    "Cal.csv",
    "Longi/longi_rsi.csv",
]

# Loaded through a `try/except (FileNotFoundError, OSError)` that degrades to a blank row —
# checked and snapshotted when present, never a reason to stop.
_OPTIONAL: list[str] = [
    "Longi/longi_beta3m.csv",
]


def _longi(short_name: str) -> str:
    """Longi factor short name (e.g. "rank") -> repo-relative path."""
    return f"Longi/longi_{short_name}.csv"


def _csv_names(obj) -> list[str]:
    """Longi filenames a FILTERS/ranker object reads. Covers _Filter/_BinFilter/_Trim/_Ranker
    (`csv_name`) and _CornerFilter (`top_csv`/`bottom_csv`); a quotient_filter's synthetic
    "a/b" label is split back into its two real files."""
    names: list[str] = []
    for attr in ("csv_name", "top_csv", "bottom_csv"):
        value = getattr(obj, attr, None)
        if isinstance(value, str):
            names += [part for part in value.split("/") if part.endswith(".csv")]
    return names


def required_files() -> tuple[list[str], list[str]]:
    """(required, optional) repo-relative paths for everything a configured run may read."""
    required: set[str] = set(_ALWAYS_REQUIRED)

    # --- Step 1/2/3 attributes, from run_config (the resting values AND every candidate a
    # sweep can select, since sweep_config feeds PRIORITY_ATTRIBUTE_DICTIONARY in wholesale)
    required.add(_longi(cfg.DOMINANCE_ATTRIBUTE))
    for attribute, _direction in cfg.DOMINANCE_ATTRIBUTE_OVERRIDES.values():
        required.add(_longi(attribute))
    for attribute in cfg.PRIORITY_ATTRIBUTE_DICTIONARY:
        required.add(_longi(attribute))
    for attribute in cfg.INFORMATIONAL_ATTRIBUTES:
        required.add(_longi(attribute))

    # --- per-strategy: the forward-gain horizon(s) and any filter-chain sources ---
    for module in _strategy_modules():
        params = getattr(module, "PARAMS", {})
        required.add(f"Longi/future_gain{params.get('period', 20)}d.csv")
        for key in ("dominance_attribute", "priority_attribute"):
            if params.get(key):
                required.add(_longi(params[key]))
        for name in _informational(params):
            required.add(_longi(name))
        for item in list(getattr(module, "FILTERS", [])) + list(getattr(module, "TRIMS", [])):
            required |= {f"Longi/{n}" for n in _csv_names(item)}
        ranker = getattr(module, "ranker", None)
        if ranker is not None:
            required |= {f"Longi/{n}" for n in _csv_names(ranker)}

    # --- horizons sweep_config can select on top of a strategy's own default ---
    for period in _swept_periods():
        required.add(f"Longi/future_gain{period}d.csv")

    optional = [rel for rel in _OPTIONAL if rel not in required]
    return sorted(required), optional


def _strategy_modules() -> list:
    """Every strategy module, or [] if discovery fails — a broken import is run_sweep's
    error to report, not a reason for the guard itself to die."""
    try:
        from run_sweep import discover_strategies
        return list(discover_strategies().values())
    except Exception as exc:                      # noqa: BLE001
        print(f"[input] WARN could not discover strategies ({type(exc).__name__}: {exc}); "
              f"checking run_config attributes only")
        return []


def _informational(params: dict) -> list[str]:
    from shared.dominance import informational_attr_list
    return informational_attr_list(params.get("informational_attributes"))


def _swept_periods() -> list[int]:
    try:
        import sweep_config
        value = sweep_config.DEFAULTS.get("period", 20)
    except Exception:                             # noqa: BLE001
        return []
    return [int(v) for v in (value if isinstance(value, list) else [value])]


# ---------------------------------------------------------------------------
# The call every entry point makes
# ---------------------------------------------------------------------------

def mode_from_argv(argv: list[str] | None = None) -> str:
    """--live / --stale-ok off the command line; "snapshot" otherwise."""
    args = set(argv if argv is not None else sys.argv[1:])
    if "--live" in args:
        return "live"
    if "--stale-ok" in args:
        return "stale-ok"
    return "snapshot"


_ensured: Path | None = None


def ensure_data(mode: str | None = None, verbose: bool = True, force: bool = False) -> Path:
    """Preflight + freeze the inputs, and point shared.config at what the run should read.

    Call this FIRST in every entry point, before anything opens a CSV. Raises
    DataUnavailable (table already printed) when the repository is mid-update; see
    shared/datacheck.py for what "mid-update" means and why it is worth stopping for.

    **Idempotent within a process**, which is load-bearing rather than a convenience: a
    sweep runs one strategy's main() dozens of times, and re-snapshotting per run would
    both waste the copy and — far worse — let the vintage change halfway through a sweep,
    so the comparison sheet would rank runs scored on different data.
    """
    global _ensured
    if _ensured is not None and not force:
        return _ensured
    required, optional = required_files()
    _ensured = datacheck.ensure_data(required, optional,
                                     mode=mode or mode_from_argv(), verbose=verbose)
    return _ensured


def main() -> int:
    required, optional = required_files()
    if "--manifest" in sys.argv[1:]:
        print(f"Required ({len(required)}):")
        print("\n".join(f"  {rel}" for rel in required))
        print(f"Optional ({len(optional)}):")
        print("\n".join(f"  {rel}" for rel in optional))
        return 0

    stats = datacheck.inspect_all(config.DATA_ROOT, required, optional)
    verdict = datacheck.evaluate(stats, prior=datacheck.read_manifest(),
                                 source=config.DATA_ROOT)
    datacheck.print_table(verdict, config.DATA_ROOT)

    prior = datacheck.read_manifest()
    if prior:
        print(f"\nExisting snapshot: daynum {prior.get('daynum')}, "
              f"{prior.get('files')} files, built {prior.get('built')} "
              f"({datacheck.SNAPSHOT_ROOT})")
    else:
        print(f"\nNo snapshot yet ({datacheck.SNAPSHOT_ROOT})")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
