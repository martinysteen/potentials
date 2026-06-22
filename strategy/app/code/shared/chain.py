"""
Realizable non-overlapping compounded chain — the one place the chain math lives.

Used both at report generation (full span) and by best_strategy.py (re-clamped to
a common oldest daynum so chain returns are comparable across strategies). Keeping
it here means the two callers can never drift apart.

A single greedy chain is anchored at the oldest hop and steps +hold, so its result
swings wildly with the exact start day (which hop it lands on). `phase_average=True`
removes that fragility: it runs the chain from every possible start offset inside the
first holding window and averages — i.e. the expected realizable return regardless of
which day you happen to begin trading.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

import pandas as pd

_TRADING_DAYS_YEAR = 252


def _compound(chain: List[Tuple[int, float]], hold: int) -> Tuple[float, float]:
    """Total compounded return % and annualized CAGR % for one chain of hops."""
    growth = 1.0
    for _dn, g in chain:
        growth *= (1.0 + g / 100.0)
    total_ret = (growth - 1.0) * 100.0
    span_daynums = (chain[-1][0] + hold) - chain[0][0]
    years = span_daynums / _TRADING_DAYS_YEAR
    cagr = ((growth ** (1.0 / years) - 1.0) * 100.0
            if years > 0 and growth > 0 else float("nan"))
    return total_ret, cagr


def _greedy_from(usable: List[Tuple[int, float]], start_idx: int,
                 hold: int) -> List[Tuple[int, float]]:
    """Greedy non-overlapping pick starting at usable[start_idx], spaced >= hold."""
    chain: List[Tuple[int, float]] = []
    next_allowed: int | None = None
    for dn, g in usable[start_idx:]:
        if next_allowed is None or dn >= next_allowed:
            chain.append((dn, g))
            next_allowed = dn + hold
    return chain


def realizable_chain(rows: Iterable[Tuple[int, float, float]], hold: int,
                     no_go_threshold: float | None = None,
                     floor_daynum: int | None = None,
                     cap_daynum: int | None = None,
                     phase_average: bool = False) -> Tuple[float, float, int]:
    """
    Compound the gains of a non-overlapping chain of hops (spaced >= `hold` daynums).

    rows            : iterable of (daynum, gain_pct, gspc_rsi_prev)
    no_go_threshold : skip a hop when its gspc_rsi_prev is present and < threshold
    floor_daynum    : ignore hops older than this (the common comparison floor)
    cap_daynum      : ignore hops newer than this (the common comparison cap)
    phase_average   : average over every start offset in the first holding window,
                      removing sensitivity to the anchor (recommended for comparison)

    Returns (total_return_pct, cagr_pct, n_trades) — averaged across phases when
    phase_average is set. NaN/0 when no hop qualifies.
    """
    usable: List[Tuple[int, float]] = []
    for daynum, gain, gspc in rows:
        dn = int(daynum)
        if floor_daynum is not None and dn < floor_daynum:
            continue
        if cap_daynum is not None and dn > cap_daynum:
            continue
        if (no_go_threshold is not None and gspc is not None
                and not pd.isna(gspc) and gspc < no_go_threshold):
            continue
        if gain is None or pd.isna(gain):
            continue
        usable.append((dn, float(gain)))
    usable.sort(key=lambda t: t[0])
    if not usable:
        return float("nan"), float("nan"), 0

    if phase_average:
        first_dn = usable[0][0]
        starts = [i for i, (dn, _g) in enumerate(usable) if dn < first_dn + hold]
    else:
        starts = [0]

    totals: List[float] = []
    cagrs: List[float] = []
    ns: List[int] = []
    for si in starts:
        chain = _greedy_from(usable, si, hold)
        if not chain:
            continue
        t, c = _compound(chain, hold)
        totals.append(t)
        cagrs.append(c)
        ns.append(len(chain))
    if not totals:
        return float("nan"), float("nan"), 0

    avg_total = sum(totals) / len(totals)
    valid_cagr = [c for c in cagrs if not pd.isna(c)]
    avg_cagr = sum(valid_cagr) / len(valid_cagr) if valid_cagr else float("nan")
    avg_n = round(sum(ns) / len(ns))
    return avg_total, avg_cagr, avg_n
