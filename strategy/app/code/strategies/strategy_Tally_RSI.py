"""
Strategy: Tally_RSI — the 3-step Tally group build:
  1. top within-day bin of beta3m        (corner_bins bins; highest market sensitivity)
  2. bottom within-day bin of median_30d (lowest values = strongest momentum rank)
  3. keep the lowest vola_keep_frac of vola100d within the survivors (tail trim)
then pick the survivors with the HIGHEST RSI14 (chooser = buy the top; low-RSI
pullback picks measured as the worst rule tested — see report 6k).

Evidence for the build and the chooser grid: longi/expAdviceModel/
REPORT_winloss_experiments_2026-07-07.md (sections 6e-6l).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, corner_filter, trim_filter, rank_by

STRATEGY_NAME = "Tally_RSI"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 22,           # forward horizon in trading days; must be a key of
                            # shared.config.FUTURE_PERIOD_LABEL (1/5/22/66/132/264)
    "No_go_GSPC_rsi": 0,
    "corner_bins": 10,      # within-day bins for both corner indicators (10 = deciles)
    "vola_keep_frac": 0.5,  # fraction of the corner kept after the vola100d trim
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

FILTERS = [
    corner_filter("longi_beta3m.csv", "longi_median_30d.csv", "corner_bins"),
]

TRIMS = [
    trim_filter("longi_vola100d.csv", "vola_keep_frac", lowest=True),
]

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS,
                                      ranker=rank_by("longi_rsi.csv", ascending=False),
                                      trims=TRIMS)


if __name__ == "__main__":
    main()
