"""
Tunables for the group-domination strategy families (DomGICS_now/_20d/_50d and
DomSector2_now/_20d/_50d) — the single place to see and change every default each
strategy_Dom*.py copies into its own PARAMS. sweep_config.py is a separate, deliberately
independent surface: it decides *what runs* (which strategies, which grid of overrides for
a sweep), not these defaults.

Three-step pipeline, three distinct attribute roles — do not conflate them (this has
happened before and broken the sweep; see shared/dominance.py for the pipeline itself):
  Step 1 — group elevation ("dominance"): DOMINANCE_ATTRIBUTE / DOMINANCE_ATTRIBUTE_DIRECTION /
                                           DOMINANCE_THRESHOLD_DECILE / DOM_COUNT_THRESHOLD
  Step 2 — test-set construction:         PRIORITY_ATTRIBUTE / PRIORITY_ATTRIBUTE_DICTIONARY /
                                           TICKERS_PER_GROUP
  Step 3 — informational only (display):  INFORMATIONAL_ATTRIBUTES — never affects
                                           selection, test-sets, or anything else.

GROUP_COLUMN is a FOURTH role, and deliberately NOT called an "attribute"
---------------------------------------------------------------------------
The three roles above are all Longi factor short names (longi_<name>.csv). `group_column`
is something else entirely: the name of a **Stamdata.csv column** whose values the tickers
are grouped BY before Step 1 counts anything ("GICS" or "Sector2"). Calling it an
"attribute" would put four different things under one word in a project where exactly that
confusion has already broken a sweep. It is never swept — one group criterion per strategy
family, fixed in the strategy module (see sweep_config.NON_SWEEPABLE).
"""

# Stamdata.csv columns a strategy family may group by. Sector2 is a genuine sub-partition
# of GICS (48 of its 50 values sit inside exactly one GICS), so it acts as a *sharpening*
# of which groups get promoted through dominance, not as a rival taxonomy. Cardinality:
# GICS 13 values (~93 tickers each), Sector2 50 (~24 each).
GROUP_COLUMNS: tuple[str, ...] = ("GICS", "Sector2")

# The "classic" backtest knobs, common to every strategy in this project.
FOCUSSET_SIZE: int = 5             # tickers picked per hop
STEP: int = 5                        # daynum step between hops
NO_GO_GSPC_RSI: int = 0             # suppress picks / chain hops when GSPC RSI < this
FROM_RANK: int = 1                   # which end of the (already directionally-graded)
                                      # priority_attribute pool to draw the focusset from:
                                      # 1=best n, -1=worst n. See shared/select.py.
MIN_CHAIN_LOTS: int = 4              # lots a run's chain must realize before it may
                                      # REPRESENT its strategy in best_strategy.xlsx.
                                      # A reporting rule, not a sweep decision: nothing is
                                      # skipped or refused, every run still produces its
                                      # run*.xlsx and its aggregated_summary.xlsx row. It
                                      # exists because chain_annual divides an additive sum
                                      # by the chain's OWN span (shared/chain.py::_additive),
                                      # so a config sparse enough to realize one lucky lot
                                      # annualizes it over ~one holding window and posts a
                                      # headline in the hundreds — which then wins
                                      # best_strategy.py's ranking and displaces a healthy
                                      # 20-lot run from the comparison. Seen for real: a
                                      # dominance_threshold_decile=0.05 / tickers_per_group=2
                                      # run scored 445 on a single lot. Note chain_inv% does
                                      # NOT catch this — it is measured over the ACTIVE
                                      # window, so two adjacent lots read as 100%.

# ---------------------------------------------------------------------------
# Step 1 — group elevation ("dominance"): a group (a value of group_column) is elevated to
# "dominating" status on a daynum when at least dom_count_threshold of its tickers beat
# THAT DAY's own best-decile cutoff of DOMINANCE_ATTRIBUTE (direction-aware: below the
# cutoff when DOMINANCE_ATTRIBUTE_DIRECTION is True, above it otherwise). DOMINANCE_THRESHOLD_DECILE
# is a FRACTION (0.10 = best decile), not a raw value — shared.dominance._daily_decile_cutoff
# computes the value at that quantile of DOMINANCE_ATTRIBUTE's cross-sectional distribution
# on that one daynum (every ticker, that day only — independently per day, not across
# history), so the cutoff is scale-free and the same fraction means "best 10%" whichever
# attribute is chosen (rank 1..~1200, rsi 0..100, beta3m usually <5, ...), on every
# individual day. DOMINANCE_ATTRIBUTE is still a single fixed value, never swept by
# sweep_config.py (contrast with Step 2's PRIORITY_ATTRIBUTE_DICTIONARY below) — not
# because of a scale mismatch anymore, but because each candidate is meant to be tried as
# its own independent run, one at a time.
# ---------------------------------------------------------------------------
DOMINANCE_ATTRIBUTE: str = "rsi"            # Longi factor short name (longi_<name>.csv)
                                              # deciding which group counts as "dominating".
DOMINANCE_ATTRIBUTE_DIRECTION: bool = False   # True = smaller value wins (e.g. rank),
                                              # False = bigger value wins. 
DOMINANCE_THRESHOLD_DECILE: float = 0.10     # Best-decile fraction of DOMINANCE_ATTRIBUTE's
                                              # that day's distribution a ticker must be within
                                              # to qualify (see scale note above).
PERSISTENCE_FRAC: float = 2 / 3              # trailing-window fraction of dominating days
                                              # required for dom_20d/dom_50d persistence.

# Qualifying tickers a group needs to count as "dominating" — Step 1 only; distinct from
# Step 2's TICKERS_PER_GROUP below. **Per group criterion, because an absolute count is not
# transferable between them.** The market-wide best decile is ~120 of ~1200 tickers, so "10
# qualifying" asks a 93-member GICS for 11% of itself but a 24-member Sector2 for 42% of
# itself — at 10 the Sector2 family would have produced almost nothing but cash hops.
# Sector2's value is derived as half of GICS's rather than written out, so the two cannot
# drift apart when the GICS value is retuned.
_DOM_COUNT_THRESHOLD_GICS: int = 10
DOM_COUNT_THRESHOLD: dict[str, int] = {
    "GICS":    _DOM_COUNT_THRESHOLD_GICS,
    "Sector2": _DOM_COUNT_THRESHOLD_GICS // 2,   # half — Sector2 sectors are ~1/4 the size
}


def dom_count_threshold_for(group_column: str) -> int:
    """Step-1 qualifying-ticker count for one group criterion. KeyError (not a default) on
    an unknown column: silently falling back to the GICS count is the kind of wrong-but-
    plausible run this project's input guard exists to prevent."""
    return DOM_COUNT_THRESHOLD[group_column]


# Per-strategy override: the strategies of a family normally all share DOMINANCE_ATTRIBUTE /
# DOMINANCE_ATTRIBUTE_DIRECTION above. An entry here, keyed by STRATEGY_NAME, overrides
# just that one strategy's pair — e.g. running DomGICS_now on a different dominance
# attribute than the persistence tiers (DomGICS_20d/_50d) without touching the shared
# default. Direction still must match the overriding attribute (same silent-inversion
# risk as the global pair above).
DOMINANCE_ATTRIBUTE_OVERRIDES: dict[str, tuple[str, bool]] = {
    #"DomGICS_now": ("rsi", False),   # chain_annual 119->184, Worst -52->-32 vs rank
                                      # (both improve at once) — see CLAUDE.md commit history.
    # DomSector2_now may well want ("rsi", False) too — its GICS twin did — but that is a
    # measurement, not an assumption: leave it out until the run says so.
}


def dominance_attribute_for(strategy_name: str) -> tuple[str, bool]:
    """(dominance_attribute, dominance_attribute_direction) for one strategy: the
    DOMINANCE_ATTRIBUTE_OVERRIDES entry if present, else the shared DOMINANCE_ATTRIBUTE /
    DOMINANCE_ATTRIBUTE_DIRECTION default."""
    return DOMINANCE_ATTRIBUTE_OVERRIDES.get(
        strategy_name, (DOMINANCE_ATTRIBUTE, DOMINANCE_ATTRIBUTE_DIRECTION))

# ---------------------------------------------------------------------------
# Step 2 — test-set construction: within each dominating group, PRIORITY_ATTRIBUTE ranks
# candidates (direction-aware) and TICKERS_PER_GROUP caps how many of the top-ranked ones
# are drawn into the pool; the pooled candidates across all dominating groups are then
# re-ranked globally by the same attribute and focusset_size/from_rank applied. Unlike
# Step 1, it is genuinely unclear which attribute makes the best selection criterion, so
# PRIORITY_ATTRIBUTE_DICTIONARY lists every candidate worth testing — sweep_config.py
# sweeps across all of them, one independent test-set (run) per entry, deriving each
# run's direction from this dict so a name can never be paired with the wrong direction.
#
# NOTE on the conformity factors: longi_conf_GICS / longi_conf_Sector2 are group-specific.
# A name listed here is swept for EVERY strategy, so "conf_GICS" would have the Sector2
# family ranking its candidates on GICS conformity — silent cross-wiring, and nothing in
# the output would look wrong. If a conformity factor is ever tested as a priority
# attribute, test one family at a time via a STRATEGIES override in sweep_config.py.
#
# Sorthand:  True = small is best= small wins
# ---------------------------------------------------------------------------
PRIORITY_ATTRIBUTE_DICTIONARY: dict[str, bool] = {
    #"beta3m":         False,
    #"conf_GICS":      False,    # group-specific — read the NOTE above before enabling
    #"conf_Sector2":   False,    # Når False (dvs høj er bedst), er der stort set kun US-aktier
    #"macd_histogram": False,
    #"median_10d":     True,
    #"median_20d":     True,
    #"median_30d":     True,
    #"median_40d":     True,
    #"median_100d":    True,
    #"PdivMA20":       False,
    #"PdivMA50":       False,
    #"per1d" :         False,
    #"per1w" :         False,
    #"per1m":          False,
    #"quot1020":       False,
    #"quot2050":       False,
    "rank":           False,       #rank=True (små-er-bedst) giver avg_gain=5% & worst=-36%
    #"rsi":            False,
    #"sh3m":           False,
    #"spr100d":        False, 
    #"spr250d":        False,     #False bedst
    #"vola20d":        False,
    #"vola100d":        False,     #True dur ikke
}
# Resting (non-swept) default: the first entry above, derived (never hand-duplicated) so
# it can't drift out of sync with the dictionary it comes from.
PRIORITY_ATTRIBUTE: str = next(iter(PRIORITY_ATTRIBUTE_DICTIONARY))
PRIORITY_ATTRIBUTE_DIRECTION: bool = PRIORITY_ATTRIBUTE_DICTIONARY[PRIORITY_ATTRIBUTE]

TICKERS_PER_GROUP: int = 3  # top candidates (by PRIORITY_ATTRIBUTE) drawn from EACH
                            # dominating group into the pooled test-set — Step 2 only;
                            # distinct from Step 1's DOM_COUNT_THRESHOLD above. Shared by
                            # both group criteria: 2 was tried for Sector2 (where 3 of a
                            # small sector is most of it) and left too many good
                            # opportunities behind.

# ---------------------------------------------------------------------------
# Step 3 — informational only: shown alongside the picks (mean/median per day in run*.xlsx
# and the extension tabs) purely for insight into what's going on along the timeline.
# Never affects which tickers get selected, how test-sets are built, or anything else.
# Keyed by group_column so each family displays ITS OWN conformity factor rather than the
# other one's. Each value may be a single Longi factor short name or a list of several.
# ---------------------------------------------------------------------------
INFORMATIONAL_ATTRIBUTES: dict[str, list[str]] = {
    "GICS":    ["rank", "rsi", "spr100d"],
    "Sector2": ["rank", "rsi", "spr100d"],
}


def informational_attributes_for(group_column: str) -> list[str]:
    """Step-3 display-only factor names for one group criterion. A copy, since it lands in
    a strategy's live PARAMS dict that run_sweep mutates in place."""
    return list(INFORMATIONAL_ATTRIBUTES[group_column])


# ---------------------------------------------------------------------------
# The PARAMS dict every strategy_Dom*.py copies
# ---------------------------------------------------------------------------

def dom_params(strategy_name: str, group_column: str, period: int = 20) -> dict:
    """The full PARAMS dict for one Dom* strategy.

    Six strategies share one 15-key parameter list; writing it out per module is how a
    rename ends up half-applied (it has happened here before). This is the one copy.

    Returns a FRESH dict on every call — run_sweep.run_strategy mutates module.PARAMS in
    place (PARAMS.clear() + update()), so two modules must never share one object.
    """
    dominance_attribute, dominance_attribute_direction = dominance_attribute_for(strategy_name)
    return {
        "focusset_size": FOCUSSET_SIZE,
        "step": STEP,
        "period": period,           # forward horizon in trading days (20 or 50)
        "No_go_GSPC_rsi": NO_GO_GSPC_RSI,
        "from_rank": FROM_RANK,
        "group_column": group_column,          # Stamdata column to group by — see the
                                                # "fourth role" note in this module's docstring
        "dominance_threshold_decile": DOMINANCE_THRESHOLD_DECILE,
        "dom_count_threshold": dom_count_threshold_for(group_column),
        "persistence_frac": PERSISTENCE_FRAC,
        "tickers_per_group": TICKERS_PER_GROUP,
        "dominance_attribute": dominance_attribute,
        "dominance_attribute_direction": dominance_attribute_direction,
        "priority_attribute": PRIORITY_ATTRIBUTE,
        "priority_attribute_direction": PRIORITY_ATTRIBUTE_DIRECTION,
        "informational_attributes": informational_attributes_for(group_column),
    }
