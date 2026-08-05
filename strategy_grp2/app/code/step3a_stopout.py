"""
Step 3a — stop-out: a post-transform over Step 3's hop series, re-scoring each lot as if a
stock's gain had been capped the moment its path breached a STOP level. Kept separate from
build_hops (SM, 2026-08-05): the simulation is the expensive part of a tick and does not
depend on where a stop is set, so ONE hop series can be re-scored at every level in a sweep
almost for free.

`longi_future_minaggr<period>d.csv` is the "foresight eye" that makes this possible: for a
CLOSED hop it already holds the lowest gain the path reached before the horizon closed (<= 0,
floored at 0 -- see longi/app/code/longi_future_minaggr.py). Applying a stop is one clamp:

    stopped_gain = STOP    if minaggr <= STOP else the original (unchanged) gain

Unconditionally STOP, not max(gain, STOP) -- a breached stock is being simulated as EXITED,
so a later recovery past STOP is not available to it; that forgone recovery is exactly the
"cost" side SM asked to see measured, not something to award back by taking the better of the
two numbers.

Still-OPEN hops have no minaggr yet (its newest period+1 columns are blank by construction,
the same realized/open boundary longi_future_per*.csv has); shared.market.partial_min_gains
reads the ELAPSED part of PotDat's price path instead -- realized history, not foresight.

A stop is not free: every level is reported as a benefit/cost pair (loss avoided vs. gain
forgone), never just a net number, since "n_stopped" alone cannot say which side dominates.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd

from shared import market
from shared.config import MINAGGR_PERIODS, minaggr_file
from shared.data_loader import load_longi, load_potdat

import step3_backtest as bt


@dataclass
class StopProfile:
    stop: float | None          # None = the "off" / unstopped baseline row
    n_positions: int            # ticker-hop slots with both a real gain and a known worst-path value
    n_stopped: int              # of those, how many breached `stop`
    benefit: float              # sum of loss avoided (>=0) over stopped positions
    cost: float                 # sum of gain forgone (>=0) over stopped positions

    @property
    def net(self) -> float:
        return self.benefit - self.cost

    @property
    def net_per_position(self) -> float:
        return self.net / self.n_positions if self.n_positions else float("nan")


def apply_stop(hops: list["bt.Hop"], stop: float | None,
               period: int) -> tuple[list["bt.Hop"], StopProfile]:
    """A NEW hop list (the raw hops are cached and shared with Step 4 -- see
    step3_backtest.run_backtest -- so this never mutates them) with each ticker's gain
    capped at `stop` where its path breached it, plus the benefit/cost decomposition over
    exactly the positions touched.

    stop=None (or 0 / falsy) is the "off" baseline: hops pass through unchanged (still
    copied, so every caller holds a fresh list) and the profile is all zeros.
    """
    if not stop:
        return ([dataclasses.replace(h) for h in hops],
                StopProfile(stop=None, n_positions=0, n_stopped=0, benefit=0.0, cost=0.0))

    if period not in MINAGGR_PERIODS:
        raise ValueError(
            f"apply_stop: period={period} has no longi_future_minaggr*.csv counterpart "
            f"(valid: {list(MINAGGR_PERIODS)})"
        )

    minaggr_df = load_longi(minaggr_file(period))
    potdat = None                      # loaded lazily, only if an open hop is present
    exit_daynum: int | None = None

    n_positions = n_stopped = 0
    benefit = cost = 0.0
    new_hops: list["bt.Hop"] = []

    for h in hops:
        if not h.tickers:
            new_hops.append(dataclasses.replace(h))
            continue

        if h.realized:
            col = str(h.daynum)
            worst = {t: (float(minaggr_df.at[t, col])
                        if t in minaggr_df.index and col in minaggr_df.columns
                           and pd.notna(minaggr_df.at[t, col])
                        else float("nan"))
                    for t in h.tickers}
        else:
            if potdat is None:
                potdat = load_potdat()
                exit_daynum = int(potdat.columns[0])
            worst = market.partial_min_gains(potdat, h.tickers, h.daynum, exit_daynum)

        new_gains = dict(h.gains)
        stopped_here: set[str] = set()
        for t in h.tickers:
            gain, w = h.gains.get(t), worst.get(t)
            if gain is None or pd.isna(gain) or w is None or pd.isna(w):
                continue
            n_positions += 1
            if w <= stop:
                n_stopped += 1
                stopped_here.add(t)
                benefit += max(0.0, stop - gain)      # loss avoided: gain was worse than stop
                cost += max(0.0, gain - stop)          # gain forgone: gain was better than stop
                new_gains[t] = stop
        new_hops.append(dataclasses.replace(h, gains=new_gains, stopped=stopped_here))

    profile = StopProfile(stop=stop, n_positions=n_positions, n_stopped=n_stopped,
                          benefit=benefit, cost=cost)
    return new_hops, profile


def parse_sweep_levels(raw: str) -> list[float]:
    """`Settings.stop_sweep`'s comma-separated ladder -> floats. Blank -> no sweep."""
    if not raw or not str(raw).strip():
        return []
    return [float(x) for x in str(raw).split(",") if x.strip()]


def levels_hops(hops_raw: list["bt.Hop"], period: int,
                levels: list[float]) -> dict[float | None, tuple[list["bt.Hop"], StopProfile]]:
    """apply_stop, once per level (plus the `None`/off baseline), keyed by level -- shared
    by sweep() and outputboard's fold-stability table so a level is never re-applied to
    hops_raw twice for the same row."""
    return {stop: apply_stop(hops_raw, stop, period) for stop in [None] + list(levels)}


def metrics_rows(by_level: dict[float | None, tuple[list["bt.Hop"], StopProfile]],
                 params: dict, settings: dict) -> list[dict]:
    """One row per level in `by_level`, combining the stop's own cost/benefit profile with
    bt.compute_metrics()'s full output over the stopped hop series -- so Worst/N_loss/
    chain_annual/median_gain/hit_rate% etc. are exactly what Step3_compare would show for
    that row at that stop_loss, reused unchanged rather than re-derived."""
    rows: list[dict] = []
    for stop, (hops, profile) in by_level.items():
        metrics = bt.compute_metrics(hops, params, settings)
        row = {
            "stop": stop,
            "n_positions": profile.n_positions, "n_stopped": profile.n_stopped,
            "benefit": profile.benefit, "cost": profile.cost,
            "net": profile.net, "net_per_position": profile.net_per_position,
        }
        row.update(metrics)
        rows.append(row)
    return rows


def sweep(hops_raw: list["bt.Hop"], params: dict, settings: dict,
         levels: list[float]) -> list[dict]:
    """One row per level in `levels`, plus an 'off' baseline first -- see metrics_rows()
    for what each row carries. `params`/`settings` are the row's own (no_go gate,
    min_chain_lots, etc.) -- only the hop gains vary between rows of this table."""
    by_level = levels_hops(hops_raw, int(params["period"]), levels)
    return metrics_rows(by_level, params, settings)


def fold_metrics(by_level: dict[float | None, tuple[list["bt.Hop"], StopProfile]],
                 params: dict, settings: dict, folds: list[dict]) -> list[dict]:
    """Per (fold, stop level): bt.compute_metrics restricted to that fold's own TEST
    window -- the SAME folds already on Step4_walkforward (a GroupResult's `.folds`,
    passed in by the caller; this module has no fold geometry of its own). Deliberately
    NOT a training-window selection like step4_walkforward.walk_group: every level is
    scored on every fold, so the question answered is "how time-stable is THIS level's
    own out-of-sample result", not "would picking the in-sample winner have survived".
    SM, 2026-08-05: stop levels are the same picks with different clamps, not
    meaningfully distinct candidates, so a training-window pick between them would
    mostly measure noise -- fold-by-fold stability of a fixed level is the more honest
    question and reuses no new fold logic."""
    rows: list[dict] = []
    for fi, f in enumerate(folds, start=1):
        for stop, (hops, _profile) in by_level.items():
            m = bt.compute_metrics(hops, params, settings, f["test_from"], f["test_to"])
            rows.append({
                "fold": fi, "test_dates": f.get("test_dates"), "stop": stop,
                "avg_gain": m["avg_gain"], "median_gain": m["median_gain"],
                "hit_rate%": m["hit_rate%"], "chain_annual": m["chain_annual"],
                "chain_n": m["chain_n"], "Worst": m["Worst"], "N_loss": m["N_loss"],
            })
    return rows


def best_level(rows: list[dict], tolerance: float) -> float | None:
    """The stop level to flag as best: risk-first (SM, 2026-08-05) -- ranked by `Worst`
    (least negative first) then `N_loss` (fewest first), among the levels whose
    `chain_annual` gives up no more than `tolerance` percent of the unstopped baseline.

    None when no level qualifies -- including when every level's `chain_annual` already
    IMPROVES on the baseline, since the tolerance is a maximum giveback, not a floor, and
    when the baseline itself has no usable chain_annual to compare against."""
    baseline = next((r for r in rows if r["stop"] is None), None)
    if baseline is None or pd.isna(baseline.get("chain_annual")):
        return None
    base_annual = baseline["chain_annual"]

    candidates = []
    for r in rows:
        if r["stop"] is None or pd.isna(r.get("chain_annual")) or pd.isna(r.get("Worst")):
            continue
        giveback_pct = ((base_annual - r["chain_annual"]) / abs(base_annual) * 100.0
                        if abs(base_annual) > 1e-9 else 0.0)
        if giveback_pct > tolerance:
            continue
        candidates.append(r)
    if not candidates:
        return None
    return min(candidates, key=lambda r: (-r["Worst"], r["N_loss"]))["stop"]
