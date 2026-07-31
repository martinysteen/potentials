"""
Strategy: Cross2050 — single-step selection:
  MA20/MA50 >= q20_50_min  (== 1 at the MA20/MA50 golden cross, > 1 once MA20 is above MA50)
then pick the survivors with the lowest longi_rank.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, quotient_filter

STRATEGY_NAME = "Cross2050"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 22,           # forward horizon in trading days; must be a key of
                            # shared.config.FUTURE_PERIOD_LABEL (1/5/22/66/132/264)
    "No_go_GSPC_rsi": 0,
    "q20_50_min": 1.05,
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

FILTERS = [
    quotient_filter("longi_ma20.csv", "longi_ma50.csv", "q20_50_min"),
]

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)


if __name__ == "__main__":
    main()
