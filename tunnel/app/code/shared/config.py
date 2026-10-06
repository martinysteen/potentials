import sys
from pathlib import Path
from typing import Final

# Force UTF-8 stdout/stderr so the em-dashes and arrows in our log lines don't
# crash on a Windows cp1252 console. Copied from potrank/app/code/shared/config.py.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # already UTF-8, or a stream that can't be reconfigured

DATA_ROOT: Final = Path("/home/sm/potentials/repositoryRTBI/data")

APP_ROOT: Final = Path(__file__).resolve().parents[2]  # .../tunnel/app/
OUTPUT_ROOT: Final = APP_ROOT / "output"

# ---------------------------------------------------------------------------
# The ACTIVE data root — what data_loader actually opens
# ---------------------------------------------------------------------------
# DATA_ROOT above is the LIVE repository, which cron rewrites all day. A run normally
# reads a frozen, vintage-coherent SNAPSHOT of it instead — see shared/datacheck.py and
# preflight.py. Functions, not constants, so the root can be redirected after import
# (same rationale as potrank/strategy_grp2 shared/config.py).
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


def active_cal() -> Path:
    return _active / "Cal.csv"
