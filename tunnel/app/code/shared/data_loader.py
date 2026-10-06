"""Cached CSV loaders.

Adapted from potrank/strategy_grp2 shared/data_loader.py — same two rules:

1. **Paths are resolved per call, never at import.** `shared.config.active_*()` points at
   the frozen snapshot once preflight has built one (see shared/datacheck.py).

2. **A failed load is LOUD and NAMED** — DataUnavailable naming the file, the root it was
   looked for in, and the preflight command that explains why it is not there.

tunnel reads Longi/longi_price.csv, Cal.csv and Strategy/StrategicStocks_<daynum>.csv.
"""

import pandas as pd
from functools import lru_cache
from pathlib import Path

from shared import config
from shared.datacheck import DataUnavailable

# Every file successfully read this process, in load order.
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
def load_cal() -> pd.Series:
    """Cal.csv as a Series: int daynum -> Timestamp. (Source daynum is European float "2278,00".)"""
    cal = _read(config.active_cal(), "Cal.csv")
    return pd.Series(pd.to_datetime(cal["Date"]).to_numpy(),
                     index=cal["Daynum"].astype(float).astype(int))


@lru_cache(maxsize=None)
def load_strategic(rel: str) -> list[str]:
    """Unique tickers of a StrategicStocks_<daynum>.csv (one row per label x pick), in file order."""
    df = _read(config.active_root() / rel, rel)
    return list(dict.fromkeys(df["ticker"].dropna().astype(str)))


def reset_cache() -> None:
    """Drop every cached frame — called by config.use_data_root() when the root changes,
    so a snapshot can never be served frames read from the live repository."""
    load_longi.cache_clear()
    load_cal.cache_clear()
    load_strategic.cache_clear()
    _LOADED.clear()


def load_manifest_line() -> str:
    """One-line summary for the end of a run's log: what was read, from where."""
    return (f"[input] {len(_LOADED)} file(s) read from {config.active_root()}: "
            + ", ".join(_LOADED))
