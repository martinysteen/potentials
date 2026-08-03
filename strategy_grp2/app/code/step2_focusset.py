"""
Step 2 — filtering and sorting. Two distinct outputs share Step 1's elevated groups:

  select_focusset() — Step 3/4's fixed, comparable per-hop TEST SAMPLE: each group's pool
  capped to tickers_per_group, then the from_rank/focusset_size window. Backtest metrics
  need a stable sample size across hundreds of hops; this is that knob, board-driven.

  production_pick() — the actual gross list a user sees (StrategicStocks.xlsx,
  Step1_groups/Step2_picks): every currently-elevated group's FULL membership, filtered and
  priority-sorted, capped only by shared.config.PRODUCTION_GROSS_CAP. tickers_per_group,
  from_rank and focusset_size do not apply here (SM, 2026-08-03) — a small dominant group
  should never lose candidates to an arbitrary per-group pre-cut, and production always
  wants the best end of the ranking, never a deliberately worst/mid research window.
"""

from __future__ import annotations

import pandas as pd

from shared.data_loader import load_longi
from shared.select import pick_by_rank
from shared.config import PRODUCTION_GROSS_CAP
from shared import expression as expr
import step0_data
import step1_dominance
from step1_dominance import elevated_groups, elevated_members


def _pool(daynum: int, dom_table: pd.DataFrame, groups: pd.Series, params: dict,
         post_filter: expr.PostFilterSpec) -> pd.Series | None:
    """The Step-3/4 candidate pool for one hop: each elevated group capped to
    tickers_per_group, post_filter applied, sign-adjusted so smaller == better (matching
    pick_by_rank's convention). None when the hop has no data, no elevated group, or the
    post_filter leaves nothing. Shared by select_focusset (the final window) and
    step3_backtest (the "how many were available before picking N" count)."""
    elevated = elevated_groups(dom_table, daynum)
    if not elevated:
        return None

    col = str(daynum)
    info = load_longi(f"longi_{params['priority_attribute']}.csv")
    if col not in info.columns:
        return None

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
        return None
    pooled = pd.concat(pools)

    candidates = pooled.index.tolist()
    if post_filter.terms:
        candidates = expr.apply_post_filter(post_filter, daynum, candidates)
        if not candidates:
            return None
        pooled = pooled.loc[candidates]

    # pick_by_rank expects smaller == better; negate a bigger-wins series so its convention
    # still applies (same trick strategy_grp's shared/engine.rank_by uses).
    return pooled if priority_direction else -pooled


def select_focusset(daynum: int, dom_table: pd.DataFrame, groups: pd.Series, params: dict,
                    post_filter: expr.PostFilterSpec) -> tuple[list[str], int]:
    """(tickers, n_candidates) for one Step-3/4 hop. [] whenever the daynum has no data, no
    elevated group, or the post_filter leaves nothing — a clean no-pick (cash) hop, never an
    error, mirroring strategy_grp v1's contract throughout. n_candidates is the pool size
    before the from_rank/focusset_size window — "how many were available before picking N"."""
    signed = _pool(daynum, dom_table, groups, params, post_filter)
    if signed is None:
        return [], 0
    tickers = pick_by_rank(signed, params["focusset_size"], params["from_rank"])
    return tickers, len(signed)


def production_pick(daynum: int, dom_table: pd.DataFrame, groups: pd.Series, params: dict,
                    post_filter: expr.PostFilterSpec) -> list[str]:
    """The gross list for one day: EVERY member of every elevated group (no per-group cap),
    post_filter applied, sorted best-first by priority_attribute, capped at
    PRODUCTION_GROSS_CAP. Always best-first — from_rank's worst/mid research windows do not
    apply to what a user actually gets shown."""
    elevated = elevated_groups(dom_table, daynum)
    if not elevated:
        return []

    col = str(daynum)
    info = load_longi(f"longi_{params['priority_attribute']}.csv")
    if col not in info.columns:
        return []

    members = elevated_members(elevated, groups)
    all_tickers = [t for tickers in members.values() for t in tickers]
    vals = info.loc[info.index.isin(all_tickers), col].dropna()
    if vals.empty:
        return []

    candidates = vals.index.tolist()
    if post_filter.terms:
        candidates = expr.apply_post_filter(post_filter, daynum, candidates)
        if not candidates:
            return []
        vals = vals.loc[candidates]

    ascending = params["priority_direction"]      # True = small_wins
    return vals.sort_values(ascending=ascending).head(PRODUCTION_GROSS_CAP).index.tolist()


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
    tickers = production_pick(daynum, dom_table, s0.groups, params, s0.post_filter)
    return daynum, tickers, elevated, params, s0
