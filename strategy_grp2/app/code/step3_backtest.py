"""
Step 3 — backtest: one FUSED timeline per row, 1-day hops only (`step` is fixed at 1 —
DesignVersion2.md rejects chained/overlapping hops as obscuring a strategy's fundamental
characteristics). Older hops use REALIZED forward gain (longi_future_per<period>d.csv);
the trailing ~period hops, whose horizon has not closed yet, use partial price return —
what strategy_grp v1 called its "extension" — flagged realized=False and excluded from
the chain. See shared/chain.py for the chain math (copied verbatim from v1) and
shared/market.py for the gain/benchmark helpers this reuses.

`build_hops()` is the expensive day-by-day simulation (one Step-2 selection per daynum
over the whole history); `compute_metrics()` is a cheap re-aggregation over an optional
[floor_daynum, cap_daynum] span — step4_walkforward.py reuses the SAME hop series across
every fold's train/test window rather than re-simulating per fold, exactly as
strategy_grp v1's best_strategy.py re-clamps one run's HopData to a common span.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import pandas as pd

from shared import market
from shared.chain import chain_lot_stats, chain_origin_sensitivity, realizable_chain
from shared.config import future_gain_file
from shared.data_loader import load_longi, load_potdat

import step0_data
import step1_dominance
import step2_focusset


@dataclass
class Hop:
    daynum: int
    tickers: list[str]
    gains: dict[str, float]        # realized gain (period-horizon) OR partial gain, per ticker
    realized: bool                 # True = closed horizon, counted in the chain
    ref_values: dict[str, float] = field(default_factory=dict)
    mkt_gain: float = float("nan")     # benchmark for this hop's gain, matching realized/partial
    beta: float = float("nan")


@dataclass
class BacktestResult:
    hops: list[Hop]
    params: dict
    metrics: dict[str, object]


def _find_start_daynum(gain_df: pd.DataFrame, min_valid: int = 10) -> int:
    """Newest daynum (working backwards through the newest-left columns) where the
    forward-gain file still has enough realized data — the realized/open boundary."""
    for col in gain_df.columns:
        if gain_df[col].dropna().size >= min_valid:
            return int(col)
    raise ValueError("no valid starting daynum found in the forward-gain file")


def build_hops(row_resolved: dict) -> tuple[list[Hop], dict]:
    """The full fused timeline for one row, newest-first, plus the params actually used
    (attribute names resolved through Step 0's twin binding)."""
    s0 = step0_data.resolve_step0(row_resolved)
    params = dict(row_resolved)
    params["dominance_attribute"] = s0.dominance_attribute
    params["priority_attribute"] = s0.priority_attribute

    period = int(params["period"])
    gain_df = load_longi(future_gain_file(period))
    potdat = load_potdat()
    beta_df = market.beta_frame()
    mkt_realized = market.market_gain_realized(period)

    dom_table, _cutoffs = step1_dominance.resolve_dom_table(s0.groups, params)

    exit_daynum = int(potdat.columns[0])
    start_daynum = _find_start_daynum(gain_df)          # realized/open boundary

    pot_cols = set(potdat.columns)
    open_daynums: list[int] = []
    d = start_daynum + 1
    while d <= exit_daynum:
        if str(d) in pot_cols:
            open_daynums.append(d)
        d += 1
    open_daynums.reverse()                              # newest first

    # gain_df.columns is newest-left, so filtering (not reordering) keeps this newest-first.
    realized_daynums = [int(c) for c in gain_df.columns if int(c) <= start_daynum]

    hops: list[Hop] = []
    for daynum in open_daynums:
        tickers = step2_focusset.select_focusset(daynum, dom_table, s0.groups, params, s0.post_filter)
        gains = market.compute_partial_gains(potdat, tickers, daynum, exit_daynum) if tickers else {}
        hops.append(Hop(
            daynum=daynum, tickers=tickers, gains=gains, realized=False,
            ref_values=market.get_reference_values(daynum),
            mkt_gain=market.market_partial_gain(potdat, daynum, exit_daynum),
            beta=market.hop_beta(beta_df, tickers, daynum),
        ))
    for daynum in realized_daynums:
        tickers = step2_focusset.select_focusset(daynum, dom_table, s0.groups, params, s0.post_filter)
        gains = market.get_gains(gain_df, tickers, daynum) if tickers else {}
        mkt = mkt_realized.get(str(daynum), float("nan"))
        hops.append(Hop(
            daynum=daynum, tickers=tickers, gains=gains, realized=True,
            ref_values=market.get_reference_values(daynum),
            mkt_gain=float(mkt) if pd.notna(mkt) else float("nan"),
            beta=market.hop_beta(beta_df, tickers, daynum),
        ))

    return hops, params


def _span(hops: list[Hop], floor_daynum: int | None, cap_daynum: int | None) -> list[Hop]:
    return [h for h in hops
            if (floor_daynum is None or h.daynum >= floor_daynum)
            and (cap_daynum is None or h.daynum <= cap_daynum)]


def gate_ok(h: Hop, threshold: float | None) -> bool:
    if threshold is None:
        return True
    gspc = h.ref_values.get("^GSPC_rsi", float("nan"))
    return pd.isna(gspc) or gspc >= threshold


def compute_metrics(hops: list[Hop], params: dict, settings: dict,
                   floor_daynum: int | None = None, cap_daynum: int | None = None) -> dict:
    """Summary metrics over an optional [floor_daynum, cap_daynum] span (default: the
    hop series' own full range). step4_walkforward.py calls this per fold with the
    train/test window instead of re-simulating — see this module's docstring."""
    threshold = params.get("no_go_gspc_rsi")
    period = int(params["period"])

    realized = _span([h for h in hops if h.realized], floor_daynum, cap_daynum)
    open_hops = _span([h for h in hops if not h.realized], floor_daynum, cap_daynum)
    gated_realized = [h for h in realized if gate_ok(h, threshold)]

    # avg_gain / median_gain / hit_rate% -- flattened across every ticker in every gated
    # hop (matches strategy_grp v1's _grand_avg_topn exactly: one pooled list, not a
    # mean-of-per-hop-means). This family's returns are right-tail driven by construction
    # (see strategy_grp's walkforward oos_median_gain note), so median/hit_rate ride beside
    # avg_gain here in Step 3 too, not just in Step 4.
    flat_gains = [g for h in gated_realized for g in h.gains.values() if pd.notna(g)]
    avg_gain = statistics.fmean(flat_gains) if flat_gains else float("nan")
    median_gain = statistics.median(flat_gains) if flat_gains else float("nan")
    hit_rate_pct = (sum(1 for g in flat_gains if g > 0) / len(flat_gains) * 100.0
                    if flat_gains else float("nan"))

    # avg_alpha / avg_beta -- per-hop mean gain vs that hop's own benchmark, averaged over
    # hops (matches v1's _grand_avg_alpha: NOT the same as flat_gains' mean minus a flat
    # market mean unless every hop has the same size).
    alphas: list[float] = []
    betas: list[float] = []
    for h in gated_realized:
        g = market.hop_avg(h.gains)
        if pd.notna(g) and pd.notna(h.mkt_gain):
            alphas.append(g - h.mkt_gain)
        if pd.notna(h.beta):
            betas.append(h.beta)
    avg_alpha = statistics.fmean(alphas) if alphas else float("nan")
    avg_beta = statistics.fmean(betas) if betas else float("nan")

    # Chain metrics over ALL realized hops in span (not pre-gated — realizable_chain
    # applies the No_go gate itself, exactly as strategy_grp v1's _chain_metrics does).
    chain_rows = [(h.daynum, market.hop_avg(h.gains), h.ref_values.get("^GSPC_rsi", float("nan")))
                  for h in realized]
    chain_ret, chain_annual, chain_n = realizable_chain(chain_rows, period, threshold, phase_average=True)
    _lot_avg, worst, n_loss = chain_lot_stats(chain_rows, period, threshold, phase_average=True)
    origin_sens = chain_origin_sensitivity(chain_rows, period, threshold, phase_average=True)

    min_chain_lots = int(settings.get("min_chain_lots", 3))
    thin = chain_n < min_chain_lots

    n_hops_active = sum(1 for h in realized if h.tickers and gate_ok(h, threshold))
    usable_daynums = [h.daynum for h in gated_realized if any(pd.notna(g) for g in h.gains.values())]

    # Open-window (still-realizing) partial summary -- v1's "extension" block, fused in.
    open_flat: list[float] = []
    open_alphas: list[float] = []
    for h in open_hops:
        if not h.tickers:
            continue
        open_flat.extend(g for g in h.gains.values() if pd.notna(g))
        g = market.hop_avg(h.gains)
        if pd.notna(g) and pd.notna(h.mkt_gain):
            open_alphas.append(g - h.mkt_gain)
    avg_partial_gain = statistics.fmean(open_flat) if open_flat else float("nan")
    avg_partial_alpha = statistics.fmean(open_alphas) if open_alphas else float("nan")

    return {
        "StartDaynum": min(usable_daynums) if usable_daynums else None,
        "EndDaynum": max(usable_daynums) if usable_daynums else None,
        "N_hops": len(realized) + len(open_hops),
        "N_hops_active": n_hops_active,
        "avg_gain": avg_gain, "median_gain": median_gain, "hit_rate%": hit_rate_pct,
        "avg_alpha": avg_alpha, "avg_beta": avg_beta,
        "chain_ret": chain_ret, "chain_annual": chain_annual, "chain_n": chain_n,
        "Worst": worst, "N_loss": n_loss, "origin_sens%": origin_sens,
        "thin": thin, "min_chain_lots": min_chain_lots,
        "avg_partial_gain": avg_partial_gain, "avg_partial_alpha": avg_partial_alpha,
        "n_open_hops": len(open_hops),
    }


def run_backtest(row_resolved: dict, settings: dict) -> BacktestResult:
    """The fused realized+open timeline and its full-span summary metrics for one row."""
    hops, params = build_hops(row_resolved)
    metrics = compute_metrics(hops, params, settings)
    return BacktestResult(hops=hops, params=params, metrics=metrics)
