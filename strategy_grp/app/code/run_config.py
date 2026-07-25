"""
Tunables for the GICS-domination strategy family (DomGICS_now/_20d/_50d) — the single
place to see and change every default each strategy_DomGICS_*.py copies into its own
PARAMS. sweep_config.py is a separate, deliberately independent surface: it decides
*what runs* (which strategies, which grid of overrides for a sweep), not these defaults.

Three-step pipeline, three distinct attribute roles — do not conflate them (this has
happened before and broken the sweep; see shared/dominance.py for the pipeline itself):
  Step 1 — GICS elevation ("dominance"):  DOMINANCE_ATTRIBUTE / DOMINANCE_ATTRIBUTE_DIRECTION /
                                           DOMINANCE_THRESHOLD / DOM_COUNT_THRESHOLD
  Step 2 — test-set construction:         PRIORITY_ATTRIBUTE / PRIORITY_ATTRIBUTE_DICTIONARY /
                                           TICKERS_PER_GICS
  Step 3 — informational only (display):  INFORMATIONAL_ATTRIBUTES — never affects
                                           selection, test-sets, or anything else.
"""

# The "classic" backtest knobs, common to every strategy in this project.
FOCUSSET_SIZE: int = 5             # tickers picked per hop
STEP: int = 5                        # daynum step between hops
NO_GO_GSPC_RSI: int = 0             # suppress picks / chain hops when GSPC RSI < this
FROM_RANK: int = 1                   # which end of the (already directionally-graded)
                                      # priority_attribute pool to draw the focusset from:
                                      # 1=best n, -1=worst n. See shared/select.py.

# ---------------------------------------------------------------------------
# Step 1 — GICS elevation ("dominance"): a GICS sector is elevated to "dominating"
# status on a daynum when at least DOM_COUNT_THRESHOLD of its (up to ~250) tickers beat
# DOMINANCE_THRESHOLD on DOMINANCE_ATTRIBUTE (direction-aware: below the threshold when
# DOMINANCE_ATTRIBUTE_DIRECTION is True, above it otherwise). DOMINANCE_THRESHOLD=100 is
# only a meaningful cutoff for a rank-like attribute (1..N, N in the hundreds) — a raw
# value threshold doesn't transfer to another attribute's scale (e.g. rsi tops out at
# 100, beta3m rarely exceeds 5) — a percentile-based cutoff would be needed to make this
# scale-free (not implemented) — so DOMINANCE_ATTRIBUTE is a single fixed value, never
# swept (contrast with Step 2's PRIORITY_ATTRIBUTE_DICTIONARY below).
# ---------------------------------------------------------------------------
DOMINANCE_ATTRIBUTE: str = "rank"            # Longi factor short name (longi_<name>.csv)
                                              # deciding which GICS counts as "dominating".
DOMINANCE_ATTRIBUTE_DIRECTION: bool = True   # True = smaller value wins (e.g. rank),
                                              # False = bigger value wins. Get this wrong
                                              # and the "dominating" selection silently
                                              # inverts (picks the weakest GICS instead of
                                              # the strongest) — no way to detect the
                                              # mismatch from the data alone.
DOMINANCE_THRESHOLD: float = 100             # DOMINANCE_ATTRIBUTE cutoff a ticker must
                                              # beat to qualify (see scale note above).
DOM_COUNT_THRESHOLD: int = 10                # qualifying tickers a GICS needs to count as
                                              # "dominating" — Step 1 only; distinct from
                                              # Step 2's TICKERS_PER_GICS below.
PERSISTENCE_FRAC: float = 2 / 3              # trailing-window fraction of dominating days
                                              # required for dom_20d/dom_50d persistence.

# ---------------------------------------------------------------------------
# Step 2 — test-set construction: within each dominating GICS, PRIORITY_ATTRIBUTE ranks
# candidates (direction-aware) and TICKERS_PER_GICS caps how many of the top-ranked ones
# are drawn into the pool; the pooled candidates across all dominating GICS are then
# re-ranked globally by the same attribute and focusset_size/from_rank applied. Unlike
# Step 1, it is genuinely unclear which attribute makes the best selection criterion, so
# PRIORITY_ATTRIBUTE_DICTIONARY lists every candidate worth testing — sweep_config.py
# sweeps across all of them, one independent test-set (run) per entry, deriving each
# run's direction from this dict so a name can never be paired with the wrong direction.
# ---------------------------------------------------------------------------
PRIORITY_ATTRIBUTE_DICTIONARY: dict[str, bool] = {
    "beta3m":         False,
    "iran":           False,
    "macd_histogram": False,
    "median_30d":     True,
    "PdivMA20":       False,
    "per1m":          False,
    "quot1020":       False,
    "quot2050":       False,
    "rsi":            False,
    "sh3m":           False,
    "spr100d":        True,
    "trump":          False,
    "vola20d":        False,
}
# Resting (non-swept) default: the first entry above, derived (never hand-duplicated) so
# it can't drift out of sync with the dictionary it comes from.
PRIORITY_ATTRIBUTE: str = next(iter(PRIORITY_ATTRIBUTE_DICTIONARY))
PRIORITY_ATTRIBUTE_DIRECTION: bool = PRIORITY_ATTRIBUTE_DICTIONARY[PRIORITY_ATTRIBUTE]

TICKERS_PER_GICS: int = 3   # top candidates (by PRIORITY_ATTRIBUTE) drawn from EACH
                            # dominating GICS into the pooled test-set — Step 2 only;
                            # distinct from Step 1's DOM_COUNT_THRESHOLD above.

# ---------------------------------------------------------------------------
# Step 3 — informational only: shown alongside the picks (min/max per day in run*.xlsx
# and the extension tabs) purely for insight into what's going on along the timeline.
# Never affects which tickers get selected, how test-sets are built, or anything else.
# May be a single Longi factor short name or a list of several.
# ---------------------------------------------------------------------------
INFORMATIONAL_ATTRIBUTES: list[str] = ["per1d", "macd_histogram"]
