"""
Realizable non-overlapping ADDITIVE chain — the one place the chain math lives.

Used by step3_backtest.py at report generation (full span, re-clamped to a common
oldest daynum so chain returns are comparable across strategies).

Returns are ADDITIVE, not compounded: each lot bets the same fixed capital and the
gain is withdrawn (not reinvested), so the chain's total return is the simple SUM of
its lot gains (Sigma g_i), and the annualized figure is that sum divided by the span
in years — a plain average annual gain, NOT a compound growth rate. This deliberately
avoids the exponential blow-up a compounded backtest produces over a long history
(reinvested gains stacking into absurd multiples); the additive total grows only
linearly with the number of lots.

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


def _additive(chain: List[Tuple[int, float]], hold: int) -> Tuple[float, float]:
    """Total ADDITIVE return % and simple annual gain % for one chain of hops.

    Gains are summed (fixed capital per lot, gain withdrawn), not compounded:
      total_ret = sum(g_i)               -- linear in the number of lots
      annual    = total_ret / years      -- plain average annual gain, NOT a CAGR
    """
    total_ret = sum(g for _dn, g in chain)
    span_daynums = (chain[-1][0] + hold) - chain[0][0]
    years = span_daynums / _TRADING_DAYS_YEAR
    annual = total_ret / years if years > 0 else float("nan")
    return total_ret, annual


def _greedy_from(usable: List[tuple], start_idx: int, hold: int) -> List[tuple]:
    """Greedy non-overlapping pick starting at usable[start_idx], spaced >= hold.

    Indexes only element 0 (the daynum), so it works unchanged on the (daynum, gain)
    pairs from _filter_usable and the (daynum, gain, extras) triples from
    _filter_usable_ext — one selection rule, whatever payload rides along.
    """
    chain: List[tuple] = []
    next_allowed: int | None = None
    for item in usable[start_idx:]:
        dn = item[0]
        if next_allowed is None or dn >= next_allowed:
            chain.append(item)
            next_allowed = dn + hold
    return chain


def _filter_usable_ext(rows: Iterable[tuple],
                       no_go_threshold: float | None,
                       floor_daynum: int | None,
                       cap_daynum: int | None) -> List[Tuple[int, float, tuple]]:
    """(daynum, gain, extras) for hops in [floor, cap] with a real gain that pass the
    no-go gate. Anything after gspc_rsi in a row rides along untouched in `extras`.

    THE single hop-selection rule for this module. _filter_usable wraps it, so the chain
    and its per-lot dispersion can never disagree about which hops are investable —
    adding a metric must never fork this rule.
    """
    usable: List[Tuple[int, float, tuple]] = []
    for row in rows:
        daynum, gain, gspc = row[0], row[1], row[2]
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
        usable.append((dn, float(gain), tuple(row[3:])))
    usable.sort(key=lambda t: t[0])
    return usable


def _filter_usable(rows: Iterable[Tuple[int, float, float]],
                   no_go_threshold: float | None,
                   floor_daynum: int | None,
                   cap_daynum: int | None) -> List[Tuple[int, float]]:
    """(daynum, gain) for investable hops — the payload-free view of _filter_usable_ext."""
    return [(dn, g) for dn, g, _x in
            _filter_usable_ext(rows, no_go_threshold, floor_daynum, cap_daynum)]


def realizable_chain(rows: Iterable[Tuple[int, float, float]], hold: int,
                     no_go_threshold: float | None = None,
                     floor_daynum: int | None = None,
                     cap_daynum: int | None = None,
                     phase_average: bool = False) -> Tuple[float, float, int]:
    """
    Additively sum the gains of a non-overlapping chain of hops (spaced >= `hold`).

    rows            : iterable of (daynum, gain_pct, gspc_rsi)
    no_go_threshold : skip a hop when its gspc_rsi is present and < threshold
    floor_daynum    : ignore hops older than this (the common comparison floor)
    cap_daynum      : ignore hops newer than this (the common comparison cap)
    phase_average   : average over every start offset in the first holding window,
                      removing sensitivity to the anchor (recommended for comparison)

    Returns (total_return_pct, annual_pct, n_trades), where total_return is the SUM of
    lot gains (additive, no reinvestment) and annual is that sum / span-years (a simple
    average annual gain, NOT a compound CAGR) — averaged across phases when
    phase_average is set. NaN/0 when no hop qualifies.
    """
    usable = _filter_usable(rows, no_go_threshold, floor_daynum, cap_daynum)
    if not usable:
        return float("nan"), float("nan"), 0

    if phase_average:
        first_dn = usable[0][0]
        starts = [i for i, (dn, _g) in enumerate(usable) if dn < first_dn + hold]
    else:
        starts = [0]

    totals: List[float] = []
    annuals: List[float] = []
    ns: List[int] = []
    for si in starts:
        chain = _greedy_from(usable, si, hold)
        if not chain:
            continue
        t, a = _additive(chain, hold)
        totals.append(t)
        annuals.append(a)
        ns.append(len(chain))
    if not totals:
        return float("nan"), float("nan"), 0

    avg_total = sum(totals) / len(totals)
    valid_annual = [a for a in annuals if not pd.isna(a)]
    avg_annual = sum(valid_annual) / len(valid_annual) if valid_annual else float("nan")
    avg_n = round(sum(ns) / len(ns))
    return avg_total, avg_annual, avg_n


# ---------------------------------------------------------------------------
# Per-investment dispersion (avg gain / worst / loss count) over the SAME hops
# realizable_chain uses, so the two can never disagree about which hops are investable.
# ---------------------------------------------------------------------------

def chain_lot_stats(rows: Iterable[Tuple[int, float, float]], hold: int,
                    no_go_threshold: float | None = None,
                    floor_daynum: int | None = None,
                    cap_daynum: int | None = None,
                    phase_average: bool = True) -> Tuple[float, float, int]:
    """Per-lot dispersion of the realizable chain over its non-overlapping lots.

    Origin-averaged over start offsets like realizable_chain, but `worst` and `n_loss` are a
    coherent WORST-CASE PAIR, not independent averages. `avg_gain` stays the origin-mean of
    per-origin mean lot gain (a central tendency, where averaging is meaningful), while:
      * `worst`  = the single lowest lot across ALL origins — the worst day any user could
                   hit, whatever day they start hopping;
      * `n_loss` = the MOST losing lots in any one origin's realized chain (max, not mean).

    Averaging an *extreme* (min) independently from a *count* (loss tally) is what let the two
    disagree in either direction — the "Worst=+0.37 yet N_loss=1" contradiction (mean-of-minima
    positive while some origins still lose) and its mirror. Taking worst = min-over-origins and
    n_loss = max-over-origins makes them a genuine worst case, guaranteeing
    `worst < 0  <=>  n_loss >= 1` (a losing lot exists iff some origin's chain counts one).

    Returns (avg_gain_pct, worst_pct, n_loss). NaN/0 when no hop qualifies.
    """
    usable = _filter_usable(rows, no_go_threshold, floor_daynum, cap_daynum)
    if not usable:
        return float("nan"), float("nan"), 0
    if phase_average:
        first_dn = usable[0][0]
        starts = [i for i, (dn, _g) in enumerate(usable) if dn < first_dn + hold]
    else:
        starts = [0]

    means: List[float] = []
    worsts: List[float] = []
    nlosses: List[int] = []
    for si in starts:
        gains = [g for _dn, g in _greedy_from(usable, si, hold)]
        if not gains:
            continue
        means.append(sum(gains) / len(gains))
        worsts.append(min(gains))
        nlosses.append(sum(1 for g in gains if g < 0))
    if not means:
        return float("nan"), float("nan"), 0
    return (sum(means) / len(means),
            min(worsts),      # worst single lot any user could hit, across all origins
            max(nlosses))     # most losers in any one origin's chain (pairs with worst)


def chain_origin_sensitivity(rows: Iterable[Tuple[int, float, float]], hold: int,
                             no_go_threshold: float | None = None,
                             floor_daynum: int | None = None,
                             cap_daynum: int | None = None,
                             phase_average: bool = True) -> float:
    """How much the chain's annual return swings with the start origin, as a percentage.

    Origin-averaging (realizable_chain's phase_average) exists precisely because a single
    greedy chain is anchor-sensitive — the annual return depends on which day you start. This
    reports that sensitivity directly: run the chain from every start offset in the first
    holding window (the same origin set realizable_chain averages), take each origin's annual
    via _additive, and return the spread (max - min) / |mean| * 100.

    LOWER is better: a small spread means the strategy pays about the same regardless of when
    a user jumps on the hopping — a robust, desirable property. NaN when fewer than two origins
    exist (spread undefined) or the mean annual is ~0.
    """
    usable = _filter_usable(rows, no_go_threshold, floor_daynum, cap_daynum)
    if not usable:
        return float("nan")
    if phase_average:
        first_dn = usable[0][0]
        starts = [i for i, (dn, _g) in enumerate(usable) if dn < first_dn + hold]
    else:
        starts = [0]

    annuals: List[float] = []
    for si in starts:
        chain = _greedy_from(usable, si, hold)
        if not chain:
            continue
        _t, a = _additive(chain, hold)
        if not pd.isna(a):
            annuals.append(a)
    if len(annuals) < 2:
        return float("nan")
    mean = sum(annuals) / len(annuals)
    if abs(mean) < 1e-9:
        return float("nan")
    return (max(annuals) - min(annuals)) / abs(mean) * 100.0
