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

# ---------------------------------------------------------------------------
# Group-specific Longi factors — bound to the family's own criterion, automatically
# ---------------------------------------------------------------------------
# Some Longi factors are not one matrix but a TWINNED FAMILY, one per group criterion:
# longi_conf_GICS.csv / longi_conf_Sector2.csv, longi_sectorbeta_GICS.csv /
# longi_sectorbeta_Sector2.csv. Feeding the GICS twin to a Sector2 strategy — in ANY of the
# three attribute roles — is silent cross-wiring: every file loads, every number is a real
# number, and nothing in the output looks wrong. It cannot be caught downstream and it cannot
# be caught by eye, so it is not left to discipline.
#
# The rule is USE THE TWIN, not refuse:
#   * Write the STEM ("conf", "sectorbeta") wherever an attribute name is expected and each
#     family reads its own twin — conf_GICS for the GICS strategies, conf_Sector2 for the
#     Sector2 ones. This is the intended spelling: one entry, both families, correct by
#     construction, both testable in a single sweep.
#   * Write one twin explicitly ("conf_GICS") and the other family is RETARGETED to its own
#     ("conf_Sector2"), never run on the foreign one. Every twin exists, so this always works
#     and no strategy is dropped from the comparison for it.
#   * Either way the RESOLVED name is what lands in the strategy's PARAMS, so it is recorded
#     as used — the Summary sheet of run*.xlsx, summary.csv, aggregated_summary.xlsx and the
#     comparison sheet of best_strategy.xlsx all show it per strategy, so a GICS column reading
#     conf_GICS sits beside a Sector2 column reading conf_Sector2 and the difference is on the
#     page. It is printed in the run header too. A report never names a factor the run did not read.
#   * Aborting is reserved for a twin that is genuinely BLOCKED — an unknown group criterion
#     (here) or a twin missing from the data (shared/dominance.py's availability check, which
#     fails only the strategies that needed it and leaves the rest of the sweep to finish).
#
# preflight guards whatever a configured run resolves to; see preflight.required_files().
# Add a stem here when the Longi side publishes a new per-criterion family.
GROUP_SPECIFIC_FACTORS: tuple[str, ...] = ("conf", "sectorbeta")


def split_group_specific(attribute: str) -> tuple[str, str] | None:
    """(stem, group_column) for a group-specific factor name, else None.

        "conf"         -> ("conf", "")      bare stem: no criterion named, take the family's own
        "conf_GICS"    -> ("conf", "GICS")  one twin, named explicitly
        "rank"         -> None              an ordinary factor: one matrix, same for every family

    Classifies only. The second element is "" for a bare stem and may name a criterion that
    does not exist — rejecting that is resolve_attribute's job.
    """
    for stem in GROUP_SPECIFIC_FACTORS:
        if attribute == stem:
            return stem, ""
        if attribute.startswith(f"{stem}_"):
            return stem, attribute[len(stem) + 1:]
    return None


def resolve_attribute(attribute: str, group_column: str, role: str = "attribute") -> str:
    """The Longi factor short name a strategy grouping by `group_column` must actually read.

    Ordinary factors pass through untouched. A group-specific one (see GROUP_SPECIFIC_FACTORS)
    is bound to `group_column`'s own twin, whether it arrived as a bare stem or as the other
    family's twin. `role` names the caller, for the error message only.

    Raises ValueError when there is no twin to bind to — a criterion outside GROUP_COLUMNS.
    Falling back to the written name (or to GICS) would produce a complete, plausible, wrong
    run, which is the one outcome this project treats as worse than stopping.
    """
    if not attribute:
        return attribute
    split = split_group_specific(attribute)
    if split is None:
        return attribute
    stem, written = split
    if group_column not in GROUP_COLUMNS:
        raise ValueError(
            f"{role}='{attribute}' is a group-specific factor (longi_{stem}_<criterion>.csv), "
            f"but group_column='{group_column}' is not one of {list(GROUP_COLUMNS)} — there is "
            f"no twin to bind it to.")
    if written and written not in GROUP_COLUMNS:
        raise ValueError(
            f"{role}='{attribute}' names group criterion '{written}', which is not one of "
            f"{list(GROUP_COLUMNS)}. Write the bare stem '{stem}' to get each family's own "
            f"twin automatically.")
    return f"{stem}_{group_column}"


def attribute_variants(attribute: str) -> list[str]:
    """Every Longi factor name `attribute` can resolve to across all group criteria: the name
    itself for an ordinary factor, all GROUP_COLUMNS twins for a group-specific one.
    preflight.required_files() unions these, so the input guard's same-newest-daynum rule
    covers a twinned pair whichever twin a given run ends up reading."""
    split = split_group_specific(attribute)
    if split is None:
        return [attribute]
    stem, _written = split
    return [f"{stem}_{column}" for column in GROUP_COLUMNS]


def resolve_params(params: dict) -> dict:
    """A finished param-set with all three attribute roles bound to its own group_column.

    The one call every path that finalizes params makes: dom_params() below (the resting
    defaults, at strategy-module import) and run_sweep.build_plan() (every swept parameter-set,
    since sweep_config feeds PRIORITY_ATTRIBUTE_DICTIONARY in wholesale and a swept name meets
    no family until then; walkforward reaches it through build_plan too). shared/dominance.py
    calls it once more at the point of use, which is what catches a PARAMS dict assembled by
    some future path that forgot.

    Returns a new dict. A set with no group_column passes through untouched — a non-Dom
    strategy has no criterion to bind to.
    """
    group_column = params.get("group_column")
    out = dict(params)
    if group_column is None:
        return out
    for key in ("dominance_attribute", "priority_attribute"):
        if out.get(key):
            out[key] = resolve_attribute(out[key], group_column, key)
    value = out.get("informational_attributes")
    if value:
        names = [value] if isinstance(value, str) else list(value)
        out["informational_attributes"] = [
            resolve_attribute(name, group_column, "informational_attributes") for name in names]
    return out


# The "classic" backtest knobs, common to every strategy in this project.
FOCUSSET_SIZE: int = 5             # tickers picked per hop
STEP: int = 1                        # daynum step between hops
PERIOD: int = 20                     # forward horizon in trading days. Must be a member of
                                      # shared.config.FUTURE_PERIODS, the "seven-pack" ladder:
                                      # 1, 5, 10, 20, 50, 100, 200. 20 is the primary horizon —
                                      # "20d dominations" reveal strategy variation cleanly, so
                                      # no second horizon is swept. Doubles as the hold length
                                      # the chain spaces its lots by.
NO_GO_GSPC_RSI: int = 0             # suppress picks / chain hops when GSPC RSI < this
FROM_RANK: int = 1                   # which end of the (already directionally-graded)
                                      # priority_attribute pool to draw the focusset from:
                                      # 1=best n, -1=worst n. See shared/select.py.
MIN_CHAIN_LOTS: int = 3              # lots a run's chain must realize before it may
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
# NOTE on the group-specific factors (conf, sectorbeta — see GROUP_SPECIFIC_FACTORS at the
# top of this module): a name listed here is swept for EVERY strategy, so it meets both
# families. Write the BARE STEM — "conf", not "conf_GICS" — and each family reads its own
# twin (longi_conf_GICS.csv for the GICS strategies, longi_conf_Sector2.csv for the Sector2
# ones), one dictionary entry covering both, each column of best_strategy.xlsx recording
# which twin it actually read. A twin written out explicitly is retargeted to the running
# family's own rather than used as written, so it can no longer cross-wire — but the stem is
# the spelling that says what is meant. The direction below belongs to the FACTOR, not to the
# criterion: both twins measure the same thing against a different grouping.
#
# Sorthand:  True = small is best= small wins
# ---------------------------------------------------------------------------
PRIORITY_ATTRIBUTE_DICTIONARY: dict[str, bool] = {
    #"beta3m":         False,
    #"conf":           True,    # group-specific: conf_GICS / conf_Sector2 per family, bound
                               # automatically. Når False (dvs høj er bedst), er der stort set
                               # kun US-aktier
    #"macd_histogram": False,
    #"median_10d":     True,
    #"median_20d":     True,
    #"median_30d":     True,
    #"median_40d":     True,
    #"median_100d":    True,
    #"PdivMA20":       False,
    #"PdivMA50":       False,
    #"per1d" :         False,
    #"per5d" :         False,
    #"per20d":         False,
    #"quot1020":       False,
    #"quot2050":       False,
    #"rank":           False,       #rank=True (små-er-bedst) giver avg_gain=5% & worst=-36%
    #"rsi":            False,
    #"sh3m":           False,
    "spr100d":        False, 
    #"spr250d":        False,     #False bedst
    #"vola20d":        False,
    #"vola100d":        False,     #True dur ikke
}
# Resting (non-swept) default: the first entry above, derived (never hand-duplicated) so
# it can't drift out of sync with the dictionary it comes from.
PRIORITY_ATTRIBUTE: str = next(iter(PRIORITY_ATTRIBUTE_DICTIONARY))
PRIORITY_ATTRIBUTE_DIRECTION: bool = PRIORITY_ATTRIBUTE_DICTIONARY[PRIORITY_ATTRIBUTE]


def priority_direction_for(attribute: str) -> bool:
    """Step-2 direction for a swept priority_attribute name, accepting either spelling of a
    group-specific factor: the bare stem ("conf") or either twin ("conf_GICS"). The direction
    is a property of the factor, so both twins resolve to the one dictionary entry and cannot
    be given conflicting directions.

    KeyError (not a default) on an unregistered name — run_sweep turns it into the "add its
    direction to PRIORITY_ATTRIBUTE_DICTIONARY first" error, since a wrong direction silently
    inverts which tickers count as best and is undetectable from the output.
    """
    if attribute in PRIORITY_ATTRIBUTE_DICTIONARY:
        return PRIORITY_ATTRIBUTE_DICTIONARY[attribute]
    split = split_group_specific(attribute)
    if split is not None and split[0] in PRIORITY_ATTRIBUTE_DICTIONARY:
        return PRIORITY_ATTRIBUTE_DICTIONARY[split[0]]
    raise KeyError(attribute)

TICKERS_PER_GROUP: int = 5  # top candidates (by PRIORITY_ATTRIBUTE) drawn from EACH
                            # dominating group into the pooled test-set — Step 2 only;
                            # distinct from Step 1's DOM_COUNT_THRESHOLD above. Shared by
                            # both group criteria: 2 was tried for Sector2 (where 3 of a
                            # small sector is most of it) and left too many good
                            # opportunities behind.

# ---------------------------------------------------------------------------
# Step 3 — informational only: shown alongside the picks (mean/median per day in run*.xlsx
# and the extension tabs) purely for insight into what's going on along the timeline.
# Never affects which tickers get selected, how test-sets are built, or anything else.
#
# ONE list for every family: a group-specific entry is written as its bare stem ("conf",
# "sectorbeta") and bound to each family's own twin by resolve_attribute — so the GICS
# strategies display longi_conf_GICS and the Sector2 ones longi_conf_Sector2 without the list
# being written twice. (This used to be a dict keyed by group_column, one hand-maintained
# list per criterion, which put the burden of never crossing the twins on whoever edited it
# and covered only this role — Steps 1 and 2 had no equivalent at all.)
# ---------------------------------------------------------------------------
INFORMATIONAL_ATTRIBUTES: list[str] = ["per1d", "rank", "rsi", "spr100d"]


def informational_attributes_for(group_column: str) -> list[str]:
    """Step-3 display-only factor names, bound to one group criterion's twins. A fresh list,
    since it lands in a strategy's live PARAMS dict that run_sweep mutates in place."""
    return [resolve_attribute(name, group_column, "informational_attributes")
            for name in INFORMATIONAL_ATTRIBUTES]


# ---------------------------------------------------------------------------
# The PARAMS dict every strategy_Dom*.py copies
# ---------------------------------------------------------------------------

def dom_params(strategy_name: str, group_column: str, period: int = PERIOD) -> dict:
    """The full PARAMS dict for one Dom* strategy.

    Six strategies share one 15-key parameter list; writing it out per module is how a
    rename ends up half-applied (it has happened here before). This is the one copy.

    Returns a FRESH dict on every call — run_sweep.run_strategy mutates module.PARAMS in
    place (PARAMS.clear() + update()), so two modules must never share one object.

    Every attribute role is passed through resolve_params(), so a group-specific factor named
    anywhere above (as a bare stem or as one twin) reaches this strategy as ITS OWN twin —
    see GROUP_SPECIFIC_FACTORS at the top of this module.
    """
    dominance_attribute, dominance_attribute_direction = dominance_attribute_for(strategy_name)
    return resolve_params({
        "focusset_size": FOCUSSET_SIZE,
        "step": STEP,
        "period": period,           # forward horizon in trading days — see PERIOD above
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
    })
