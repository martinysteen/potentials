"""
GICS-sector "domination" signal and ticker selection for the DomGICS_* strategy family.

Bypasses shared.engine's per-ticker filter chain — that engine has no group-by-sector
aggregation and no trailing-window primitive — but produces the exact same hop_results
shape make_strategy().main() does, so shared.report.save_report and shared.extension
apply unchanged.

Pipeline (one daynum):
    1. gics_dominance_now: count tickers per GICS that "beat" rank_threshold on
       longi_{priority_attribute}.csv — below it when priority_ascending (smaller wins,
       e.g. rank, the default), above it otherwise (bigger wins). A GICS with
       >= dom_count_threshold such tickers is "dominating" that daynum.
    2. add_persistence: a GICS is also dom_20d/dom_50d when it held dom_now on at least
       persistence_frac of the trailing 20/50 daynums (inclusive of the daynum itself).
    3. select_focusset: each dominating GICS contributes its BEST tickers_per_gics
       tickers by longi_{info_attribute}.csv (bigger always wins — a fixed convention,
       not configurable like priority_attribute's direction) — or its WORST
       tickers_per_gics when from_rank=-1, so a bottom-pick draws from genuinely weak
       tickers rather than the weakest of an already-best-biased pool. The pooled
       candidates are then re-ranked globally by the same value and pick_by_rank's
       from_rank window applied (1=best n, -1=worst n) — same "smaller is better" trick
       shared.engine's rank_by uses (negate a bigger-is-better series before handing it
       to pick_by_rank).

priority_attribute/priority_ascending default to run_config.PRIORITY_ATTRIBUTE/
PRIORITY_ASCENDING; info_attribute defaults to run_config.INFO_ATTRIBUTE.
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

def gics_dominance_now(rank_threshold: float, dom_count_threshold: int,
                       priority_attribute: str = "rank",
                       priority_ascending: bool = True) -> pd.DataFrame:
    """GICS x daynum boolean: True where >= dom_count_threshold tickers of that GICS
    beat rank_threshold on longi_{priority_attribute}.csv on that daynum — "beat" means
    below the threshold when priority_ascending (smaller wins), above it otherwise."""
    signal = load_longi(f"longi_{priority_attribute}.csv")
    gics = load_stamdata()["GICS"].dropna()
    common = signal.index.intersection(gics.index)
    vals = signal.loc[common]
    qualifying = vals < rank_threshold if priority_ascending else vals > rank_threshold
    counts = qualifying.groupby(gics.loc[common]).sum()
    return counts >= dom_count_threshold


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


def dominance_tables(rank_threshold: float, dom_count_threshold: int,
                     persistence_frac: float,
                     priority_attribute: str = "rank",
                     priority_ascending: bool = True) -> dict[str, pd.DataFrame]:
    """{'dom_now', 'dom_20d', 'dom_50d'} -> GICS x daynum boolean matrices."""
    dom_now = gics_dominance_now(rank_threshold, dom_count_threshold,
                                 priority_attribute, priority_ascending)
    return {
        "dom_now": dom_now,
        "dom_20d": add_persistence(dom_now, 20, persistence_frac),
        "dom_50d": add_persistence(dom_now, 50, persistence_frac),
    }


# ---------------------------------------------------------------------------
# Ticker selection
# ---------------------------------------------------------------------------

def select_focusset(daynum: int, dom_wide: pd.DataFrame, tickers_per_gics: int,
                    focusset_size: int, from_rank: int = 1,
                    info_attribute: str = "per1d") -> list[str]:
    """Tickers for one daynum: each GICS dominating on `dom_wide` at this daynum
    contributes its tickers_per_gics BEST tickers by longi_{info_attribute}.csv (bigger
    always wins) when from_rank=1, or its tickers_per_gics WORST when from_rank=-1 — the
    per-sector pool tracks the same end of the ranking the final pick draws from, so a
    bottom-pick reaches genuinely weak tickers rather than the weakest of an already-
    best-biased pool. The pooled candidates are then re-ranked globally by the same
    value and the focusset_size/from_rank window applied. [] if the daynum has no data
    or no dominating GICS — a clean no-pick (cash) hop, never an error."""
    col = str(daynum)
    if col not in dom_wide.columns:
        return []
    dominant = dom_wide.index[dom_wide[col].fillna(False)]
    if len(dominant) == 0:
        return []

    info = load_longi(f"longi_{info_attribute}.csv")
    if col not in info.columns:
        return []
    gics = load_stamdata()["GICS"]

    # Which end of the ranking each sector's pool should draw from: the best (highest)
    # values for from_rank=1, the worst (lowest) for from_rank=-1.
    pool_ascending = from_rank != 1

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
    return pick_by_rank(-pooled, focusset_size, from_rank)   # pick_by_rank: smaller == better


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

    def _dom_wide() -> pd.DataFrame:
        return dominance_tables(params["rank_threshold"], params["dom_count_threshold"],
                                params["persistence_frac"],
                                params.get("priority_attribute", "rank"),
                                params.get("priority_ascending", True))[dom_col]

    def _selector(daynum: int, dom_wide: pd.DataFrame) -> list[str]:
        return select_focusset(daynum, dom_wide, params["tickers_per_gics"],
                               params["focusset_size"], params.get("from_rank", 1),
                               params.get("info_attribute", "per1d"))

    def main() -> None:
        period: int = params.get("period", 20)
        gain_df  = load_longi(f"future_gain{period}d.csv")
        dom_wide = _dom_wide()

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
            tickers = _selector(daynum, dom_wide)
            if not tickers:
                hop_results.append({
                    "daynum": daynum, "tickers": [], "gains": {},
                    "ref_values": get_reference_values(daynum),
                })
                daynum -= step
                continue
            hop_results.append({
                "daynum": daynum,
                "tickers": tickers,
                "gains": get_gains(gain_df, tickers, daynum),
                "ref_values": get_reference_values(daynum),
            })
            daynum -= step

        if not hop_results:
            print("No valid hops produced — no dominating GICS in the data range")
            sys.exit(1)

        save_report(strategy_name, params, hop_results)
        print(f"Done: {len(hop_results)} hops  "
              f"daynum {hop_results[0]['daynum']} -> {hop_results[-1]['daynum']}")

    def build_extension(workbook=None):
        from shared.extension import run_extension
        dom_wide = _dom_wide()
        return run_extension(strategy_name, params,
                             lambda dn: _selector(dn, dom_wide),
                             get_reference_values, workbook=workbook)

    return main, build_extension
