"""
Rank-window selection — the single place that decides *where in the ranking*
a strategy draws its focusset from.

Every strategy first narrows the universe to a survivor set (via its own filters),
then orders the survivors by longi_rank, where a SMALLER rank value == better.
Historically each strategy took the best n (rank 1..n). `pick_by_rank` generalises
that into a movable window controlled by the `from_rank` parameter, so the same
machinery can test "avoid the top" and "take from the bottom" without touching
each strategy's filter logic.
"""

import pandas as pd


def pick_by_rank(rank_series: pd.Series, n: int, from_rank: int = 1) -> list[str]:
    """
    Pick n tickers from a rank-bearing series (smaller rank == better).

    from_rank semantics (1-based position in the ranking):
        1   -> the best n           (ranks 1..n)            [default, classic top-pick]
        k>1 -> skip the best k-1, take the next n (ranks k..k+n-1)   ["avoid the top"]
        -1  -> the worst n          (whatever ranks sit at the bottom)

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
    ordered = s.sort_values(ascending=True, kind="mergesort")   # best (lowest rank) first

    if from_rank == -1:
        return ordered.index[-n:].tolist()         # the worst n

    if from_rank >= 1:
        start = from_rank - 1                       # 1-based rank -> 0-based offset
        window = ordered.index[start:start + n]
        return window.tolist() if len(window) == n else []

    raise ValueError(f"from_rank must be >= 1 or == -1, got {from_rank}")
