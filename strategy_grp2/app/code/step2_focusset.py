"""
Step 2 — filtering and sorting: pool each elevated group's best candidates, apply the
optional post_filter, re-rank globally, and take the from_rank window. Production runs
stop here — the result is the gross list that ships in StrategicStocks.xlsx.
"""

from __future__ import annotations

import pandas as pd

from shared.data_loader import load_longi
from shared.select import pick_by_rank
from shared import expression as expr
import step0_data
import step1_dominance
from step1_dominance import elevated_groups, elevated_members


def select_focusset(daynum: int, dom_table: pd.DataFrame, groups: pd.Series, params: dict,
                    post_filter: expr.PostFilterSpec) -> list[str]:
    """Tickers for one hop. [] whenever the daynum has no data, no elevated group, or the
    post_filter leaves nothing — a clean no-pick (cash) hop, never an error, mirroring
    strategy_grp v1's contract throughout."""
    elevated = elevated_groups(dom_table, daynum)
    if not elevated:
        return []

    col = str(daynum)
    info = load_longi(f"longi_{params['priority_attribute']}.csv")
    if col not in info.columns:
        return []

    priority_direction: bool = params["priority_direction"]
    from_rank = params["from_rank"]           # already parsed: ("edge"|"offset"|"quantile", v)

    # Each elevated group's OWN pool is drawn from its BEST candidates, for every from_rank
    # form except a plain worst-n pick ("edge", -1) — where each group's pool is drawn from
    # its worst instead, so a bottom-pick reaches genuinely weak tickers rather than the
    # weakest of an already-best-biased pool (see strategy_grp v1's shared/dominance.py).
    # The "mid"/quantile/offset windows still pool each group's best tickers_per_group —
    # the window itself is decided at the GLOBAL re-rank step below, not per group.
    best_first_ascending = priority_direction
    pool_ascending = (not best_first_ascending) if from_rank == ("edge", -1) else best_first_ascending

    members = elevated_members(elevated, groups)
    pools: list[pd.Series] = []
    for tickers in members.values():
        vals = info.loc[info.index.isin(tickers), col].dropna()
        if vals.empty:
            continue
        pools.append(vals.sort_values(ascending=pool_ascending).head(params["tickers_per_group"]))
    if not pools:
        return []
    pooled = pd.concat(pools)

    candidates = pooled.index.tolist()
    if post_filter.terms:
        candidates = expr.apply_post_filter(post_filter, daynum, candidates)
        if not candidates:
            return []
        pooled = pooled.loc[candidates]

    # pick_by_rank expects smaller == better; negate a bigger-wins series so its convention
    # still applies (same trick strategy_grp's shared/engine.rank_by uses).
    signed = pooled if priority_direction else -pooled
    return pick_by_rank(signed, params["focusset_size"], from_rank)


def current_pick(row_resolved: dict):
    """(daynum, tickers, elevated_groups, params, step0_result) for the CURRENT (newest)
    daynum — what production ships (StrategicStocks.xlsx) and what the output board's
    Runs/Step1_groups/Step2_picks sheets show. Raises ValueError if no group ever
    dominates with this row's Step-1 parameters."""
    s0 = step0_data.resolve_step0(row_resolved)
    params = dict(row_resolved)
    params["dominance_attribute"] = s0.dominance_attribute
    params["priority_attribute"] = s0.priority_attribute

    dom_table, _cutoffs = step1_dominance.resolve_dom_table(s0.groups, params)
    if dom_table.empty:
        raise ValueError("no group ever dominates with this row's Step-1 parameters")
    daynum = max(int(c) for c in dom_table.columns)
    elevated = step1_dominance.elevated_groups(dom_table, daynum)
    tickers = select_focusset(daynum, dom_table, s0.groups, params, s0.post_filter)
    return daynum, tickers, elevated, params, s0
