"""
Realizable non-overlapping ADDITIVE chain — the one place the chain math lives.

Used both at report generation (full span) and by best_strategy.py (re-clamped to
a common oldest daynum so chain returns are comparable across strategies). Keeping
it here means the two callers can never drift apart.

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

`laddered_portfolio` is a second, economically distinct estimator over the *same* hops:
instead of one serial position, it models an always-invested book of n = hold/step
staggered tranches and reports the additive return of the blended portfolio. It is a
diagnostic alternative (a trend-following, continuously-deployed investment style), not
the selection metric — best_strategy.py still ranks on the phase-averaged chain.
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


def _filter_usable(rows: Iterable[Tuple[int, float, float]],
                   no_go_threshold: float | None,
                   floor_daynum: int | None,
                   cap_daynum: int | None) -> List[Tuple[int, float]]:
    """(daynum, gain) for hops in [floor, cap] with a real gain that pass the no-go gate.

    The single hop-selection rule shared by realizable_chain and the *_lot_stats
    dispersion helpers, so a chain and its own per-lot statistics can never disagree
    about which hops are investable.
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
    return usable


def realizable_chain(rows: Iterable[Tuple[int, float, float]], hold: int,
                     no_go_threshold: float | None = None,
                     floor_daynum: int | None = None,
                     cap_daynum: int | None = None,
                     phase_average: bool = False) -> Tuple[float, float, int]:
    """
    Additively sum the gains of a non-overlapping chain of hops (spaced >= `hold`).

    rows            : iterable of (daynum, gain_pct, gspc_rsi_prev)
    no_go_threshold : skip a hop when its gspc_rsi_prev is present and < threshold
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


def laddered_portfolio(rows: Iterable[Tuple[int, float, float]], hold: int, step: int,
                       no_go_threshold: float | None = None,
                       floor_daynum: int | None = None,
                       cap_daynum: int | None = None
                       ) -> Tuple[float, float, int, float]:
    """
    Continuously-invested laddered portfolio over the same hops — an alternative to
    realizable_chain, not a replacement.

    Models an always-in book of n = hold // step equal-weight tranches entered `step`
    daynums apart, each held `hold`. Returns are ADDITIVE here too: each sleeve sums the
    gains of its slots (no reinvestment) and the book is the equal-weight mean of the
    sleeve sums. Two deliberate differences from realizable_chain:
      * No phasing loop — the n staggered sleeves ARE the phases, run concurrently, so
        the result is the mean of those sleeves' additive sums. When inv% is 100 and hops
        are uniformly step-spaced the n sleeves ARE the n chain phases, so ladder_ret ==
        chain_ret exactly (mean of sleeve sums == mean of phase totals); but ladder_annual
        usually lands BELOW chain_annual, because the chain divides each phase total by
        that phase's own (ragged, ~hold-shorter) span — a smaller divisor that lifts the
        per-phase annual — while the ladder divides by one consistent full-active-window
        span. On skip days the ladder additionally holds cash (0%) where the chain
        redeploys, so with interior skips ladder_ret < chain_ret too. (Ladder >= chain
        holds only for dense, skip-free strategies like Ranknow.)
      * A no-go (gspc_rsi_prev < threshold) or missing-gain slot is held in CASH (0% for
        that cycle) and the tranche stays on schedule — it does NOT delay re-entry the
        way the serial chain does. This is the always-invested, trend-following posture.

    The clock is anchored to the ACTIVE window — the first to the last *invested* hop.
    Leading/trailing cash (e.g. the pre-signal warm-up daynums a win-prob strategy cannot
    trade, or the most-recent unrealized hops) is trimmed before the span and the invested
    fraction are computed, so both match what realizable_chain measures over its usable
    hops. Without this the span would be padded by the common-span floor/cap and the
    annual figure would divide by phantom cash years (sinking it below the chain annual)
    and inv% would count days the strategy structurally could not act on. Interior cash (genuine
    skip days inside the active window) is kept as 0% so the sleeves stay rigidly staggered.

    rows            : (daynum, gain_pct, gspc_rsi_prev)
    hold            : holding horizon (the `period` param); must be a multiple of step
    step            : entry spacing between tranches
    no_go_threshold : a hop whose gspc_rsi_prev is present and < threshold -> cash (0%)
    floor/cap       : restrict to the common comparison span (as in realizable_chain)

    Returns (total_return_pct, annual_pct, n_sleeves, invested_frac), where total_return
    is the additive mean of the sleeve sums and annual is that / active-window-years (a
    simple average annual gain, NOT a compound CAGR). NaN when the active window is empty
    or `hold` is not a positive multiple of `step`.
    """
    if step <= 0 or hold <= 0 or hold % step != 0:
        return float("nan"), float("nan"), 0, float("nan")
    n = hold // step

    # Collect hops in span; a gated / missing slot becomes cash (0%) but keeps its slot
    # so the tranches stay rigidly staggered. The cash flag is carried so leading/trailing
    # cash can be trimmed below (a real gain of exactly 0.0 must not read as cash).
    hops: List[Tuple[int, float, bool]] = []
    for daynum, gain, gspc in rows:
        dn = int(daynum)
        if floor_daynum is not None and dn < floor_daynum:
            continue
        if cap_daynum is not None and dn > cap_daynum:
            continue
        cash = (no_go_threshold is not None and gspc is not None
                and not pd.isna(gspc) and gspc < no_go_threshold)
        if gain is None or pd.isna(gain):
            cash = True
        hops.append((dn, 0.0 if cash else float(gain), cash))
    if not hops:
        return float("nan"), float("nan"), n, float("nan")
    hops.sort(key=lambda t: t[0])

    # Trim to the active window [first invested, last invested]; interior cash is retained.
    invested_dns = [dn for dn, _g, cash in hops if not cash]
    if not invested_dns:
        return float("nan"), float("nan"), n, float("nan")
    first_dn, last_dn = invested_dns[0], invested_dns[-1]
    hops = [(dn, g) for dn, g, _cash in hops if first_dn <= dn <= last_dn]
    invested = len(invested_dns)

    # Assign each hop to a sleeve by its step-slot modulo n; SUM gains within the sleeve.
    sleeve_sum: dict[int, float] = {}
    for dn, g in hops:
        phase = round((dn - first_dn) / step) % n
        sleeve_sum[phase] = sleeve_sum.get(phase, 0.0) + g

    # Equal-weight additive blend; an absent sleeve contributes 0.0 (idle cash all span).
    blended = sum(sleeve_sum.get(p, 0.0) for p in range(n)) / n
    total_ret = blended
    span_daynums = (last_dn + hold) - first_dn
    years = span_daynums / _TRADING_DAYS_YEAR
    annual = total_ret / years if years > 0 else float("nan")
    return total_ret, annual, n, invested / len(hops)


# ---------------------------------------------------------------------------
# Per-investment dispersion (avg gain / worst / loss count) over the SAME hops the
# return estimators use. Kept here so the dispersion of a chain and of a ladder are
# each measured over exactly that estimator's investment set — never copied between
# the two (the chain holds ~hold/step times fewer positions than the ladder).
# ---------------------------------------------------------------------------

def chain_lot_stats(rows: Iterable[Tuple[int, float, float]], hold: int,
                    no_go_threshold: float | None = None,
                    floor_daynum: int | None = None,
                    cap_daynum: int | None = None,
                    phase_average: bool = True) -> Tuple[float, float, int]:
    """Per-lot dispersion of the realizable chain over its non-overlapping lots.

    Phase-averaged like realizable_chain: each start offset yields one chain; we report
    the mean of per-chain (mean gain), the mean of per-chain (worst lot), and the
    rounded mean of per-chain (loss count) — i.e. typical behaviour of one realized
    chain of ~chain_n lots, NOT of the full hop population.

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
            sum(worsts) / len(worsts),
            round(sum(nlosses) / len(nlosses)))


def chain_inv_pct(rows: Iterable[Tuple[int, float, float]], hold: int,
                  no_go_threshold: float | None = None,
                  floor_daynum: int | None = None,
                  cap_daynum: int | None = None,
                  phase_average: bool = True) -> float:
    """Share of the chain's active span actually held in a position (%) — the chain's
    analog of ladder_inv%.

    The serial chain takes the next usable hop once the previous lot closes. A slot that
    is gated (No_go: gspc_rsi_prev < threshold) or unfillable (too few survivors to reach
    focusset_size -> NaN gain) is dropped by _filter_usable, so when no usable hop exists
    at the reinvest point (prev_lot + hold) the chain idles in cash until a later one
    appears. inv% = invested days / active-span days = chain_n*hold / ((last+hold)-first),
    phase-averaged. 100% when lots are exactly hold-spaced; lower when No_go / too-few-
    survivors force idle gaps longer than the spacing the chain would otherwise keep.
    Usually sits ABOVE ladder_inv% — the chain only needs one usable day per `hold`, so it
    shrugs off scattered gating the always-every-slot ladder eats. NaN when no hop qualifies.
    """
    usable = _filter_usable(rows, no_go_threshold, floor_daynum, cap_daynum)
    if not usable:
        return float("nan")
    if phase_average:
        first_dn = usable[0][0]
        starts = [i for i, (dn, _g) in enumerate(usable) if dn < first_dn + hold]
    else:
        starts = [0]

    invs: List[float] = []
    for si in starts:
        chain = _greedy_from(usable, si, hold)
        if not chain:
            continue
        span = (chain[-1][0] + hold) - chain[0][0]
        if span > 0:
            invs.append(min(1.0, len(chain) * hold / span) * 100.0)
    return sum(invs) / len(invs) if invs else float("nan")


def laddered_lot_stats(rows: Iterable[Tuple[int, float, float]],
                       no_go_threshold: float | None = None,
                       floor_daynum: int | None = None,
                       cap_daynum: int | None = None
                       ) -> Tuple[float, float, int, int]:
    """Per-investment dispersion of the ladder over every invested hop in the span.

    The ladder buys at every hop, so this is the whole investable population (cash /
    no-go slots are not investments and are excluded). Returns (avg_gain_pct,
    worst_pct, n_loss, n_invested) — n_invested is the ladder's total investment count.
    """
    gains = [g for _dn, g in _filter_usable(
        rows, no_go_threshold, floor_daynum, cap_daynum)]
    if not gains:
        return float("nan"), float("nan"), 0, 0
    return (sum(gains) / len(gains),
            min(gains),
            sum(1 for g in gains if g < 0),
            len(gains))
