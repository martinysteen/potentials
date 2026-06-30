"""Strategy: P50 — longi_P50d_win >= threshold, then pick by lowest longi_rank."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, col_filter

STRATEGY_NAME = "P50"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 20,           # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": 40,
    "p50d_win_min": 0.9,
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

FILTERS = [
    col_filter("longi_P50d_win.csv", "p50d_win_min"),
]

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)


if __name__ == "__main__":
    main()
