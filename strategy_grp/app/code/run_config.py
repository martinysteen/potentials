"""
Tunables for the GICS-domination strategy family (DomGICS_now/_20d/_50d) — the single
place to see and change every default each strategy_DomGICS_*.py copies into its own
PARAMS. sweep_config.py is a separate, deliberately independent surface: it decides
*what runs* (which strategies, which grid of overrides for a sweep), not these defaults.
"""

# The "classic" backtest knobs, common to every strategy in this project.
FOCUSSET_SIZE: int = 5             # tickers picked per hop
STEP: int = 5                        # daynum step between hops
NO_GO_GSPC_RSI: int = 0             # suppress picks / chain hops when GSPC RSI < this
FROM_RANK: int = 1                   # which end of the info_attribute ranking to draw
                                      # from: 1=best n, -1=worst n. See shared/select.py.

RANK_THRESHOLD: float = 100          # PRIORITY_ATTRIBUTE cutoff a ticker must beat to count
DOM_COUNT_THRESHOLD: int = 10        # qualifying tickers a GICS needs to be "dominating"
PERSISTENCE_FRAC: float = 2 / 3      # trailing-window fraction of dominating days required
TICKERS_PER_GICS: int = 3            # best tickers (by INFO_ATTRIBUTE) drawn per dominating GICS

# Longi factor names (the "longi_<name>.csv" part — no prefix/suffix) driving the two
# distinct roles in the pipeline. Swap in another Longi CSV's short name to retarget
# either role without touching shared/dominance.py.
PRIORITY_ATTRIBUTE: str = "rank"     # decides which GICS counts as "dominating" (rank_threshold)
INFO_ATTRIBUTE: str = "per1d"        # picks tickers within & across dominating GICS — purely a
                                      # selection signal (always "bigger wins"), not itself
                                      # configurable for direction the way priority is.

# PRIORITY_ATTRIBUTE's value orientation: True = smaller value wins (e.g. rank), False =
# bigger value wins. Get this wrong and the "dominating" selection silently inverts
# (picks the weakest GICS instead of the strongest) — there is no way to detect the
# mismatch from the data alone. INFO_ATTRIBUTE has no equivalent flag: unlike dominance,
# which strategy still needs it to be RIGHT, ticker selection is a soft comparative pick
# where "bigger wins" is the fixed, always-correct convention for the informational
# factors in use (e.g. per1d) — a direction toggle would go unused.
PRIORITY_ASCENDING: bool = True      # rank_threshold cutoff: signal < threshold qualifies
