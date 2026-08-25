"""Cached CSV loaders.

Adapted from strategy_grp2/app/code/shared/data_loader.py — same two rules, both learned
the hard way there:

1. **Paths are resolved per call, never at import.** `shared.config.active_*()` points at
   the frozen snapshot once preflight has built one (see shared/datacheck.py). Binding a
   path at import time would make that redirection impossible.

2. **A failed load is LOUD and NAMED.** These files live in a repository that cron rewrites
   all day; a missing one used to surface as a bare pandas traceback thrown deep inside a
   strategy. Now every failure raises DataUnavailable naming the file, the root it was
   looked for in, and the preflight command that explains why it is not there.

potrank has no PotDat.csv or Cal.csv dependency (no forward-horizon lookups, no date
display), so those loaders are dropped here; `load_yfinance()` is new.
"""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from shared import config
from shared.datacheck import DataUnavailable

# Every file successfully read this process, in load order — printed by
# `load_manifest_line()` so a run's log states which vintage it actually ran on.
_LOADED: list[str] = []


def _read(path: Path, label: str, **kwargs) -> pd.DataFrame:
    """Read one European-format CSV, or fail with a message that says what to do."""
    try:
        df = pd.read_csv(path, sep=";", decimal=",", **kwargs)
    except FileNotFoundError:
        raise DataUnavailable(
            f"{label}: not found at {path}\n"
            f"  The input repository is rewritten on a cron all day and files are deleted "
            f"before their replacements land.\n"
            f"  Run `python preflight.py` for the full input table, or re-run in a few minutes."
        ) from None
    except Exception as exc:
        raise DataUnavailable(
            f"{label}: unreadable at {path} ({type(exc).__name__}: {exc})\n"
            f"  Most likely a partially written file. Run `python preflight.py`."
        ) from None
    _LOADED.append(label)
    return df


@lru_cache(maxsize=None)
def load_longi(filename: str) -> pd.DataFrame:
    """Load a Longi matrix CSV. Rows=tickers, cols=daynum strings, newest-left."""
    return _read(config.active_longi() / filename, f"Longi/{filename}", index_col=0)


@lru_cache(maxsize=None)
def load_stamdata() -> pd.DataFrame:
    """Load Stamdata.csv as strings. Rows=tickers, cols=attributes (Name, GICS, Sector2, ...).

    dtype=str deliberately: potrank passes PE/Yield/FKplus/etc. straight through to the
    output CSV in their existing European text form, with no float round-trip. The ticker
    column is NOT set as the index here — its header is a timestamp, not a label; callers
    address it by position (see potrank.py's ticker-universe step)."""
    return _read(config.active_stamdata(), "Stamdata.csv", dtype=str)


@lru_cache(maxsize=None)
def load_yfinance() -> pd.DataFrame:
    """Load Yfinance/Yfinance.csv. Already one row per ticker (see makeYfinanceSnapshot.py's
    groupby(Symbol).idxmax(Daynum)), ^-prefixed tickers already excluded upstream — no
    dedupe needed here. Its ticker column is genuinely named `Ticker`, so index_col=0 gives
    a real index, unlike Stamdata's timestamp-headed first column."""
    return _read(config.active_yfinance(), "Yfinance/Yfinance.csv", index_col=0)


def reset_cache() -> None:
    """Drop every cached frame — called by config.use_data_root() when the root changes,
    so a snapshot can never be served frames read from the live repository."""
    load_longi.cache_clear()
    load_stamdata.cache_clear()
    load_yfinance.cache_clear()
    _LOADED.clear()


def loaded_files() -> list[str]:
    """Files actually read so far, in load order (deduplicated by the lru_caches)."""
    return list(_LOADED)


def load_manifest_line() -> str:
    """One-line summary for the end of a run's log: what was read, from where."""
    return (f"[input] {len(_LOADED)} file(s) read from {config.active_root()}: "
            + ", ".join(_LOADED))
