"""
Which input files tunnel needs — and the one call every entry point makes before it
reads anything.

    python preflight.py             # print the input table for the live repository
    python preflight.py --manifest  # just list the required/optional files

Mechanics (present / non-empty / parseable / not mid-write / all one vintage, then freeze
into app/data/input/) live in shared/datacheck.py, copied verbatim from potrank. This
module holds the project-specific half: a static two-file list.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import config, datacheck
from shared.datacheck import DataUnavailable          # re-exported for callers

PRICES_FILE = "longi_price.csv"
RANK_FILE = "longi_rank.csv"          # --universe top: rank 1 = best (see longi_rank.py)
REQUIRED: list[str] = [f"Longi/{PRICES_FILE}", "Cal.csv"]
OPTIONAL: list[str] = []


def strategic_file(root: Path | None = None) -> str | None:
    """Newest Strategy/StrategicStocks_<daynum>.csv (strategy_grp2 --production output),
    relative to the data root — the default ticker universe for tunnel runs."""
    found = sorted((root or config.DATA_ROOT).glob("Strategy/StrategicStocks_*.csv"),
                   key=lambda f: int(f.stem.rsplit("_", 1)[1]) if f.stem.rsplit("_", 1)[1].isdigit() else -1)
    return f"Strategy/{found[-1].name}" if found else None


def required_files(universe: str = "strategic") -> list[str]:
    if universe == "all":
        return list(REQUIRED)
    if universe == "top":
        return REQUIRED + [f"Longi/{RANK_FILE}"]
    ss = strategic_file()
    if ss is None:
        raise DataUnavailable(f"No Strategy/StrategicStocks_*.csv under {config.DATA_ROOT}")
    return REQUIRED + [ss]


def mode_from_argv(argv: list[str] | None = None) -> str:
    args = set(argv if argv is not None else sys.argv[1:])
    if "--live" in args:
        return "live"
    if "--stale-ok" in args:
        return "stale-ok"
    return "snapshot"


_ensured: Path | None = None


def ensure_data(universe: str = "strategic", mode: str | None = None,
                verbose: bool = True, force: bool = False) -> Path:
    """Preflight + freeze the inputs, and point shared.config at what the run should read.
    Call this FIRST in every entry point, before anything opens a CSV. Idempotent."""
    global _ensured
    if _ensured is not None and not force:
        return _ensured
    _ensured = datacheck.ensure_data(required_files(universe), OPTIONAL,
                                     mode=mode or mode_from_argv(), verbose=verbose)
    return _ensured


def main() -> int:
    required = required_files("all" if "--all" in sys.argv[1:] else "strategic")
    if "--manifest" in sys.argv[1:]:
        print(f"Required ({len(required)}):")
        print("\n".join(f"  {rel}" for rel in required))
        print(f"Optional ({len(OPTIONAL)}):")
        print("\n".join(f"  {rel}" for rel in OPTIONAL))
        return 0

    stats = datacheck.inspect_all(config.DATA_ROOT, required, OPTIONAL)
    verdict = datacheck.evaluate(stats, prior=datacheck.read_manifest(), source=config.DATA_ROOT)
    datacheck.print_table(verdict, config.DATA_ROOT)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
