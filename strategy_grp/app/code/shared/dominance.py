"""
GICS-sector "domination" signal and ticker selection for the DomGICS_* strategy family.

Bypasses shared.engine's per-ticker filter chain — that engine has no group-by-sector
aggregation and no trailing-window primitive — but produces the exact same hop_results
shape make_strategy().main() does, so shared.report.save_report and shared.extension
apply unchanged.

Pipeline (one daynum) — three distinct attribute roles, see run_config.py:
    1. gics_dominance_now (Step 1 — elevation): count tickers per GICS that "beat" THAT
       DAY's best-decile cutoff of longi_{dominance_attribute}.csv — the value at the
       dominance_threshold_decile quantile of that attribute's cross-sectional distribution on
       that one daynum (every ticker, that day only — computed independently per day, not
       across history), direction-aware: below the cutoff when
       dominance_attribute_direction (smaller wins, e.g. rank, the default), above it
       otherwise (bigger wins). Scale-free by construction, so dominance_threshold_decile (a
       fraction, default 0.10 = best decile) means the same thing for any attribute — see
       _daily_decile_cutoff. A GICS with >= dom_count_threshold such tickers is
       "dominating" that daynum.
    2. add_persistence: a GICS is also dom_20d/dom_50d when it held dom_now on at least
       persistence_frac of the trailing 20/50 daynums (inclusive of the daynum itself).
    3. select_focusset (Step 2 — test-set construction): each dominating GICS
       contributes its BEST tickers_per_gics tickers by longi_{priority_attribute}.csv
       (direction-aware: smaller wins when priority_attribute_direction, bigger
       otherwise) — or its WORST tickers_per_gics when from_rank=-1, so a bottom-pick
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
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from shared.data_loader import load_longi, load_stamdata, daynum_to_date
from shared.engine import get_gains, get_reference_values
from shared.report import save_report
from shared.select import pick_by_rank


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


def gics_dominance_now(dominance_threshold_decile: float, dom_count_threshold: int,
                       dominance_attribute: str = "rank",
                       dominance_attribute_direction: bool = True
                       ) -> tuple[pd.DataFrame, pd.Series]:
    """GICS x daynum boolean: True where >= dom_count_threshold tickers of that GICS
    beat THAT DAY's best-decile cutoff of longi_{dominance_attribute}.csv (see
    _daily_decile_cutoff — dominance_threshold_decile is a fraction, e.g. 0.10 = best decile,
    not a raw value, computed independently per daynum) — "beat" means below the cutoff
    when dominance_attribute_direction (smaller wins), above it otherwise.

    Also returns the per-daynum cutoff Series (Step 1's day-by-day threshold, for
    reporting — see shared/report.py's dominance_cutoff row)."""
    signal = load_longi(f"longi_{dominance_attribute}.csv")
    cutoffs = _daily_decile_cutoff(signal, dominance_threshold_decile, dominance_attribute_direction)
    gics = load_stamdata()["GICS"].dropna()
    common = signal.index.intersection(gics.index)
    vals = signal.loc[common]
    qualifying = (vals.lt(cutoffs) if dominance_attribute_direction
                  else vals.gt(cutoffs))
    counts = qualifying.groupby(gics.loc[common]).sum()
    return counts >= dom_count_threshold, cutoffs


def add_persistence(dom_now: pd.DataFrame, window: int, frac_threshold: float) -> pd.DataFrame:
    """Row-wise (per GICS) trailing persistence: True where dom_now held on at least
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
                     dominance_attribute_direction: bool = True
                     ) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    """{'dom_now', 'dom_20d', 'dom_50d'} -> GICS x daynum boolean matrices, plus the
    per-daynum dominance cutoff Series (Step 1's day-by-day threshold — one value per
    daynum, shared by all three tiers since persistence is derived from dom_now, not
    from the cutoff itself)."""
    dom_now, cutoffs = gics_dominance_now(dominance_threshold_decile, dom_count_threshold,
                                          dominance_attribute, dominance_attribute_direction)
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


def select_focusset(daynum: int, dom_wide: pd.DataFrame, tickers_per_gics: int,
                    focusset_size: int, from_rank: int = 1,
                    priority_attribute: str = "rank",
                    priority_attribute_direction: bool = True) -> list[str]:
    """Tickers for one daynum: each GICS dominating on `dom_wide` at this daynum
    contributes its tickers_per_gics BEST tickers by longi_{priority_attribute}.csv
    (direction-aware: smaller wins when priority_attribute_direction, bigger otherwise)
    when from_rank=1, or its tickers_per_gics WORST when from_rank=-1 — the per-sector
    pool tracks the same end of the ranking the final pick draws from, so a bottom-pick
    reaches genuinely weak tickers rather than the weakest of an already-best-biased
    pool. The pooled candidates are then re-ranked globally by the same value and the
    focusset_size/from_rank window applied. [] if the daynum has no data or no
    dominating GICS — a clean no-pick (cash) hop, never an error.
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
    gics = load_stamdata()["GICS"]

    # Best-first sort order for this attribute: ascending when smaller wins, descending
    # when bigger wins. from_rank=1 draws each sector's pool from the best end;
    # from_rank=-1 draws from the worst end (the reverse order).
    best_first_ascending = priority_attribute_direction
    pool_ascending = best_first_ascending if from_rank == 1 else not best_first_ascending

    pools: list[pd.Series] = []
    for sector in dominant:
        sector_tickers = gics.index[gics == sector]
        vals = info.loc[info.index.isin(sector_tickers), col].dropna()
        if vals.empty:
            continue
        pools.append(vals.sort_values(ascending=pool_ascending).head(tickers_per_gics))

    if not pools:
        return []
    pooled = pd.concat(pools)
    # pick_by_rank expects smaller == better; negate a bigger-wins series so its
    # convention still applies (same trick shared.engine.rank_by uses).
    signed = pooled if priority_attribute_direction else -pooled
    return pick_by_rank(signed, focusset_size, from_rank)


# ---------------------------------------------------------------------------
# Strategy factory — the make_strategy() analog for the DomGICS family
# ---------------------------------------------------------------------------

def _find_start_daynum(gain_df: pd.DataFrame, min_valid: int = 10) -> int:
    """First daynum (newest first) where future_gain{period}d has sufficient realized data."""
    for col in gain_df.columns:
        if gain_df[col].dropna().size >= min_valid:
            return int(col)
    raise ValueError("No valid starting daynum found in future_gain data")


def make_dom_strategy(strategy_name: str, params: dict, dom_col: str):
    """
    Build the (main, build_extension) pair for one DomGICS_* strategy — the same
    external contract shared.engine.make_strategy returns, so run_sweep.py's discovery
    and extension.py's per-strategy extension building work unmodified.

    `params` MUST be the module-level PARAMS dict (read live, mirroring make_strategy's
    contract with run_sweep's in-place PARAMS.clear()+update()). `dom_col` selects which
    dominance_tables() column ("dom_now"/"dom_20d"/"dom_50d") this strategy draws from.
    """

    def _dom_data() -> tuple[pd.DataFrame, pd.Series]:
        """(dom_wide, cutoffs) — this strategy's dominance table plus the per-daynum
        dominance cutoff Series (Step 1, day-by-day; see gics_dominance_now)."""
        tables, cutoffs = dominance_tables(params["dominance_threshold_decile"], params["dom_count_threshold"],
                                           params["persistence_frac"],
                                           params.get("dominance_attribute", "rank"),
                                           params.get("dominance_attribute_direction", True))
        return tables[dom_col], cutoffs

    def _selector(daynum: int, dom_wide: pd.DataFrame) -> list[str]:
        return select_focusset(daynum, dom_wide, params["tickers_per_gics"],
                               params["focusset_size"], params.get("from_rank", 1),
                               params.get("priority_attribute", "rank"),
                               params.get("priority_attribute_direction", True))

    def main() -> None:
        # Idempotent — a no-op when run_sweep/extension already froze the inputs, and the
        # guard when this strategy file is executed directly. Deferred import: preflight
        # reaches back into run_sweep -> strategies -> this module, so importing it at
        # module level would cycle.
        import preflight
        preflight.ensure_data()

        period: int = params.get("period", 20)
        gain_df  = load_longi(f"future_gain{period}d.csv")
        dom_wide, cutoffs = _dom_data()

        n: int    = params["focusset_size"]
        step: int = params["step"]

        start_daynum = _find_start_daynum(gain_df)
        min_daynum   = int(gain_df.columns[-1])

        print(f"--- {strategy_name} ---")
        print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
        print(f"Min daynum   : {min_daynum}")
        print(f"Focusset size: {n}   Step: {step}   Period: {period}d   Dom col: {dom_col}")
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
            print("No valid hops produced — no dominating GICS in the data range")
            sys.exit(1)

        # Second net behind preflight. An all-but-empty run is the exact signature of an
        # input problem that no longer raises: select_focusset returns [] whenever the
        # daynum is not a column, so a file of the wrong vintage yields a full-length run
        # of cash hops that looks healthy until the report is read. A persistence tier can
        # legitimately sit out long stretches, but not ~all of history.
        n_empty = sum(1 for h in hop_results if not h["tickers"])
        if n_empty > 0.9 * len(hop_results):
            print(f"  ** WARNING: {n_empty}/{len(hop_results)} hops picked nothing. "
                  f"If this is not expected for '{dom_col}', check the inputs: "
                  f"`python preflight.py`.")

        save_report(strategy_name, params, hop_results)
        print(f"Done: {len(hop_results)} hops  "
              f"daynum {hop_results[0]['daynum']} -> {hop_results[-1]['daynum']}")

    def build_extension(workbook=None):
        from shared.extension import run_extension
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
