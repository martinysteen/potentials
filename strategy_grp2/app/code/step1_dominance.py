"""
Step 1 — group dominance, levels A / B / C.

Generalizes strategy_grp v1's shared/dominance.py: the group key comes from Step 0's
resolved `groups` Series (any Stamdata expression, not a fixed column name). The
qualifying-ticker COUNT threshold is `dom_count_min` for a group at or above
`2 * dom_count_min` members; below that it is HALVED relative to the group's own size
(`group_size / 2`, decimals kept, no rounding) rather than raised — SM's original
prototype rule, restored 2026-08-05 after a 2026-08-03 refinement replaced it with a
size-INCREASING formula that inverted the intent (see DesignVersion2.md's 2026-08-05
correction). `dominance_decile` is unrelated to this threshold — it only decides which
INDIVIDUAL tickers qualify as "elite" that day (`daily_decile_cutoff`); how many of them
a group needs is `dom_count_min` alone.
Levels A/B/C replace v1's dom_now/dom_20d/dom_50d naming (today / persistent-over-a-trailing-
window), per SM's design; only the ONE table a row's own `level` needs is computed.
"""

from __future__ import annotations

import pandas as pd

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


def dom_count_threshold(group_size: int, dom_count_min: int) -> float:
    """threshold = dom_count_min for a group at/above 2*dom_count_min members; below that,
    HALF the group's own size (decimals kept -- an 8-member group needs 4.0, a 9-member
    group needs 4.5, so 5 qualifiers clear it and 4 do not; no ceil/round is applied since
    the >= comparison against an integer count already resolves it).

    Equivalent to min(dom_count_min, group_size / 2) -- the two branches agree exactly at
    the group_size == 2*dom_count_min boundary, so there is no discontinuity there. SM's
    original design: a big sector needs a real, size-independent headcount of qualifiers
    to count as dominant; a small sector needs proportionally FEWER, not more, since it
    has fewer members to draw qualifiers from in the first place. This is the opposite
    direction from the 2026-08-03 formula it replaces, which raised the bar for LARGE
    groups (and excluded e.g. a 227-member GICS sector with 34 qualifiers while admitting
    a 201-member one with 31) -- see DesignVersion2.md's 2026-08-05 correction."""
    if group_size >= 2 * dom_count_min:
        return float(dom_count_min)
    return group_size / 2


def group_dominance_now(groups: pd.Series, dominance_attribute: str, dominance_direction: bool,
                        dominance_decile: float, dom_count_min: int
                        ) -> tuple[pd.DataFrame, pd.Series]:
    """group-key x daynum boolean: True where the group has >= its own qualifying-ticker
    threshold (dom_count_threshold — dom_count_min flat, halved for a small group) of
    tickers beating that day's own best-decile cutoff. Also returns the per-daynum cutoff
    Series (Step 1's day-by-day threshold, for reporting).

    Two independent decisions, deliberately not entangled (SM's original design, restored
    2026-08-05): dominance_decile decides which INDIVIDUAL tickers count as "elite" today;
    dom_count_min decides how MANY of them a group needs to count as "dominant". Neither
    parameter derives the other."""
    signal = load_longi(f"longi_{dominance_attribute}.csv")
    cutoffs = daily_decile_cutoff(signal, dominance_decile, dominance_direction)
    common = signal.index.intersection(groups.index)
    vals = signal.loc[common]
    qualifying = vals.lt(cutoffs) if dominance_direction else vals.gt(cutoffs)
    group_keys = groups.loc[common]
    counts = qualifying.groupby(group_keys).sum()
    group_sizes = group_keys.value_counts()
    thresholds = group_sizes.reindex(counts.index).apply(
        lambda n: dom_count_threshold(int(n), dom_count_min)
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


def elite_members(groups: pd.Series, dominance_attribute: str, dominance_direction: bool,
                  dominance_decile: float, daynum: int) -> dict[str, list[str]]:
    """group key -> ELITE tickers only (those that individually cleared today's decile
    cutoff — the same per-ticker test group_dominance_now sums into its per-group
    `counts`), best-first within each group. For reporting the actual roster behind an
    elevated group's count, not its gross membership (SM, 2026-08-05: "I am absolutely
    not interested in gross members but a list of elite members").

    Uses the SAME daily_decile_cutoff() as group_dominance_now, so a ticker counted here
    is exactly a ticker counted there — no separate definition of "elite" to drift out of
    sync. [] when the daynum has no column."""
    signal = load_longi(f"longi_{dominance_attribute}.csv")
    col = str(daynum)
    if col not in signal.columns:
        return {}
    cutoff = daily_decile_cutoff(signal, dominance_decile, dominance_direction)[col]
    common = signal.index.intersection(groups.index)
    vals = signal.loc[common, col].dropna()
    qualifying = vals[vals.lt(cutoff) if dominance_direction else vals.gt(cutoff)]
    qualifying = qualifying.sort_values(ascending=dominance_direction)   # best-first

    out: dict[str, list[str]] = {}
    for t in qualifying.index:
        out.setdefault(str(groups.loc[t]), []).append(t)
    return out
