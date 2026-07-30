"""Cached CSV loaders.

Two rules here, both learned the hard way:

1. **Paths are resolved per call, never at import.** `shared.config.active_*()` points at
   the frozen snapshot once preflight has built one (see shared/datacheck.py). Binding
   `DATA_LONGI` at import time — as this module used to — made that redirection impossible.

2. **A failed load is LOUD and NAMED.** These files live in a repository that cron rewrites
   all day; a missing one used to surface as a bare pandas traceback thrown six frames deep
   inside a strategy, which run_sweep then swallowed into a single scrolling line. Now every
   failure raises DataUnavailable naming the file, the root it was looked for in, and the
   preflight command that explains why it is not there.
"""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from shared import config
from shared.datacheck import DataUnavailable

# Every file successfully read this process, in load order — printed by
# `load_manifest_line()` so a run's log states which vintage it actually ran on.
_LOADED: list[str] = []


def _read(path: Path, label: str) -> pd.DataFrame:
    """Read one European-format matrix CSV, or fail with a message that says what to do."""
    try:
        df = pd.read_csv(path, sep=";", decimal=",", index_col=0)
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
    return _read(config.active_longi() / filename, f"Longi/{filename}")


@lru_cache(maxsize=None)
def load_potdat() -> pd.DataFrame:
    """Load PotDat.csv. Rows=tickers, cols=daynum strings, newest-left."""
    return _read(config.active_potdat(), "PotDat.csv")


@lru_cache(maxsize=None)
def load_stamdata() -> pd.DataFrame:
    """Load Stamdata.csv. Rows=tickers, cols=attributes (Name, Sector, GICS, Sector2, Zone, ...)."""
    return _read(config.active_stamdata(), "Stamdata.csv")


@lru_cache(maxsize=None)
def _load_cal() -> pd.DataFrame:
    # Index is Daynum as float (European decimal in source: "2055,00" → 2055.0)
    return _read(config.active_cal(), "Cal.csv")


def daynum_to_date(daynum: int) -> str:
    """Convert a daynum integer to a date string via Cal.csv."""
    try:
        cal = _load_cal()
        key = float(daynum)
        if key in cal.index:
            return str(cal.loc[key].iloc[0])
    except Exception:
        pass
    return f"dn{daynum}"


def reset_cache() -> None:
    """Drop every cached frame — called by config.use_data_root() when the root changes,
    so a snapshot can never be served frames read from the live repository."""
    load_longi.cache_clear()
    load_potdat.cache_clear()
    load_stamdata.cache_clear()
    _load_cal.cache_clear()
    _LOADED.clear()


def loaded_files() -> list[str]:
    """Files actually read so far, in load order (deduplicated by the lru_caches)."""
    return list(_LOADED)


def load_manifest_line() -> str:
    """One-line summary for the end of a run's log: what was read, from where."""
    return (f"[input] {len(_LOADED)} file(s) read from {config.active_root()}: "
            + ", ".join(_LOADED))
