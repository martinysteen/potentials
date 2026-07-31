"""
Strategy: Cross1020 — single-step selection:
  MA10/MA20 >= q10_20_min  (== 1 at the MA10/MA20 golden cross, > 1 once MA10 is above MA20)
then pick the survivors with the lowest longi_rank.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, quotient_filter

STRATEGY_NAME = "Cross1020"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 22,           # forward horizon in trading days; must be a key of
                            # shared.config.FUTURE_PERIOD_LABEL (1/5/22/66/132/264)
    "No_go_GSPC_rsi": 0,
    "q10_20_min": 1.03,
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

FILTERS = [
    quotient_filter("longi_ma10.csv", "longi_ma20.csv", "q10_20_min"),
]

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)


if __name__ == "__main__":
    main()
