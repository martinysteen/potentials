import sys
from pathlib import Path
from typing import Final

# Force UTF-8 stdout/stderr so the em-dashes and arrows in our log lines don't
# crash on a Windows cp1252 console. Imported transitively by every entry point,
# so one place covers all.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # already UTF-8, or a stream that can't be reconfigured

DATA_ROOT: Final = Path("/home/sm/potentials/repositoryRTBI/data")
DATA_LONGI: Final = DATA_ROOT / "Longi"
POTDAT_PATH: Final = DATA_ROOT / "PotDat.csv"
STAMDATA_PATH: Final = DATA_ROOT / "Stamdata.csv"
CAL_PATH: Final = DATA_ROOT / "Cal.csv"

APP_ROOT: Final = Path(__file__).resolve().parents[2]  # .../strategy_grp2/app/
CONTROL_ROOT: Final = APP_ROOT / "control"
CONTROL_BOARD_PATH: Final = CONTROL_ROOT / "control_board.xlsx"
DERIVED_ROOT: Final = APP_ROOT / "data" / "derived"

# ---------------------------------------------------------------------------
# The ACTIVE data root — what data_loader actually opens
# ---------------------------------------------------------------------------
# DATA_ROOT above is the LIVE repository, which cron rewrites all day (rclone sync :07/:37,
# longi :15, conformity :30). A run normally reads a frozen, vintage-coherent SNAPSHOT of it
# instead — see shared/datacheck.py and preflight.py. `_active` is the root data_loader
# resolves its paths against; it starts as the live root, so any caller that never sets a
# snapshot behaves exactly as before.
#
# These are functions, not constants, on purpose: `from shared.config import DATA_LONGI`
# binds a value at import time and could never be redirected afterwards, which is precisely
# the bug that made this indirection necessary.
_active: Path = DATA_ROOT


def use_data_root(root: Path) -> None:
    """Point every subsequent load at `root`. Clears data_loader's caches, since anything
    already read came from the previous root."""
    global _active
    if root == _active:
        return
    _active = Path(root)
    from shared import data_loader          # deferred: data_loader imports this module
    data_loader.reset_cache()


def active_root() -> Path:
    return _active


def active_longi() -> Path:
    return _active / "Longi"


def active_potdat() -> Path:
    return _active / "PotDat.csv"


def active_stamdata() -> Path:
    return _active / "Stamdata.csv"


def active_cal() -> Path:
    return _active / "Cal.csv"


REPORT_ROOT: Final = APP_ROOT / "report"
SUMMARY_CSV: Final = REPORT_ROOT / "summary.csv"

# Step 2's production/display gross list (StrategicStocks.xlsx, Step1_groups/Step2_picks) is
# every currently-elevated group's FULL membership, filtered and priority-sorted, capped only
# here -- not by tickers_per_group or focusset_size, which are Step 3/4's backtest-sampling
# knobs and stay on the control board. Deliberately a code constant, not a board column (SM,
# 2026-08-03): a user should see the whole qualifying list, not a value they might tune per row.
PRODUCTION_GROSS_CAP: Final = 20


# Tickers read from PotDat.csv for market context in summary reports.
REFERENCE_TICKERS: Final[list[str]] = ["^GSPC", "^STOXX", "^HSI", "^VIX"]

# ---------------------------------------------------------------------------
# The forward-horizon files
# ---------------------------------------------------------------------------
# `period` stays an INT everywhere, deliberately. It is not just a filename infix: it is
# also the hold length in daynums that chain.py spaces lots by, that walkforward embargoes
# the training window by, and that sizes the extension's still-open window. Only the
# FILENAME is looked up here, so none of that arithmetic has to change.
#
# The "seven-pack": literal trading-day counts (1/5/10/20/50/100/200), so the label is
# always just f"{period}d". Entry is the day AFTER the signal day (see
# longi_future_performance.py), so a hop at daynum d buys at d+1.
FUTURE_PERIODS: Final[tuple[int, ...]] = (1, 5, 10, 20, 50, 100, 200)


def future_gain_file(period: int) -> str:
    """Longi filename holding the realized forward gain for a `period`-day hold.

    Raises on an unknown period rather than falling back to a default: a wrong horizon
    file does not crash anything downstream, it produces a complete and entirely
    plausible report measured against the wrong future.
    """
    period = int(period)
    if period not in FUTURE_PERIODS:
        raise ValueError(
            f"period={period} has no longi_future_per*.csv counterpart. "
            f"Valid periods: {list(FUTURE_PERIODS)}"
        )
    return f"longi_future_per{period}d.csv"


# longi_future_minaggr*.csv (the Step-3a stop-out "foresight eye") exists for only two of
# the seven-pack horizons -- see longi/app/code/longi_future_minaggr.py's PERIODS list.
MINAGGR_PERIODS: Final[tuple[int, ...]] = (20, 50)


def minaggr_file(period: int) -> str:
    """Longi filename holding the worst-drawdown-from-entry path for a `period`-day hold
    (<= 0, floored at 0). Raises on a period with no counterpart, same reasoning as
    future_gain_file: a silently-wrong file would produce a plausible but meaningless stop.
    """
    period = int(period)
    if period not in MINAGGR_PERIODS:
        raise ValueError(
            f"period={period} has no longi_future_minaggr*.csv counterpart. "
            f"Valid periods: {list(MINAGGR_PERIODS)}"
        )
    return f"longi_future_minaggr{period}d.csv"
