"""
Strategy: Ranknow
Select the N tickers with the best (lowest) longi_rank at each test daynum,
then measure their realised forward gains over 20d and 50d horizons.
N is set via PARAMS["focusset_size"].
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.data_loader import load_longi, load_potdat, daynum_to_date
from shared.report import save_report
from shared.select import pick_by_rank

STRATEGY_NAME = "Ranknow"

# Set True to log every hop; keep False to avoid noise during sweeps.
VERBOSE = False

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "period": 20,           # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": 40,
    "from_rank": 1,         # where in the ranking to draw from: 1=best n,
                            # k>1=skip best k-1, -1=worst n. See shared/select.py.
}

# ---------------------------------------------------------------------------
# Core strategy logic
# ---------------------------------------------------------------------------

def select_focusset(daynum: int, rank_df: pd.DataFrame, n: int) -> list[str]:
    """Return n tickers by rank at daynum, windowed by PARAMS['from_rank']
    (1=best n, k>1=skip best k-1, -1=worst n)."""
    col = str(daynum)
    if col not in rank_df.columns:
        return []
    return pick_by_rank(rank_df[col], n, PARAMS.get("from_rank", 1))


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
                      min_valid: int = 10) -> int:
    """
    Walk future_gain20d columns left-to-right (newest first) and return the
    first daynum where both rank_df AND gain20_df have at least min_valid valid values.
    This skips the most recent ~20 daynums where future gain is not yet realized.
    """
    for col in gain20_df.columns:
        daynum = int(col)
        scol = str(daynum)
        has_rank = scol in rank_df.columns and rank_df[scol].dropna().size >= min_valid
        has_gain = gain20_df[col].dropna().size >= min_valid
        if has_rank and has_gain:
            return daynum
    raise ValueError("No valid starting daynum found — check future_gain20d.csv and longi_rank.csv")


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
    rank_df = load_longi("longi_rank.csv")
    period: int = PARAMS.get("period", 20)
    gain_df = load_longi(f"future_gain{period}d.csv")

    n: int = PARAMS["focusset_size"]
    step: int = PARAMS["step"]

    start_daynum = find_start_daynum(gain_df, rank_df)
    # Stop before the oldest column in either file we depend on
    min_daynum = max(int(gain_df.columns[-1]), int(rank_df.columns[-1]))

    print(f"--- {STRATEGY_NAME} ---")
    print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
    print(f"Min daynum   : {min_daynum}")
    print(f"Focusset size: {n}   Step: {step}   Period: {period}d")
    print()

    hop_results: list[dict] = []
    daynum = start_daynum

    while daynum >= min_daynum:
        tickers = select_focusset(daynum, rank_df, n)
        if not tickers:
            print(f"  daynum {daynum}: no focusset available — stopping")
            break

        gains = get_gains(gain_df, tickers, daynum)
        avg = _hop_avg(gains)

        hop_num = len(hop_results) + 1
        date_str = daynum_to_date(daynum)
        line = (f"  hop {hop_num:>2}: daynum {daynum} ({date_str})"
                f"  {period}d avg={avg:+.2f}%")
        if VERBOSE:
            print(line)

        hop_results.append({
            "daynum": daynum,
            "tickers": tickers,
            "gains": gains,
            "ref_values_prev": get_reference_values(daynum - 1),
        })
        daynum -= step

    print()
    if not hop_results:
        print("No valid hops produced — exiting")
        sys.exit(1)

    save_report(STRATEGY_NAME, PARAMS, hop_results)

    n_hops = len(hop_results)
    print(f"Done: {n_hops} hops  "
          f"daynum {hop_results[0]['daynum']} → {hop_results[-1]['daynum']}")


def build_extension(workbook=None):
    from shared.extension import run_extension
    rank_df = load_longi("longi_rank.csv")
    n: int  = PARAMS["focusset_size"]
    return run_extension(STRATEGY_NAME, PARAMS,
                         lambda d: select_focusset(d, rank_df, n),
                         get_reference_values, workbook=workbook)


if __name__ == "__main__":
    main()
