"""
Strategy: Tally_Rank — the 3-step Tally group build:
  1. top within-day bin of beta3m        (corner_bins bins; highest market sensitivity)
  2. bottom within-day bin of median_30d (lowest values = strongest momentum rank)
  3. keep the lowest vola_keep_frac of vola100d within the survivors (tail trim)
then pick the survivors with the lowest longi_rank (chooser = RankNow).

Evidence for the build and the chooser grid: longi/expAdviceModel/
REPORT_winloss_experiments_2026-07-07.md (sections 6e-6l).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.engine import make_strategy, corner_filter, trim_filter

STRATEGY_NAME = "Tally_Rank"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 20,           # forward horizon in trading days (20 or 50)
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

main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS, trims=TRIMS)


if __name__ == "__main__":
    main()
