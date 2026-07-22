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
