"""
Market context and benchmark helpers shared by step3_backtest.py and step4_walkforward.py —
consolidates what strategy_grp v1 split across shared/engine.py, shared/report.py and
shared/extension.py, since v2 fuses the realized backtest and the open-window extension
into one timeline (see DesignVersion2.md's Step 3 write-up) and both regimes need the same
building blocks.

`alpha` throughout this project is ACTIVE RETURN (focusset gain minus the benchmark's gain
for the same daynum) — it assumes beta=1 and a zero risk-free rate, and is NOT Jensen's
alpha. The benchmark is the equal-weighted cross-sectional mean of EVERY ticker that
daynum (not a cap-weighted index): "the average stock you could have picked that day" is
the right counterfactual for a stock-picking strategy. See strategy_grp v1's CLAUDE.md for
the full argument against a regression form.
"""

from __future__ import annotations

import pandas as pd

from shared.config import future_gain_file
from shared.data_loader import load_longi, load_potdat


def get_gains(gain_df: pd.DataFrame, tickers: list[str], daynum: int) -> dict[str, float]:
    """Realized gains for tickers at daynum, from a longi_future_per*.csv matrix. NaN for
    missing data — never an error."""
    col = str(daynum)
    if col not in gain_df.columns:
        return {t: float("nan") for t in tickers}
    return {
        t: (float(gain_df.at[t, col])
            if t in gain_df.index and pd.notna(gain_df.at[t, col])
            else float("nan"))
        for t in tickers
    }


def get_reference_values(daynum: int) -> dict[str, float]:
    """Market context at the investment daynum: ^GSPC/^STOXX/^HSI RSI14, ^VIX raw value
    (RSI of VIX is misleading — it moves inversely to markets)."""
    rsi_df = load_longi("longi_rsi.csv")
    potdat = load_potdat()
    col = str(daynum)
    result: dict[str, float] = {}

    for ticker in ("^GSPC", "^STOXX", "^HSI"):
        key = f"{ticker}_rsi"
        try:
            val = (rsi_df.at[ticker, col]
                   if ticker in rsi_df.index and col in rsi_df.columns
                   else float("nan"))
            result[key] = float(val) if pd.notna(val) else float("nan")
        except (KeyError, ValueError):
            result[key] = float("nan")

    try:
        val = (potdat.at["^VIX", col]
               if "^VIX" in potdat.index and col in potdat.columns
               else float("nan"))
        result["^VIX"] = float(val) if pd.notna(val) else float("nan")
    except (KeyError, ValueError):
        result["^VIX"] = float("nan")

    return result


def hop_avg(gains: dict[str, float]) -> float:
    vals = [v for v in gains.values() if pd.notna(v)]
    return sum(vals) / len(vals) if vals else float("nan")


def hop_median(gains: dict[str, float]) -> float:
    import statistics
    vals = [v for v in gains.values() if pd.notna(v)]
    return statistics.median(vals) if vals else float("nan")


def hit_rate(gains: dict[str, float]) -> float:
    """Fraction of non-NaN gains that are > 0, as a percentage. NaN when nothing to score."""
    vals = [v for v in gains.values() if pd.notna(v)]
    return (sum(1 for v in vals if v > 0) / len(vals) * 100.0) if vals else float("nan")


def market_gain_realized(period: int) -> pd.Series:
    """Benchmark for REALIZED hops: equal-weighted cross-sectional mean of
    longi_future_per<period>d.csv, per daynum."""
    return load_longi(future_gain_file(period)).mean(axis=0)


def beta_frame() -> pd.DataFrame | None:
    """longi_beta3m.csv, or None when absent — beta is optional context, never required."""
    try:
        return load_longi("longi_beta3m.csv")
    except (FileNotFoundError, OSError):
        return None


def hop_beta(beta_df: pd.DataFrame | None, tickers: list[str], daynum: int) -> float:
    """Mean beta3m of a hop's tickers, as known ON the entry daynum — a PRE-trade number,
    context for reading alpha (these picks tend to run above market beta), not a forecast."""
    if beta_df is None:
        return float("nan")
    col = str(daynum)
    if col not in beta_df.columns:
        return float("nan")
    vals = [float(beta_df.at[t, col]) for t in tickers
            if t in beta_df.index and pd.notna(beta_df.at[t, col])]
    return sum(vals) / len(vals) if vals else float("nan")


def compute_partial_gains(potdat: pd.DataFrame, tickers: list[str],
                         entry_daynum: int, exit_daynum: int) -> dict[str, float]:
    """(price[exit] - price[entry]) / price[entry] * 100, for a still-OPEN hop whose
    horizon has not realized yet. NaN when a price is unavailable."""
    ec, xc = str(entry_daynum), str(exit_daynum)
    result: dict[str, float] = {}
    for t in tickers:
        try:
            pe = (float(potdat.at[t, ec])
                  if t in potdat.index and ec in potdat.columns and pd.notna(potdat.at[t, ec])
                  else float("nan"))
            px = (float(potdat.at[t, xc])
                  if t in potdat.index and xc in potdat.columns and pd.notna(potdat.at[t, xc])
                  else float("nan"))
            result[t] = ((px - pe) / pe * 100
                         if pd.notna(pe) and pd.notna(px) and pe != 0
                         else float("nan"))
        except (KeyError, ValueError):
            result[t] = float("nan")
    return result


def partial_min_gains(potdat: pd.DataFrame, tickers: list[str],
                      entry_daynum: int, exit_daynum: int) -> dict[str, float]:
    """Worst (<=0) gain reached so far in a still-OPEN hop, over the ELAPSED part of the
    window only -- step3a_stopout's counterpart to compute_partial_gains' single final-day
    figure, for the trailing ~period hops longi_future_minaggr*.csv has no value for yet
    (its newest period+1 columns are blank by construction, same boundary as the realized
    gain file). Same (entry_daynum, exit_daynum) pair as compute_partial_gains, so the two
    stay consistent about what counts as "entry" and "as of today". NaN when the entry
    price is unavailable."""
    ec = str(entry_daynum)
    window_cols = [c for c in potdat.columns if entry_daynum <= int(c) <= exit_daynum]
    result: dict[str, float] = {}
    for t in tickers:
        try:
            pe = (float(potdat.at[t, ec])
                  if t in potdat.index and ec in potdat.columns and pd.notna(potdat.at[t, ec])
                  else float("nan"))
        except (KeyError, ValueError):
            pe = float("nan")
        if pd.isna(pe) or pe == 0 or t not in potdat.index:
            result[t] = float("nan")
            continue
        prices = pd.to_numeric(potdat.loc[t, window_cols], errors="coerce").dropna()
        if prices.empty:
            result[t] = float("nan")
            continue
        result[t] = min(0.0, (float(prices.min()) - pe) / pe * 100)
    return result


def market_partial_gain(potdat: pd.DataFrame, entry_daynum: int, exit_daynum: int) -> float:
    """Benchmark for an OPEN hop, over the SAME still-elapsed window: equal-weighted
    cross-sectional mean of every ticker's partial price return. Deliberately not
    market_gain_realized — the realized longi_future_per* matrix by definition does not
    exist yet for these entries."""
    import numpy as np
    ec, xc = str(entry_daynum), str(exit_daynum)
    if ec not in potdat.columns or xc not in potdat.columns:
        return float("nan")
    pe = pd.to_numeric(potdat[ec], errors="coerce")
    px = pd.to_numeric(potdat[xc], errors="coerce")
    ret = ((px - pe) / pe * 100).where(pe.notna() & px.notna() & (pe != 0))
    ret = ret[np.isfinite(ret)]
    return float(ret.mean()) if len(ret) else float("nan")
