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
REPORT_ROOT: Final = APP_ROOT / "report"
SUMMARY_CSV: Final = REPORT_ROOT / "summary.csv"

# Tickers read from PotDat.csv for market context in summary reports.
# Verify exact names match PotDat.csv index before first run.
REFERENCE_TICKERS: Final[list[str]] = ["^GSPC", "^STOXX", "^HSI", "^VIX"]

# ---------------------------------------------------------------------------
# The forward-horizon files
# ---------------------------------------------------------------------------
# Kept byte-identical to ../../../strategy_grp/app/code/shared/config.py — see that
# project's CLAUDE.md on keeping the shared/ modules in sync.
#
# `period` stays an INT everywhere, deliberately. It is not just a filename infix: it is
# also the hold length in daynums that chain.py spaces lots by and that sizes the
# extension's still-open window. Only the FILENAME is looked up here, so none of that
# arithmetic has to change.
#
# Day counts mirror longi/app/code/longi_performance.py exactly — the forward family is the
# same ladder as the trailing longi_per* one. Entry is the day AFTER the signal day
# (see longi_future_performance.py), so a hop at daynum d buys at d+1.
FUTURE_PERIOD_LABEL: Final[dict[int, str]] = {
    1: "1d", 5: "1w", 22: "1m", 66: "3m", 132: "6m", 264: "1y",
}


def future_gain_file(period: int) -> str:
    """Longi filename holding the realized forward gain for a `period`-day hold.

    Raises on an unknown period rather than falling back to a default: a wrong horizon
    file does not crash anything downstream, it produces a complete and entirely
    plausible report measured against the wrong future.
    """
    try:
        return f"longi_future_per{FUTURE_PERIOD_LABEL[int(period)]}.csv"
    except KeyError:
        raise ValueError(
            f"period={period} has no longi_future_per*.csv counterpart. "
            f"Valid periods: {sorted(FUTURE_PERIOD_LABEL)}"
        ) from None
