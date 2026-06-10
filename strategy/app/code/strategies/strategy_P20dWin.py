"""
Strategy: P20dWin
Select tickers where longi_P20d_win >= 0.8 at the test daynum,
then pick the N with the lowest longi_rank. Backtest 20d and 50d gains.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.data_loader import load_longi, load_potdat, daynum_to_date
from shared.report import save_report

STRATEGY_NAME = "P20dWin"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "No_go_GSPC_rsi": 40,
    "p20d_win_min": 0.8,
}


# ---------------------------------------------------------------------------
# Core strategy logic
# ---------------------------------------------------------------------------

def select_focusset(daynum: int, p20d_win_df: pd.DataFrame,
                    rank_df: pd.DataFrame, n: int) -> list[str]:
    """Return the n tickers with P20d_win >= threshold and lowest rank at daynum."""
    col = str(daynum)
    threshold: float = PARAMS["p20d_win_min"]

    if col not in p20d_win_df.columns:
        return []
    win_series = p20d_win_df[col].dropna()
    qualifying = win_series[win_series >= threshold].index.tolist()
    if not qualifying:
        return []

    if col not in rank_df.columns:
        return []
    rank_series = rank_df.loc[rank_df.index.isin(qualifying), col].dropna()
    if rank_series.empty:
        return []
    return rank_series.nsmallest(n).index.tolist()


def get_gains(gain_df: pd.DataFrame, tickers: list[str], daynum: int) -> dict[str, float]:
    """Read realised gains for tickers at daynum. Returns NaN for missing data."""
    col = str(daynum)
    if col not in gain_df.columns:
        return {t: float("nan") for t in tickers}
    return {
        t: (float(gain_df.at[t, col])
            if t in gain_df.index and pd.notna(gain_df.at[t, col])
            else float("nan"))
        for t in tickers
    }


def find_start_daynum(gain20_df: pd.DataFrame, rank_df: pd.DataFrame,
                      p20d_win_df: pd.DataFrame, min_valid: int = 10) -> int:
    """
    Walk future_gain20d columns left-to-right (newest first) and return the
    first daynum where all three data sources have sufficient data.
    Skips the most recent ~20 daynums where future gain is not yet realized.
    """
    for col in gain20_df.columns:
        daynum = int(col)
        scol = str(daynum)
        has_rank  = scol in rank_df.columns     and rank_df[scol].dropna().size >= min_valid
        has_gain  = gain20_df[col].dropna().size >= min_valid
        has_p20dw = scol in p20d_win_df.columns
        if has_rank and has_gain and has_p20dw:
            return daynum
    raise ValueError("No valid starting daynum found — check future_gain20d.csv, longi_rank.csv, and longi_P20d_win.csv")


def get_reference_values(daynum: int) -> dict[str, float]:
    """
    Market context at starting daynum.
    ^GSPC, ^STOXX, ^HSI: RSI14 as direction indicator.
    ^VIX: raw value (RSI of VIX is misleading as it moves inversely to markets).
    """
    rsi_df = load_longi("longi_rsi.csv")
    potdat = load_potdat()
    col    = str(daynum)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hop_avg(gains: dict[str, float]) -> float:
    vals = [v for v in gains.values() if pd.notna(v)]
    return sum(vals) / len(vals) if vals else float("nan")


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def main() -> None:
    p20d_win_df = load_longi("longi_P20d_win.csv")
    rank_df     = load_longi("longi_rank.csv")
    gain20_df   = load_longi("future_gain20d.csv")
    gain50_df   = load_longi("future_gain50d.csv")

    n: int    = PARAMS["focusset_size"]
    step: int = PARAMS["step"]

    start_daynum = find_start_daynum(gain20_df, rank_df, p20d_win_df)
    min_daynum = max(
        int(gain20_df.columns[-1]),
        int(rank_df.columns[-1]),
        int(p20d_win_df.columns[-1]),
    )

    print(f"--- {STRATEGY_NAME} ---")
    print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
    print(f"Min daynum   : {min_daynum}")
    print(f"Focusset size: {n}   Step: {step}   P20d_win >= {PARAMS['p20d_win_min']}")
    print()

    hop_results: list[dict] = []
    daynum = start_daynum

    while daynum >= min_daynum:
        tickers = select_focusset(daynum, p20d_win_df, rank_df, n)
        if not tickers:
            daynum -= step
            continue

        gains_20d = get_gains(gain20_df, tickers, daynum)
        gains_50d = get_gains(gain50_df, tickers, daynum)
        avg20 = _hop_avg(gains_20d)
        avg50 = _hop_avg(gains_50d)

        hop_num = len(hop_results) + 1
        date_str = daynum_to_date(daynum)
        line = (f"  hop {hop_num:>3}: daynum {daynum} ({date_str})"
                f"  tickers={tickers}"
                f"  20d avg={avg20:+.2f}%")
        if pd.notna(avg50):
            line += f"  50d avg={avg50:+.2f}%"
        else:
            line += "  50d=n/a"
        print(line)

        hop_results.append({
            "daynum": daynum,
            "tickers": tickers,
            "gains_20d": gains_20d,
            "gains_50d": gains_50d,
            "ref_values_prev": get_reference_values(daynum - 1),
        })
        daynum -= step

    print()
    if not hop_results:
        print("No valid hops produced — no tickers met P20d_win >= threshold in the data range")
        sys.exit(1)

    save_report(STRATEGY_NAME, PARAMS, hop_results)

    n_hops = len(hop_results)
    print(f"Done: {n_hops} hops  "
          f"daynum {hop_results[0]['daynum']} → {hop_results[-1]['daynum']}")


if __name__ == "__main__":
    main()
