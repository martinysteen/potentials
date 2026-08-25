"""
Which input files potrank2.csv needs — and the one call every entry point makes before it
reads anything.

    python preflight.py             # print the input table for the live repository
    python preflight.py --manifest  # just list the required/optional files

Mechanics (present / non-empty / parseable / not mid-write / all one vintage, then freeze
into app/data/input/) live in shared/datacheck.py, copied verbatim from strategy_grp2 —
deliberately generic. This module holds the project-specific half.

Unlike strategy_grp2 (whose required-files list depends on which control-board rows are
active), potrank has no control board: every run builds the same 68 columns, so the
required list is STATIC — see columns.required_files(), the single source of truth also
used by potrank.py to build the file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import config, datacheck
from shared.datacheck import DataUnavailable          # re-exported for callers
import columns


def mode_from_argv(argv: list[str] | None = None) -> str:
    args = set(argv if argv is not None else sys.argv[1:])
    if "--live" in args:
        return "live"
    if "--stale-ok" in args:
        return "stale-ok"
    return "snapshot"


_ensured: Path | None = None


def ensure_data(mode: str | None = None, verbose: bool = True, force: bool = False) -> Path:
    """Preflight + freeze the inputs, and point shared.config at what the run should read.

    Call this FIRST in every entry point, before anything opens a CSV. Idempotent within a
    process (force=True re-checks anyway — not needed by potrank.py today, kept for parity
    with strategy_grp2's preflight.ensure_data and for ad-hoc use)."""
    global _ensured
    if _ensured is not None and not force:
        return _ensured
    required, optional = columns.required_files()
    _ensured = datacheck.ensure_data(required, optional,
                                     mode=mode or mode_from_argv(), verbose=verbose)
    return _ensured


def main() -> int:
    required, optional = columns.required_files()

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
