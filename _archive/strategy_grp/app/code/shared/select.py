"""
Rank-window selection — the single place that decides whether a strategy draws its
focusset from the top or the bottom of its ranking.

Every strategy first narrows the universe to a survivor set (via its own filters),
then orders the survivors by SOME attribute, pre-oriented so a SMALLER value == better
(callers negate a bigger-is-better series before handing it here — see
shared.engine._Ranker / shared.dominance.select_focusset). `pick_by_rank` picks the
best or the worst n of that ordering via the `from_rank` parameter.
"""

import pandas as pd


def pick_by_rank(rank_series: pd.Series, n: int, from_rank: int = 1) -> list[str]:
    """
    Pick n tickers from a rank-bearing series (smaller value == better).

    from_rank:
        1  -> the best n   (lowest-valued)   [default]
        -1 -> the worst n  (highest-valued)

    Returns [] when the requested window cannot be filled with n tickers, so a hop
    that cannot be served stays a clean no-pick (cash) day — exactly the contract
    the callers already relied on.
    """
    s = rank_series.dropna()
    if len(s) < n:
        return []
    # Stable sort so ties resolve by original order — this makes from_rank=1
    # byte-identical to the historical `nsmallest(n)` (keep="first") and keeps
    # the whole window deterministic across pandas versions.
    ordered = s.sort_values(ascending=True, kind="mergesort")   # best (lowest value) first

    if from_rank == -1:
        return ordered.index[-n:].tolist()         # the worst n

    if from_rank == 1:
        return ordered.index[:n].tolist()           # the best n

    raise ValueError(f"from_rank must be 1 or -1, got {from_rank}")
