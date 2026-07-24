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
FROM_RANK: int = 1                   # which end of the (already directionally-graded)
                                      # info_attribute pool to draw the focusset from:
                                      # 1=best n, -1=worst n. See shared/select.py.

# The dominance step: a GICS sector is elevated to "dominating" status on a daynum when
# at least DOM_COUNT_THRESHOLD of its (up to ~250) tickers beat RANK_THRESHOLD on
# DOMINANCE_ATTRIBUTE. Fixed at "rank": RANK_THRESHOLD=100 is only a meaningful cutoff
# for a rank-like attribute (1..N, N in the hundreds) — a raw value threshold doesn't
# transfer to another attribute's scale (e.g. rsi tops out at 100, beta3m rarely exceeds
# 5), so DOMINANCE_ATTRIBUTE is not swept. If another attribute were ever used here, a
# percentile-based cutoff would be needed instead of a fixed value — not implemented.
RANK_THRESHOLD: float = 100          # DOMINANCE_ATTRIBUTE cutoff a ticker must beat to count
DOM_COUNT_THRESHOLD: int = 10        # qualifying tickers a GICS needs to be "dominating"
PERSISTENCE_FRAC: float = 2 / 3      # trailing-window fraction of dominating days required
TICKERS_PER_GICS: int = 3            # best tickers (by INFO_ATTRIBUTE) drawn per dominating GICS
DOMINANCE_ATTRIBUTE: str = "rank"    # decides which GICS counts as "dominating" — fixed,
                                      # never swept (see note above).
DOMINANCE_ASCENDING: bool = True     # True = smaller value wins (rank always is); we always
                                      # elevate to dominance by being BELOW rank_threshold.

# The grading step: within an already-dominating GICS, INFO_ATTRIBUTE picks/ranks the
# actual focusset tickers — no threshold, direction only (see INFO_ATTRIBUTE_DIRECTIONS).
# May be a single Longi factor short name or a list of several; only the FIRST name
# drives actual ticker selection, any further names are informational only — shown as
# extra min/max rows in run*.xlsx and the extension tabs, no effect on which tickers get
# picked. A bare string is still accepted (treated as a one-element list).
INFO_ATTRIBUTE: list[str] = ["per1d", "macd_histogram"]

# Every Longi factor short name usable as the PRIMARY (first) INFO_ATTRIBUTE, mapped to
# its grading direction: True = smaller value wins ("low"), False = bigger value wins
# ("high"). Single source of truth so a mismatch can't be hand-paired wrong — selecting
# with a primary name absent from this dict is a hard error. Add an entry here before
# using a new name as the primary INFO_ATTRIBUTE.
INFO_ATTRIBUTE_DIRECTIONS: dict[str, bool] = {
    "per1d": False,   # high
}
