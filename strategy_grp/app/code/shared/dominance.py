"""
Group "domination" signal and ticker selection for the Dom* strategy families
(DomGICS_now/_20d/_50d, DomSector2_now/_20d/_50d).

Bypasses shared.engine's per-ticker filter chain — that engine has no group-by-sector
aggregation and no trailing-window primitive — but produces the exact same hop_results
shape make_strategy().main() does, so shared.report.save_report and shared.extension
apply unchanged.

WHICH grouping is used is the `group_column` param: the name of a Stamdata.csv column
("GICS" or "Sector2") whose values the tickers are bucketed by. It is deliberately not
called an "attribute" — that word is taken by the three Longi-factor roles below, and this
project has already been broken once by conflating them. See run_config.py's docstring.

Pipeline (one daynum) — three distinct attribute roles, see run_config.py:
    1. group_dominance_now (Step 1 — elevation): count tickers per group that "beat" THAT
       DAY's best-decile cutoff of longi_{dominance_attribute}.csv — the value at the
       dominance_threshold_decile quantile of that attribute's cross-sectional distribution on
       that one daynum (every ticker, that day only — computed independently per day, not
       across history), direction-aware: below the cutoff when
       dominance_attribute_direction (smaller wins, e.g. rank, the default), above it
       otherwise (bigger wins). Scale-free by construction, so dominance_threshold_decile (a
       fraction, default 0.10 = best decile) means the same thing for any attribute — see
       _daily_decile_cutoff. A group with >= dom_count_threshold such tickers is
       "dominating" that daynum. NOTE dom_count_threshold is an absolute count and so is
       NOT transferable between group criteria — a 24-ticker Sector2 cannot meet a
       threshold set for a 93-ticker GICS; run_config.dom_count_threshold_for() holds the
       per-criterion value.
    2. add_persistence: a group is also dom_20d/dom_50d when it held dom_now on at least
       persistence_frac of the trailing 20/50 daynums (inclusive of the daynum itself).
    3. select_focusset (Step 2 — test-set construction): each dominating group
       contributes its BEST tickers_per_group tickers by longi_{priority_attribute}.csv
       (direction-aware: smaller wins when priority_attribute_direction, bigger
       otherwise) — or its WORST tickers_per_group when from_rank=-1, so a bottom-pick
       draws from genuinely weak tickers rather than the weakest of an already-best-
       biased pool. The pooled candidates are then re-ranked globally by the same value
       and pick_by_rank's from_rank window applied (1=best n, -1=worst n) — same
       "smaller is better" trick shared.engine's rank_by uses (negate a bigger-is-better
       series before handing it to pick_by_rank).

dominance_attribute/dominance_attribute_direction default to run_config.DOMINANCE_ATTRIBUTE/
DOMINANCE_ATTRIBUTE_DIRECTION; priority_attribute/priority_attribute_direction default to
run_config.PRIORITY_ATTRIBUTE/PRIORITY_ATTRIBUTE_DIRECTION (one attribute at a time — the
candidates worth testing are enumerated in run_config.PRIORITY_ATTRIBUTE_DICTIONARY and
swept by sweep_config.py, each defining an independent test-set/run).

informational_attr_list (Step 3 — display only, see run_config.INFORMATIONAL_ATTRIBUTES)
normalizes a name-or-list param for shared/report.py and shared/extension.py; it never
feeds selection.

All three roles are passed through bind_group_attributes() before a run reads anything, so a
group-specific factor (longi_conf_GICS/longi_conf_Sector2, longi_sectorbeta_*) is always the
twin matching THIS strategy's group_column — never the other family's. See
run_config.GROUP_SPECIFIC_FACTORS for the rule and TwinUnavailable for the one case that
aborts instead of binding.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import run_config as cfg
from shared.config import active_longi, future_gain_file
from shared.data_loader import load_longi, load_stamdata, daynum_to_date
from shared.engine import get_gains, get_reference_values
from shared.report import save_report
from shared.select import pick_by_rank


# ---------------------------------------------------------------------------
# Group-specific attributes — bound to this strategy's own criterion at the point of use
# ---------------------------------------------------------------------------

class TwinUnavailable(Exception):
    """A group-specific factor's twin for this strategy's group_column is not in the data.

    Deliberately NOT a DataUnavailable: that one means the repository is mid-update and every
    remaining run would fail identically, so run_sweep re-raises it and stops. This means one
    criterion's twin is missing while the other's is fine — the GICS family can complete and
    only the Sector2 strategies have nothing to read. run_sweep's per-run `except Exception`
    catches it, prints it, and lets the sweep finish, so the strategies that CAN run still get
    their columns in best_strategy.xlsx.
    """


def bind_group_attributes(params: dict) -> dict:
    """Bind every group-specific attribute in a live PARAMS dict to its own group_column.

    Resolution normally happened upstream (run_config.dom_params for the resting defaults,
    run_sweep.build_plan for a swept set); this is the backstop that makes it unconditional —
    a PARAMS dict assembled by any other path (a future entry point, a hand-edited module, a
    row read back from a report) is corrected here rather than quietly reading the wrong twin.

    Writes the resolved names back into `params` IN PLACE — it is the live dict the report is
    written from, so this is what makes run*.xlsx / summary.csv / best_strategy.xlsx name the
    twin the run actually read instead of the one that was configured. Returns it for chaining.

    Raises TwinUnavailable when the bound twin has no file; ValueError (from
    run_config.resolve_attribute) when there is no twin to bind to at all.
    """
    resolved = cfg.resolve_params(params)
    for role in ("dominance_attribute", "priority_attribute"):
        if resolved.get(role):
            _require_available(resolved[role], role, params.get("group_column"))
    for name in informational_attr_list(resolved.get("informational_attributes")):
        _require_available(name, "informational_attributes", params.get("group_column"))
    params.update(resolved)
    return params


def _require_available(attribute: str, role: str, group_column: str | None) -> None:
    """TwinUnavailable if a group-specific factor's bound twin is not on disk. Only checked
    for group-specific names: an ordinary missing factor is preflight's business (a whole-run
    input failure), while a missing twin is specific to one family and must not take the
    other one down with it."""
    if cfg.split_group_specific(attribute) is None:
        return
    path = active_longi() / f"longi_{attribute}.csv"
    if path.exists():
        return
    raise TwinUnavailable(
        f"{role}='{attribute}': group_column='{group_column}' needs {path.name}, which is not "
        f"in {active_longi()}. The other criterion's twin is unaffected — its strategies still "
        f"run. Check that the group_conformity cron published this twin (`python preflight.py`).")


# ---------------------------------------------------------------------------
# Dominance computation
# ---------------------------------------------------------------------------

def _daily_decile_cutoff(signal: pd.DataFrame, decile: float,
                         dominance_attribute_direction: bool) -> pd.Series:
    """Per-daynum quantile of signal's cross-sectional distribution — each day's OWN
    best-decile cutoff (every ticker on that daynum, NaN dropped), computed independently
    day by day, not across the full history. Scale-free: the same `decile` fraction (e.g.
    0.10) means "best 10%" for any attribute, whatever its raw range (rank 1..~1200, rsi
    0..100, beta3m usually <5, ...), so dominance_attribute can be swapped without
    recalibrating a raw-value threshold by hand.

    Returns a Series indexed by daynum (signal's columns).

    direction=True  (smaller wins, e.g. rank): boundary of the SMALLEST `decile` fraction
                     -> low quantile (e.g. 0.10 -> 10th percentile).
    direction=False (bigger wins):             boundary of the LARGEST `decile` fraction
                     -> high quantile (e.g. 0.10 -> 90th percentile, i.e. 1 - decile).
    """
    q = decile if dominance_attribute_direction else 1 - decile
    return signal.quantile(q, axis=0)


def group_dominance_now(dominance_threshold_decile: float, dom_count_threshold: int,
                        dominance_attribute: str = "rank",
                        dominance_attribute_direction: bool = True,
                        group_column: str = "GICS"
                        ) -> tuple[pd.DataFrame, pd.Series]:
    """group x daynum boolean: True where >= dom_count_threshold tickers of that group
    beat THAT DAY's best-decile cutoff of longi_{dominance_attribute}.csv (see
    _daily_decile_cutoff — dominance_threshold_decile is a fraction, e.g. 0.10 = best decile,
    not a raw value, computed independently per daynum) — "beat" means below the cutoff
    when dominance_attribute_direction (smaller wins), above it otherwise.

    `group_column` names the Stamdata.csv column the tickers are bucketed by ("GICS" or
    "Sector2"); the index of the returned frame is that column's values.

    Also returns the per-daynum cutoff Series (Step 1's day-by-day threshold, for
    reporting — see shared/report.py's dominance_cutoff row)."""
    signal = load_longi(f"longi_{dominance_attribute}.csv")
    cutoffs = _daily_decile_cutoff(signal, dominance_threshold_decile, dominance_attribute_direction)
    groups = load_stamdata()[group_column].dropna()
    common = signal.index.intersection(groups.index)
    vals = signal.loc[common]
    qualifying = (vals.lt(cutoffs) if dominance_attribute_direction
                  else vals.gt(cutoffs))
    counts = qualifying.groupby(groups.loc[common]).sum()
    return counts >= dom_count_threshold, cutoffs


def add_persistence(dom_now: pd.DataFrame, window: int, frac_threshold: float) -> pd.DataFrame:
    """Row-wise (per group) trailing persistence: True where dom_now held on at least
    frac_threshold of the `window` daynums ending at (and including) that daynum.

    Columns are newest-left in the source data, so this re-sorts ascending by daynum to
    make pandas' trailing rolling window land on the OLDER days, then restores the
    original column order."""
    ascending_cols = sorted(dom_now.columns, key=int)
    ascending = dom_now[ascending_cols]
    frac = ascending.T.rolling(window, min_periods=window).mean().T
    return (frac >= frac_threshold)[dom_now.columns]


def dominance_tables(dominance_threshold_decile: float, dom_count_threshold: int,
                     persistence_frac: float,
                     dominance_attribute: str = "rank",
                     dominance_attribute_direction: bool = True,
                     group_column: str = "GICS"
                     ) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    """{'dom_now', 'dom_20d', 'dom_50d'} -> group x daynum boolean matrices, plus the
    per-daynum dominance cutoff Series (Step 1's day-by-day threshold — one value per
    daynum, shared by all three tiers since persistence is derived from dom_now, not
    from the cutoff itself).

    NOTE for callers that memoize this (walkforward.py): `group_column` is part of the
    identity of the result — two criteria with otherwise identical Step-1 params produce
    completely different tables."""
    dom_now, cutoffs = group_dominance_now(dominance_threshold_decile, dom_count_threshold,
                                           dominance_attribute, dominance_attribute_direction,
                                           group_column)
    tables = {
        "dom_now": dom_now,
        "dom_20d": add_persistence(dom_now, 20, persistence_frac),
        "dom_50d": add_persistence(dom_now, 50, persistence_frac),
    }
    return tables, cutoffs


# ---------------------------------------------------------------------------
# Ticker selection
# ---------------------------------------------------------------------------

def informational_attr_list(value: str | list[str] | None) -> list[str]:
    """Normalize a Step-3 informational_attributes param to a list of longi factor short
    names. Accepts a single name or a list of several (e.g. ["per1d", "macd_histogram"]);
    [] when the value is falsy. Display only (shared/report.py, shared/extension.py show
    mean/median rows for every entry) — never feeds selection; see select_focusset for that.
    """
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


def select_focusset(daynum: int, dom_wide: pd.DataFrame, tickers_per_group: int,
                    focusset_size: int, from_rank: int = 1,
                    priority_attribute: str = "rank",
                    priority_attribute_direction: bool = True,
                    group_column: str = "GICS") -> list[str]:
    """Tickers for one daynum: each group dominating on `dom_wide` at this daynum
    contributes its tickers_per_group BEST tickers by longi_{priority_attribute}.csv
    (direction-aware: smaller wins when priority_attribute_direction, bigger otherwise)
    when from_rank=1, or its tickers_per_group WORST when from_rank=-1 — the per-sector
    pool tracks the same end of the ranking the final pick draws from, so a bottom-pick
    reaches genuinely weak tickers rather than the weakest of an already-best-biased
    pool. The pooled candidates are then re-ranked globally by the same value and the
    focusset_size/from_rank window applied. [] if the daynum has no data or no
    dominating group — a clean no-pick (cash) hop, never an error.

    `group_column` must be the SAME Stamdata column `dom_wide` was built from (its index
    holds that column's values) — see dominance_tables.
    """
    col = str(daynum)
    if col not in dom_wide.columns:
        return []
    dominant = dom_wide.index[dom_wide[col].fillna(False)]
    if len(dominant) == 0:
        return []

    info = load_longi(f"longi_{priority_attribute}.csv")
    if col not in info.columns:
        return []
    groups = load_stamdata()[group_column]

    # Best-first sort order for this attribute: ascending when smaller wins, descending
    # when bigger wins. from_rank=1 draws each sector's pool from the best end;
    # from_rank=-1 draws from the worst end (the reverse order).
    best_first_ascending = priority_attribute_direction
    pool_ascending = best_first_ascending if from_rank == 1 else not best_first_ascending

    pools: list[pd.Series] = []
    for sector in dominant:
        sector_tickers = groups.index[groups == sector]
        vals = info.loc[info.index.isin(sector_tickers), col].dropna()
        if vals.empty:
            continue
        pools.append(vals.sort_values(ascending=pool_ascending).head(tickers_per_group))

    if not pools:
        return []
    pooled = pd.concat(pools)
    # pick_by_rank expects smaller == better; negate a bigger-wins series so its
    # convention still applies (same trick shared.engine.rank_by uses).
    signed = pooled if priority_attribute_direction else -pooled
    return pick_by_rank(signed, focusset_size, from_rank)


# ---------------------------------------------------------------------------
# Flicker — turnover diagnostics (never rank on these)
# ---------------------------------------------------------------------------
#
# A finer group criterion promotes on a noisier count (5-of-24 vs 10-of-93), so its
# dominating set should swing harder day to day. Whether that is chasing noise or tracking
# real sector rotation is the open question; these two numbers are what make the
# stability<->rotation trade visible instead of implicit in three chain_annual values.
#
# DIAGNOSTIC ONLY, like origin_sens%. The chain takes non-overlapping lots spaced >= period
# apart, so every lot is a fresh purchase however much the picks churned in between:
# turnover costs chain_annual exactly nothing and there is no transaction-cost argument to
# make here. What flicker actually costs is followability — a daily recommendation that
# changes under the user — which is a reason to prefer a persistence tier, not a return
# penalty. Do not let these into best_run().
#
# Both are measured per STEP (not per trading day), so they are only comparable across runs
# that share `step`.

def _set_turnover(previous: set[str], current: set[str]) -> float:
    """Jaccard distance: |A Δ B| / |A ∪ B|. 0 = identical, 1 = no overlap."""
    union = previous | current
    if not union:
        return 0.0
    return len(previous ^ current) / len(union)


def turnover_stats(hop_results: list[dict], dom_wide: pd.DataFrame) -> dict[str, float]:
    """{'pick_turnover', 'group_turnover'} over consecutive hops.

    Only pairs where BOTH hops are invested are counted. Cash gaps are the persistence
    gate doing its job and are already reported by chain_inv%/N_hops_active; folding them
    in here would make a strategy that sits out half the time look maximally flickery
    for the opposite reason.

    Returns NaN for a measure with no qualifying adjacent pair (e.g. a run of isolated
    single hops), never 0 — 0 means "measured, and perfectly stable".
    """
    pick_moves: list[float] = []
    group_moves: list[float] = []
    prev_tickers: set[str] | None = None
    prev_groups: set[str] | None = None

    for hop in hop_results:
        tickers = set(hop["tickers"])
        col = str(hop["daynum"])
        groups = (set(dom_wide.index[dom_wide[col].fillna(False)])
                  if col in dom_wide.columns else set())
        if tickers and prev_tickers:
            pick_moves.append(_set_turnover(prev_tickers, tickers))
        if groups and prev_groups:
            group_moves.append(_set_turnover(prev_groups, groups))
        prev_tickers = tickers or None
        prev_groups = groups or None

    nan = float("nan")
    return {
        "pick_turnover":  sum(pick_moves) / len(pick_moves) if pick_moves else nan,
        "group_turnover": sum(group_moves) / len(group_moves) if group_moves else nan,
    }


# ---------------------------------------------------------------------------
# Strategy factory — the make_strategy() analog for the Dom* families
# ---------------------------------------------------------------------------

def _find_start_daynum(gain_df: pd.DataFrame, min_valid: int = 10) -> int:
    """First daynum (newest first) where the forward-gain file has sufficient realized data."""
    for col in gain_df.columns:
        if gain_df[col].dropna().size >= min_valid:
            return int(col)
    raise ValueError("No valid starting daynum found in the forward-gain file")


def make_dom_strategy(strategy_name: str, params: dict, dom_col: str):
    """
    Build the (main, build_extension) pair for one Dom* strategy — the same
    external contract shared.engine.make_strategy returns, so run_sweep.py's discovery
    and extension.py's per-strategy extension building work unmodified.

    `params` MUST be the module-level PARAMS dict (read live, mirroring make_strategy's
    contract with run_sweep's in-place PARAMS.clear()+update()). `dom_col` selects which
    dominance_tables() column ("dom_now"/"dom_20d"/"dom_50d") this strategy draws from.
    The group criterion comes from params["group_column"].
    """

    def _dom_data() -> tuple[pd.DataFrame, pd.Series]:
        """(dom_wide, cutoffs) — this strategy's dominance table plus the per-daynum
        dominance cutoff Series (Step 1, day-by-day; see group_dominance_now)."""
        tables, cutoffs = dominance_tables(params["dominance_threshold_decile"], params["dom_count_threshold"],
                                           params["persistence_frac"],
                                           params.get("dominance_attribute", "rank"),
                                           params.get("dominance_attribute_direction", True),
                                           # Required, NOT params.get(..., "GICS"): a missing
                                           # key silently grouping by GICS would produce a
                                           # complete, plausible, wrong run — exactly the
                                           # failure mode this project's input guard exists
                                           # for. A KeyError is the loud alternative.
                                           params["group_column"])
        return tables[dom_col], cutoffs

    def _selector(daynum: int, dom_wide: pd.DataFrame) -> list[str]:
        return select_focusset(daynum, dom_wide, params["tickers_per_group"],
                               params["focusset_size"], params.get("from_rank", 1),
                               params.get("priority_attribute", "rank"),
                               params.get("priority_attribute_direction", True),
                               params["group_column"])

    def main() -> None:
        # Idempotent — a no-op when run_sweep/extension already froze the inputs, and the
        # guard when this strategy file is executed directly. Deferred import: preflight
        # reaches back into run_sweep -> strategies -> this module, so importing it at
        # module level would cycle.
        import preflight
        preflight.ensure_data()

        # AFTER the snapshot, so the twin-availability check reads what this run will read.
        bind_group_attributes(params)

        period: int = params.get("period", 20)
        gain_df  = load_longi(future_gain_file(period))
        dom_wide, cutoffs = _dom_data()

        n: int    = params["focusset_size"]
        step: int = params["step"]
        group_column: str = params["group_column"]

        start_daynum = _find_start_daynum(gain_df)
        min_daynum   = int(gain_df.columns[-1])

        print(f"--- {strategy_name} ---")
        print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
        print(f"Min daynum   : {min_daynum}")
        print(f"Focusset size: {n}   Step: {step}   Period: {period}d   Dom col: {dom_col}")
        # Group first: with two families in one sweep, the tier alone no longer identifies
        # which run is scrolling past.
        print(f"Group by     : {group_column}   "
              f"dom_count_threshold: {params['dom_count_threshold']}")
        # The BOUND attribute names, so a group-specific factor's twin is visible in the log
        # as well as in the report (see run_config.GROUP_SPECIFIC_FACTORS): a sweep of "conf"
        # scrolls past as conf_GICS here and conf_Sector2 there.
        print(f"Dominance on : {params['dominance_attribute']}   "
              f"Priority on: {params['priority_attribute']}")
        print()

        hop_results: list[dict] = []
        daynum = start_daynum
        while daynum >= min_daynum:
            cutoff = cutoffs.get(str(daynum))
            dom_cutoff = float(cutoff) if pd.notna(cutoff) else None
            tickers = _selector(daynum, dom_wide)
            if not tickers:
                hop_results.append({
                    "daynum": daynum, "tickers": [], "gains": {},
                    "ref_values": get_reference_values(daynum),
                    "dom_cutoff": dom_cutoff,
                })
                daynum -= step
                continue
            hop_results.append({
                "daynum": daynum,
                "tickers": tickers,
                "gains": get_gains(gain_df, tickers, daynum),
                "ref_values": get_reference_values(daynum),
                "dom_cutoff": dom_cutoff,
            })
            daynum -= step

        if not hop_results:
            print(f"No valid hops produced — no dominating {group_column} in the data range")
            sys.exit(1)

        # Second net behind preflight. An all-but-empty run is the exact signature of an
        # input problem that no longer raises: select_focusset returns [] whenever the
        # daynum is not a column, so a file of the wrong vintage yields a full-length run
        # of cash hops that looks healthy until the report is read. A persistence tier can
        # legitimately sit out long stretches, but not ~all of history.
        n_empty = sum(1 for h in hop_results if not h["tickers"])
        if n_empty > 0.9 * len(hop_results):
            print(f"  ** WARNING: {n_empty}/{len(hop_results)} hops picked nothing. "
                  f"If this is not expected for '{dom_col}' on {group_column}, either the "
                  f"inputs are bad (`python preflight.py`) or dom_count_threshold "
                  f"({params['dom_count_threshold']}) is too high for {group_column}'s "
                  f"sector sizes.")

        turnover = turnover_stats(hop_results, dom_wide)
        save_report(strategy_name, params, hop_results, extra_summary=turnover)
        print(f"Done: {len(hop_results)} hops  "
              f"daynum {hop_results[0]['daynum']} -> {hop_results[-1]['daynum']}  "
              f"pick_turnover {turnover['pick_turnover']:.3f}  "
              f"group_turnover {turnover['group_turnover']:.3f}")

    def build_extension(workbook=None):
        from shared.extension import run_extension
        # The extension is reached from extension.py, which binds a winning run's params onto
        # the module without going through the sweep — so it needs the same binding main()
        # does, or a report sheet could name one twin while the picks came from the other.
        bind_group_attributes(params)
        dom_wide, _cutoffs = _dom_data()
        return run_extension(strategy_name, params,
                             lambda dn: _selector(dn, dom_wide),
                             get_reference_values, workbook=workbook)

    # Tag the entry point with the tier it draws from, so a caller holding only the
    # discovered module (run_sweep.discover_strategies) can tell a DomGICS_* strategy
    # from a plain filter one and rebuild its picks itself — walkforward.py needs this.
    # Purely informational; nothing in the run path reads it.
    main.strategy_name = strategy_name
    main.dom_col = dom_col

    return main, build_extension
