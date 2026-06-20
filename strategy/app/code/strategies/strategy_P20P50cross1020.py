"""
Strategy: P20P50cross1020
Selection driven by an ad-hoc quotient table built at runtime:

  Q10_20 = longi_ma10.csv / longi_ma20.csv   (== 1 at the MA10/MA20 golden cross,
                                               > 1 once MA10 has crossed above MA20)

Four-stage selection:
  1. longi_P20d_win.csv — keep those where P20d_win >= p20d_win_min
  2. longi_P50d_win.csv — keep those where P50d_win >= p50d_win_min
  3. Q10_20 (ad-hoc)    — keep those where Q10_20 >= q10_20_min
     N_survivors = number of tickers passing all three filters (recorded per hop)
  4. longi_rank.csv     — from survivors, pick N with lowest rank

Days where fewer than focusset_size tickers survive all filters are skipped entirely.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.data_loader import load_longi, load_potdat, daynum_to_date
from shared.report import save_report

STRATEGY_NAME = "P20P50cross1020"

PARAMS: dict = {
    "focusset_size": 3,
    "step": 1,
    "No_go_GSPC_rsi": 45,
    "p20d_win_min": 0.9,
    "p50d_win_min": 0.9,
    "q10_20_min": 1.03,
}


# ---------------------------------------------------------------------------
# Ad-hoc Q10_20 table
# ---------------------------------------------------------------------------

def build_q10_20() -> pd.DataFrame:
    """
    Build the ad-hoc Q10_20 quotient table (MA10 / MA20), used downstream as if it
    were a preformed Longi matrix CSV. Aligns on tickers (rows) and daynum (cols);
    cells are NaN where either MA is missing or MA20 is zero.
    """
    ma10_df = load_longi("longi_ma10.csv")
    ma20_df = load_longi("longi_ma20.csv")
    q_df = ma10_df.divide(ma20_df.replace(0, float("nan")))
    return q_df


# ---------------------------------------------------------------------------
# Core strategy logic
# ---------------------------------------------------------------------------

def survivors(daynum: int, p20d_win_df: pd.DataFrame, p50d_win_df: pd.DataFrame,
              q_df: pd.DataFrame) -> set[str]:
    """
    Tickers passing the P20d_win, P50d_win and Q10_20 filters at daynum.
    Returns an empty set if any source lacks the column. Never raises.
    """
    col = str(daynum)
    if (col not in p20d_win_df.columns or col not in p50d_win_df.columns
            or col not in q_df.columns):
        return set()

    p20d_series = p20d_win_df[col].dropna()
    qualifying = set(p20d_series[p20d_series >= PARAMS["p20d_win_min"]].index)
    if not qualifying:
        return set()

    p50d_series = p50d_win_df[col].dropna()
    qualifying &= set(p50d_series[p50d_series >= PARAMS["p50d_win_min"]].index)
    if not qualifying:
        return set()

    q_series = q_df[col].dropna()
    qualifying &= set(q_series[q_series >= PARAMS["q10_20_min"]].index)
    return qualifying


def select_focusset(daynum: int, p20d_win_df: pd.DataFrame, p50d_win_df: pd.DataFrame,
                    q_df: pd.DataFrame, rank_df: pd.DataFrame, n: int) -> list[str]:
    """
    Return exactly n tickers that meet both P-win thresholds and the Q10_20 minimum,
    ranked by lowest rank at daynum. Returns [] if fewer than n survivors qualify.
    """
    col = str(daynum)
    qualifying = survivors(daynum, p20d_win_df, p50d_win_df, q_df)
    if not qualifying or col not in rank_df.columns:
        return []

    rank_series = rank_df.loc[rank_df.index.isin(qualifying), col].dropna()
    if len(rank_series) < n:
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
                      p20d_win_df: pd.DataFrame, p50d_win_df: pd.DataFrame,
                      q_df: pd.DataFrame, min_valid: int = 10) -> int:
    """Return the first daynum where all data sources have sufficient data."""
    for col in gain20_df.columns:
        daynum = int(col)
        scol = str(daynum)
        has_rank  = scol in rank_df.columns and rank_df[scol].dropna().size >= min_valid
        has_gain  = gain20_df[col].dropna().size >= min_valid
        has_p20dw = scol in p20d_win_df.columns
        has_p50dw = scol in p50d_win_df.columns
        has_q     = scol in q_df.columns
        if has_rank and has_gain and has_p20dw and has_p50dw and has_q:
            return daynum
    raise ValueError(
        "No valid starting daynum found — check future_gain20d.csv, longi_rank.csv, "
        "longi_P20d_win.csv, longi_P50d_win.csv, longi_ma10.csv, and longi_ma20.csv"
    )


def get_reference_values(daynum: int) -> dict[str, float]:
    """
    Market context at starting daynum.
    ^GSPC, ^STOXX, ^HSI: RSI14. ^VIX: raw value.
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
    p50d_win_df = load_longi("longi_P50d_win.csv")
    rank_df     = load_longi("longi_rank.csv")
    gain20_df   = load_longi("future_gain20d.csv")
    gain50_df   = load_longi("future_gain50d.csv")
    q_df        = build_q10_20()

    n: int    = PARAMS["focusset_size"]
    step: int = PARAMS["step"]

    start_daynum = find_start_daynum(gain20_df, rank_df, p20d_win_df, p50d_win_df, q_df)
    min_daynum = max(
        int(gain20_df.columns[-1]),
        int(rank_df.columns[-1]),
        int(p20d_win_df.columns[-1]),
        int(p50d_win_df.columns[-1]),
        int(q_df.columns[-1]),
    )

    print(f"--- {STRATEGY_NAME} ---")
    print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
    print(f"Min daynum   : {min_daynum}")
    print(f"Focusset size: {n}   Step: {step}"
          f"   P20d_win >= {PARAMS['p20d_win_min']}   P50d_win >= {PARAMS['p50d_win_min']}"
          f"   Q10_20 >= {PARAMS['q10_20_min']}")
    print()

    hop_results: list[dict] = []
    skipped = 0
    daynum = start_daynum

    while daynum >= min_daynum:
        tickers = select_focusset(daynum, p20d_win_df, p50d_win_df, q_df, rank_df, n)
        if not tickers:
            skipped += 1
            daynum -= step
            continue

        n_survivors = len(survivors(daynum, p20d_win_df, p50d_win_df, q_df))
        gains_20d = get_gains(gain20_df, tickers, daynum)
        gains_50d = get_gains(gain50_df, tickers, daynum)
        avg20 = _hop_avg(gains_20d)
        avg50 = _hop_avg(gains_50d)

        hop_num = len(hop_results) + 1
        date_str = daynum_to_date(daynum)
        line = (f"  hop {hop_num:>3}: daynum {daynum} ({date_str})"
                f"  survivors={n_survivors}"
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
            "n_survivors": n_survivors,
            "gains_20d": gains_20d,
            "gains_50d": gains_50d,
            "ref_values_prev": get_reference_values(daynum - 1),
        })
        daynum -= step

    print()
    print(f"Days with no qualifying tickers (P20d_win & P50d_win & Q10_20): {skipped}")
    if not hop_results:
        print("No valid hops produced — no tickers passed all three filters in the data range")
        sys.exit(1)

    save_report(STRATEGY_NAME, PARAMS, hop_results)

    n_hops = len(hop_results)
    print(f"Done: {n_hops} hops  "
          f"daynum {hop_results[0]['daynum']} → {hop_results[-1]['daynum']}")


def build_extension() -> None:
    from shared.extension import run_extension
    p20d_win_df = load_longi("longi_P20d_win.csv")
    p50d_win_df = load_longi("longi_P50d_win.csv")
    rank_df     = load_longi("longi_rank.csv")
    q_df        = build_q10_20()
    n: int      = PARAMS["focusset_size"]
    run_extension(STRATEGY_NAME, PARAMS,
                  lambda d: select_focusset(d, p20d_win_df, p50d_win_df, q_df, rank_df, n),
                  get_reference_values)


if __name__ == "__main__":
    main()
