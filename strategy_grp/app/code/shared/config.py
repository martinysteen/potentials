import sys
from pathlib import Path
from typing import Final

# Force UTF-8 stdout/stderr so the em-dashes and arrows in our log lines don't
# crash on a Windows cp1252 console. Imported transitively by every entry point
# (strategies, run_sweep, aggregate_summary, best_strategy), so one place covers all.
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

APP_ROOT: Final = Path(__file__).resolve().parents[2]  # .../strategy/app/

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

# Tickers read from PotDat.csv for market context in summary reports.
# Verify exact names match PotDat.csv index before first run.
REFERENCE_TICKERS: Final[list[str]] = ["^GSPC", "^STOXX", "^HSI", "^VIX"]
