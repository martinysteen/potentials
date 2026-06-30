"""
Strategy: P20P50 — two-step selection:
  longi_P20d_win >= min  &  longi_P50d_win >= min
then pick the survivors with the lowest longi_rank. (P20P50cross1020/2050 without the
golden-cross step.)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, col_filter

STRATEGY_NAME = "P20P50"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 20,           # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": 0,
    "p20d_win_min": 0.8,
    "p50d_win_min": 0.8,
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

FILTERS = [
    col_filter("longi_P20d_win.csv", "p20d_win_min"),
    col_filter("longi_P50d_win.csv", "p50d_win_min"),
]

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)


if __name__ == "__main__":
    main()
