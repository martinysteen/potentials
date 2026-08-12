"""
Which input files this tick's active board rows actually need — and the one call every
entry point makes before it reads anything.

    python preflight.py             # print the input table for the live repository
    python preflight.py --manifest  # just list the files this tick's active rows require

Mechanics (present / non-empty / parseable / not mid-write / all one vintage, then freeze
into app/data/input/) live in shared/datacheck.py, copied verbatim from strategy_grp v1 —
deliberately generic. This module holds the project-specific half, but derives its file
list from the CONTROL BOARD's active rows rather than a fixed run_config/strategies set —
see control_board.py / step0_data.py.

Why the list is a SUPERSET over every active row (not per-row): a coherent snapshot must
serve the whole tick at once, and computing one per row would let the vintage drift
between rows scored in the same comparison. See strategy_grp's preflight.py for the
original write-up of this reasoning.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import config, datacheck
from shared.datacheck import DataUnavailable          # re-exported for callers
from shared import expression as expr
import control_board as cb
import step0_data as s0

_ALWAYS_REQUIRED: list[str] = [
    "PotDat.csv",
    "Stamdata.csv",
    "Cal.csv",
    "Longi/longi_rsi.csv",
]

_OPTIONAL: list[str] = [
    "Longi/longi_beta3m.csv",
]


def _longi(short_name: str) -> str:
    return f"Longi/longi_{short_name}.csv"


def required_files_for_rows(rows: list["cb.RunRow"],
                            settings: dict | None = None) -> tuple[list[str], list[str]]:
    """(required, optional) repo-relative paths for every ACTIVE, cleanly-parsing row.

    A row whose group_expression or attribute names don't even resolve is skipped here —
    raising it is step0_data's job when that row actually runs, not preflight's job to
    guard around. A row's own resolution errors surface from --dry-run / --check.

    `settings` (Settings sheet, e.g. `stop_sweep`) is needed too: whether Step3a_stopout's
    sweep runs — and therefore whether longi_future_minaggr<period>d.csv is required — is a
    board-level knob, not something a single row's own columns decide."""
    required: set[str] = set(_ALWAYS_REQUIRED)
    sweep_on = bool(str((settings or {}).get("stop_sweep", "")).strip())
    for row in rows:
        if not row.active or not row.ok:
            continue
        r = row.resolved
        try:
            gspec = expr.parse_group_expression(r["group_expression"])
            for role in ("dominance_attribute", "priority_attribute"):
                required.add(_longi(s0.resolve_group_specific(r[role], gspec.dimensions)))
            for name in r.get("informational_attributes", ()):
                required.add(_longi(s0.resolve_group_specific(name, gspec.dimensions)))
        except expr.ExpressionError:
            continue   # unresolvable row — its own error surfaces elsewhere, not here
        period = int(r["period"])
        required.add(f"Longi/{config.future_gain_file(period)}")
        if r.get("post_filter"):
            for t in expr.parse_post_filter(r["post_filter"]).terms:
                required.add(_longi(t.column))
        # Step 3a: a row's own stop_loss always needs the minaggr file; a row with no
        # stop_loss set still gets one when the board-wide sweep is on (outputboard runs
        # every active row through Step 3 now, not just ones already configured with a stop).
        wants_minaggr = r.get("stop_loss") or sweep_on
        if period in config.MINAGGR_PERIODS and wants_minaggr:
            required.add(f"Longi/{config.minaggr_file(period)}")

    optional = [rel for rel in _OPTIONAL if rel not in required]
    return sorted(required), optional


def mode_from_argv(argv: list[str] | None = None) -> str:
    args = set(argv if argv is not None else sys.argv[1:])
    if "--live" in args:
        return "live"
    if "--stale-ok" in args:
        return "stale-ok"
    return "snapshot"


_ensured: Path | None = None


def ensure_data(rows: list["cb.RunRow"] | None = None, settings: dict | None = None,
                mode: str | None = None, verbose: bool = True, force: bool = False) -> Path:
    """Preflight + freeze the inputs, and point shared.config at what the run should read.

    Call this FIRST in every entry point, before anything opens a CSV. Idempotent within a
    process (see strategy_grp v1's preflight.py for why that matters — a tick evaluates
    many rows and must score all of them on one coherent vintage)."""
    global _ensured
    if _ensured is not None and not force:
        return _ensured
    if rows is None or settings is None:
        board = cb.read_board()
        rows = rows if rows is not None else board.runs
        settings = settings if settings is not None else board.settings
    required, optional = required_files_for_rows(rows, settings)
    _ensured = datacheck.ensure_data(required, optional,
                                     mode=mode or mode_from_argv(), verbose=verbose)
    return _ensured


def main() -> int:
    board = cb.read_board()
    required, optional = required_files_for_rows(board.runs, board.settings)

    if "--manifest" in sys.argv[1:]:
        print(f"Required ({len(required)}):")
        print("\n".join(f"  {rel}" for rel in required))
        print(f"Optional ({len(optional)}):")
        print("\n".join(f"  {rel}" for rel in optional))
        return 0

    stats = datacheck.inspect_all(config.DATA_ROOT, required, optional)
    verdict = datacheck.evaluate(stats, prior=datacheck.read_manifest(), source=config.DATA_ROOT)
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
