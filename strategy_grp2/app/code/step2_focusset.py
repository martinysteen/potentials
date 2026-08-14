"""
Step 2 — filtering and sorting. Two distinct outputs share Step 1's elevated groups:

  select_focusset() — Step 3/4's fixed, comparable per-hop TEST SAMPLE: each group's pool
  capped to tickers_per_group, then the from_rank/focusset_size window. Backtest metrics
  need a stable sample size across hundreds of hops; this is that knob, board-driven.

  production_pick() — the actual gross list a user sees (StrategicStocks.xlsx,
  Step1_groups/Step2_picks): EACH currently-elevated group's own top `tickers_per_group`
  by priority_attribute, unconditionally included (SM, 2026-08-05 — restoring the board's
  stated intent, "3 picked from each"). Not a global top-N pool: a genuinely dominant
  group is never shut out by another group's stronger candidates. from_rank/focusset_size
  still do not apply here — production always wants each group's best end of the ranking,
  never a deliberately worst/mid research window.
"""

from __future__ import annotations

import pandas as pd

from shared.data_loader import load_longi
from shared.select import pick_by_rank
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
    """The gross list for one day: EACH elevated group's own top `tickers_per_group` by
    priority_attribute, unconditionally included — total is num_elevated_groups *
    tickers_per_group (or less, when a group has fewer qualifying members than that), never
    truncated by competition against another elevated group's stronger candidates.

    Restored 2026-08-05 (SM): the prior rule (2026-08-03) pooled every elevated group's
    FULL membership and kept only the global top `shared.config.PRODUCTION_GROSS_CAP` by
    priority_attribute — meant to stop a small dominant group losing candidates to an
    arbitrary per-group pre-cut, but its actual effect was the opposite of the point of
    calling a group "dominant": a genuinely elevated group could get ZERO production picks
    if its tickers didn't rank well globally (live evidence: Basi, one of 5 elevated GICS
    sectors, got none against Tech/Fina/Indu). `tickers_per_group` is the board's own
    stated per-group intent ("we have specified... that we want 3 picked from each") and
    now governs this the same way it already governs Step 3/4's select_focusset() pool —
    same per-group-cap-then-post_filter order as `_pool()` above, for consistency.

    Always best-first per group — from_rank's worst/mid research windows do not apply to
    what a user actually gets shown."""
    elevated = elevated_groups(dom_table, daynum)
    if not elevated:
        return []

    col = str(daynum)
    info = load_longi(f"longi_{params['priority_attribute']}.csv")
    if col not in info.columns:
        return []

    ascending = params["priority_direction"]      # True = small_wins
    members = elevated_members(elevated, groups)
    pools: list[pd.Series] = []
    for tickers in members.values():
        vals = info.loc[info.index.isin(tickers), col].dropna()
        if vals.empty:
            continue
        pools.append(vals.sort_values(ascending=ascending).head(params["tickers_per_group"]))
    if not pools:
        return []
    pooled = pd.concat(pools)

    candidates = pooled.index.tolist()
    if post_filter.terms:
        candidates = expr.apply_post_filter(post_filter, daynum, candidates)
        if not candidates:
            return []
        pooled = pooled.loc[candidates]

    return pooled.sort_values(ascending=ascending).index.tolist()


def _resolve_history(row_resolved: dict):
    """(step0_result, dom_table, params) — the Step-0/1 resolution shared by current_pick
    (newest daynum only) and pick_history (every daynum). Raises ValueError if no group
    ever dominates with this row's Step-1 parameters."""
    s0 = step0_data.resolve_step0(row_resolved)
    params = dict(row_resolved)
    params["dominance_attribute"] = s0.dominance_attribute
    params["priority_attribute"] = s0.priority_attribute

    dom_table, _cutoffs = step1_dominance.resolve_dom_table(s0.groups, params)
    if dom_table.empty:
        raise ValueError("no group ever dominates with this row's Step-1 parameters")
    return s0, dom_table, params


def current_pick(row_resolved: dict):
    """(daynum, tickers, elevated_groups, params, step0_result) for the CURRENT (newest)
    daynum — what production ships (StrategicStocks.xlsx) and what the output board's
    Runs/Step1_groups/Step2_picks sheets show. Raises ValueError if no group ever
    dominates with this row's Step-1 parameters."""
    s0, dom_table, params = _resolve_history(row_resolved)
    daynum = max(int(c) for c in dom_table.columns)
    elevated = step1_dominance.elevated_groups(dom_table, daynum)
    tickers = production_pick(daynum, dom_table, s0.groups, params, s0.post_filter)
    return daynum, tickers, elevated, params, s0


def pick_history(row_resolved: dict) -> tuple["step0_data.Step0Result", dict[int, list[str]]]:
    """(step0_result, {daynum: tickers}) — production_pick() run across EVERY daynum this
    row's dominance table covers (~650), not just the newest (SM, 2026-08-13: "a similar
    list must be pulled on any other of the time line"). tickers is [] for a daynum with no
    elevated group, same clean-no-pick convention as production_pick/current_pick.

    Development-tick only (feeds picks_<daynum>.csv) — never called by --production, which
    only ever needs the one newest-daynum pick current_pick gives it."""
    s0, dom_table, params = _resolve_history(row_resolved)
    history: dict[int, list[str]] = {}
    for col in dom_table.columns:
        daynum = int(col)
        history[daynum] = production_pick(daynum, dom_table, s0.groups, params, s0.post_filter)
    return s0, history
