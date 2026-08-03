"""
Step 1 — group dominance, levels A / B / C.

Generalizes strategy_grp v1's shared/dominance.py: the group key comes from Step 0's
resolved `groups` Series (any Stamdata expression, not a fixed column name), and the
qualifying-ticker threshold is RELATIVE to each group's own size — see DesignVersion2.md's
"Refinements agreed during implementation" (dom_count_min, board-driven; dom_count_frac,
NOT board-driven — derived from dominance_decile, see shared.config.DOM_COUNT_FRAC_MARGIN).
Levels A/B/C replace v1's dom_now/dom_20d/dom_50d naming (today / persistent-over-a-trailing-
window), per SM's design; only the ONE table a row's own `level` needs is computed.
"""

from __future__ import annotations

import math

import pandas as pd

from shared.config import DOM_COUNT_FRAC_MARGIN
from shared.data_loader import load_longi

_DEFAULT_WINDOW: dict[str, int] = {"B": 20, "C": 50}


def daily_decile_cutoff(signal: pd.DataFrame, decile: float, direction: bool) -> pd.Series:
    """Per-daynum quantile of signal's cross-sectional distribution — every ticker, that
    day only, computed independently day by day (not across history). Scale-free: the
    same `decile` fraction means "best decile" whatever the attribute's raw range.

    direction=True  (smaller wins, e.g. rank): low quantile  (0.10 -> 10th percentile)
    direction=False (bigger wins):              high quantile (0.10 -> 90th percentile)
    """
    q = decile if direction else 1 - decile
    return signal.quantile(q, axis=0)


def dom_count_threshold(group_size: int, dom_count_min: int, dom_count_frac: float) -> int:
    """threshold = max(dom_count_min, ceil(dom_count_frac * group_size))."""
    return max(dom_count_min, math.ceil(dom_count_frac * group_size))


def group_dominance_now(groups: pd.Series, dominance_attribute: str, dominance_direction: bool,
                        dominance_decile: float, dom_count_min: int
                        ) -> tuple[pd.DataFrame, pd.Series]:
    """group-key x daynum boolean: True where the group has >= its own (size-relative)
    qualifying-ticker threshold beating that day's own best-decile cutoff. Also returns
    the per-daynum cutoff Series (Step 1's day-by-day threshold, for reporting).

    dom_count_frac is not a caller-supplied parameter: a group only counts as dominant when
    over-represented among today's qualifiers relative to the population base rate
    (dominance_decile IS that base rate), so it is always dominance_decile + a fixed margin —
    see shared.config.DOM_COUNT_FRAC_MARGIN."""
    signal = load_longi(f"longi_{dominance_attribute}.csv")
    cutoffs = daily_decile_cutoff(signal, dominance_decile, dominance_direction)
    common = signal.index.intersection(groups.index)
    vals = signal.loc[common]
    qualifying = vals.lt(cutoffs) if dominance_direction else vals.gt(cutoffs)
    group_keys = groups.loc[common]
    counts = qualifying.groupby(group_keys).sum()
    group_sizes = group_keys.value_counts()
    dom_count_frac = dominance_decile + DOM_COUNT_FRAC_MARGIN
    thresholds = group_sizes.reindex(counts.index).apply(
        lambda n: dom_count_threshold(int(n), dom_count_min, dom_count_frac)
    )
    dom_now = counts.ge(thresholds, axis=0)
    return dom_now, cutoffs


def add_persistence(dom_now: pd.DataFrame, window: int, frac_threshold: float) -> pd.DataFrame:
    """Trailing persistence: True where dom_now held on at least frac_threshold of the
    `window` daynums ending at (and including) that daynum.

    Data-format gotcha: Longi columns are newest-left (highest daynum first); re-sort
    ascending by daynum before pandas' trailing `.rolling()`, then restore the original
    newest-left column order."""
    ascending_cols = sorted(dom_now.columns, key=int)
    ascending = dom_now[ascending_cols]
    frac = ascending.T.rolling(window, min_periods=window).mean().T
    return (frac >= frac_threshold)[dom_now.columns]


def resolve_dom_table(groups: pd.Series, params: dict) -> tuple[pd.DataFrame, pd.Series]:
    """The ONE dominance table this row's `level` (A/B/C) needs, plus the per-daynum
    dominance cutoff Series (level-independent — persistence is derived from dom_now, not
    from the cutoff itself)."""
    dom_now, cutoffs = group_dominance_now(
        groups,
        params["dominance_attribute"], params["dominance_direction"],
        params["dominance_decile"], params["dom_count_min"],
    )
    level = params["level"]
    if level == "A":
        return dom_now, cutoffs
    window = params.get("persistence_window") or _DEFAULT_WINDOW[level]
    return add_persistence(dom_now, window, params["persistence_frac"]), cutoffs


def elevated_groups(dom_table: pd.DataFrame, daynum: int) -> list[str]:
    """Group keys elevated ("dominating") at one daynum. [] when the daynum has no column
    or no group qualifies — a clean no-pick hop, never an error."""
    col = str(daynum)
    if col not in dom_table.columns:
        return []
    return dom_table.index[dom_table[col].fillna(False)].tolist()


def elevated_members(group_keys: list[str], groups: pd.Series) -> dict[str, list[str]]:
    """group key -> member tickers, restricted to the elevated groups passed in."""
    return {key: groups.index[groups == key].tolist() for key in group_keys}
