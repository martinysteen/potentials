"""
Rank-window selection — the single place that decides which slice of a ranking a run
draws its focusset from.

Every caller first narrows the universe to a candidate set, then orders it by SOME
attribute, pre-oriented so a SMALLER value == better (negate a bigger-is-better series
before calling this — see step2_focusset.select_focusset). `pick_by_rank` then takes the
window named by `from_rank`, which arrives already parsed by
`param_spec.parse_from_rank` — one of:

    ("edge", 1)        the best n     (v1 default)
    ("edge", -1)        the worst n
    ("offset", k)       fixed offset, integer k >= 2 — "skip the top k-1"
    ("quantile", f)     n centred at quantile f of the pool, 0 < f < 1 ("mid" == 0.5)

Two different empty-window contracts, deliberately (see DesignVersion2.md's
"Refinements agreed during implementation"): "edge"/"offset" are ABSOLUTE positions in the
ranking and return [] when the pool can't fill the requested window (a clean cash hop,
matching v1's behaviour exactly for edge/offset). "quantile" is POOL-RELATIVE by
construction — the window is defined as a fraction of whatever pool size N is — so it always
exists once N >= n; it CLAMPS to the pool rather than ever returning [].
"""

import pandas as pd

FromRank = tuple[str, int | float]


def pick_by_rank(rank_series: pd.Series, n: int, from_rank: FromRank) -> list[str]:
    """
    Pick n tickers from a rank-bearing series (smaller value == better).

    `from_rank` must already be parsed (see param_spec.parse_from_rank) — this function
    does not accept a bare int/str, since the parse step is what turns 1 vs "mid" vs an
    ordinary offset into an unambiguous instruction.
    """
    s = rank_series.dropna()
    n_pool = len(s)
    if n_pool < n:
        return []
    # Stable sort so ties resolve by original order — keeps ("edge", 1) byte-identical to
    # the historical `nsmallest(n)` (keep="first") and the whole window deterministic
    # across pandas versions.
    ordered = s.sort_values(ascending=True, kind="mergesort")   # best (lowest value) first

    kind, value = from_rank

    if kind == "edge":
        if value == 1:
            return ordered.index[:n].tolist()
        if value == -1:
            return ordered.index[-n:].tolist()
        raise ValueError(f"from_rank edge value must be 1 or -1, got {value!r}")

    if kind == "offset":
        start = int(value) - 1                      # 1-indexed rank -> 0-indexed position
        if start < 0:
            raise ValueError(f"from_rank offset must be >= 2, got {value!r}")
        if start + n > n_pool:
            return []                                # the fixed window doesn't fit — cash hop
        return ordered.index[start:start + n].tolist()

    if kind == "quantile":
        f = float(value)
        if not 0.0 < f < 1.0:
            raise ValueError(f"from_rank quantile must be in (0,1), got {value!r}")
        start = round(f * n_pool - n / 2)
        start = max(0, min(start, n_pool - n))       # clamp — always fits since n_pool >= n
        return ordered.index[start:start + n].tolist()

    raise ValueError(f"unknown from_rank kind {kind!r}")
