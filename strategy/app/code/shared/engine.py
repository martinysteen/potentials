"""
Declarative strategy engine — the single place that holds the backtest machinery
every filter-based strategy shares.

A strategy is fully described by three things:
    STRATEGY_NAME : str
    PARAMS        : dict   (thresholds + focusset_size/step/period/No_go_GSPC_rsi/from_rank)
    FILTERS       : list   (col_filter / quotient_filter specs)
    [ranker]      : optional — how to order survivors in the final pick (default longi_rank ↑)

`make_strategy(name, params, filters, ranker)` returns the `(main, build_extension)` pair
the rest of the system expects, so a strategy file is a ~20-line declaration:

    from shared.engine import make_strategy, col_filter, quotient_filter
    STRATEGY_NAME = "Cross1020"
    PARAMS = {...}
    FILTERS = [quotient_filter("longi_ma10.csv", "longi_ma20.csv", "q10_20_min")]
    main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)

Selection pipeline (one daynum):
    N filters (any longi CSV, any of >= > <= <)  →  intersect survivors
      →  order by ranker (any longi CSV, ascending or descending)
      →  pick_by_rank window (from_rank: 1=best n, k>1=skip top, -1=worst n)

There is no hard limit on the number of filters; "max 3 steps" is a modelling choice,
not something the engine enforces. New criteria and new final-step priorities are pure
declarations — no engine edit needed.

Compatibility: run_sweep.run_strategy mutates a strategy's PARAMS in place
(`module.PARAMS.clear(); module.PARAMS.update(swept)`) and then calls `module.main()`.
The engine therefore closes over the SAME params dict object and reads every value
(thresholds, period, focusset_size, step, from_rank) LIVE at call time, never copying
at construction — clear()+update() preserves identity, so live reads see swept values.
"""

import operator as _op
import sys
from pathlib import Path
from typing import Callable

import pandas as pd

# Allow `from shared...` imports when a strategy file runs us as `python strategy_X.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.data_loader import load_longi, load_potdat, daynum_to_date
from shared.report import save_report
from shared.select import pick_by_rank


# ---------------------------------------------------------------------------
# Filter specs
# ---------------------------------------------------------------------------

_OPS: dict[str, Callable[[pd.Series, float], pd.Series]] = {
    ">=": _op.ge, ">": _op.gt, "<=": _op.le, "<": _op.lt,
}


class _Filter:
    """One selection step: keep tickers where `source[daynum] <op> PARAMS[param]`.

    The source DataFrame is resolved once (lazily, on first use) by `_build`, so a
    plain CSV and an ad-hoc MA quotient table look identical to the rest of the engine.
    The threshold is read live from `params[param]` at every call.
    """

    def __init__(self, build: Callable[[], pd.DataFrame], param: str, op: str, label: str):
        if op not in _OPS:
            raise ValueError(f"Unsupported filter op {op!r}; use one of {sorted(_OPS)}")
        self._build = build
        self.param  = param
        self._cmp   = _OPS[op]
        self.label  = label          # for error messages / find_start_daynum diagnostics
        self._df: pd.DataFrame | None = None

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = self._build()
        return self._df

    def qualifying(self, daynum: int, params: dict) -> set[str] | None:
        """Tickers passing this filter at daynum, or None if the column is absent."""
        col = str(daynum)
        if col not in self.df.columns:
            return None
        series = self.df[col].dropna()
        return set(series[self._cmp(series, params[self.param])].index)


def col_filter(csv_name: str, param: str, op: str = ">=") -> _Filter:
    """Filter on a preformed Longi matrix CSV: keep `value <op> PARAMS[param]`.

    e.g. col_filter("longi_rsi.csv", "rsi_min")                     -> RSI >= min
         col_filter("longi_beta1yr.csv", "beta_max", op="<")        -> beta < max
    """
    return _Filter(lambda: load_longi(csv_name), param, op, csv_name)


def quotient_filter(num_csv: str, den_csv: str, param: str, op: str = ">=") -> _Filter:
    """Filter on an ad-hoc quotient table num/den (e.g. MA10/MA20), used as if it were a
    preformed Longi matrix. Aligns on tickers (rows) and daynum (cols); cells are NaN
    where either side is missing or the denominator is zero. Keeps `quotient <op> PARAMS[param]`."""
    def build() -> pd.DataFrame:
        num = load_longi(num_csv)
        den = load_longi(den_csv)
        return num.divide(den.replace(0, float("nan")))
    return _Filter(build, param, op, f"{num_csv}/{den_csv}")


# ---------------------------------------------------------------------------
# Ranker spec — how to order survivors in the final pick
# ---------------------------------------------------------------------------

class _Ranker:
    """The final ordering step. Produces a series over the survivors where SMALLER == better,
    so it plugs straight into pick_by_rank. A descending ranker (larger == better, e.g.
    highest FKplus) is realised by negating the source values.
    """

    def __init__(self, csv_name: str, ascending: bool):
        self.csv_name  = csv_name
        self.ascending = ascending
        self._df: pd.DataFrame | None = None

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = load_longi(self.csv_name)
        return self._df

    def order_series(self, daynum: int, survivors: set[str]) -> pd.Series:
        """Rank-bearing series (smaller == better) over the survivors at daynum.
        Empty if the column is absent."""
        col = str(daynum)
        if col not in self.df.columns:
            return pd.Series(dtype=float)
        series = self.df.loc[self.df.index.isin(survivors), col].dropna()
        return series if self.ascending else -series


def rank_by(csv_name: str = "longi_rank.csv", ascending: bool = True) -> _Ranker:
    """Ranker spec for the final pick.

    ascending=True  (default) -> smaller-is-better, e.g. rank_by("longi_rank.csv").
    ascending=False           -> larger-is-better, e.g. rank_by("longi_FKplus.csv", ascending=False)
                                  to pick the highest-FKplus survivors.
    The from_rank window (1=best n, k>1=skip top, -1=worst n) applies in either direction.
    """
    return _Ranker(csv_name, ascending)


# ---------------------------------------------------------------------------
# Shared per-hop helpers (identical across every strategy)
# ---------------------------------------------------------------------------

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


def get_reference_values(daynum: int) -> dict[str, float]:
    """
    Market context at the investment daynum.
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


def _hop_avg(gains: dict[str, float]) -> float:
    vals = [v for v in gains.values() if pd.notna(v)]
    return sum(vals) / len(vals) if vals else float("nan")


# ---------------------------------------------------------------------------
# Strategy factory
# ---------------------------------------------------------------------------

def make_strategy(strategy_name: str, params: dict, filters: list[_Filter],
                  ranker: _Ranker | None = None):
    """
    Build the (main, build_extension) callable pair for one filter-based strategy.

    `params` MUST be the module-level PARAMS dict (the engine reads it live so the sweep's
    in-place override is honoured). `filters` is a list of col_filter/quotient_filter specs,
    intersected as survivors. `ranker` orders the survivors (default longi_rank ascending).
    """
    if ranker is None:
        ranker = rank_by()

    # n_survivors is recorded (and rendered as the N_survivors report row) only when more
    # than one filter is in play — matching the historical behaviour of the cross strategies.
    track_survivors = len(filters) >= 2

    def survivors(daynum: int) -> set[str]:
        """Tickers passing every filter at daynum. Empty if any source lacks the column."""
        result: set[str] | None = None
        for f in filters:
            q = f.qualifying(daynum, params)
            if q is None:
                return set()
            result = q if result is None else (result & q)
            if not result:
                return set()
        return result if result is not None else set()

    def select_focusset(daynum: int) -> list[str]:
        """Survivors ordered by the ranker, then the from_rank window applied."""
        surv = survivors(daynum)
        if not surv:
            return []
        order = ranker.order_series(daynum, surv)
        if order.empty:
            return []
        n = params["focusset_size"]
        return pick_by_rank(order, n, params.get("from_rank", 1))

    def find_start_daynum(gain_df: pd.DataFrame, min_valid: int = 10) -> int:
        """First daynum (newest first) where gains, the ranker, and every filter have data."""
        for col in gain_df.columns:
            daynum = int(col)
            scol = str(daynum)
            has_gain = gain_df[col].dropna().size >= min_valid
            has_rank = scol in ranker.df.columns and ranker.df[scol].dropna().size >= min_valid
            has_filt = all(scol in f.df.columns for f in filters)
            if has_gain and has_rank and has_filt:
                return daynum
        sources = ", ".join([gain_df.columns.name or "future_gain", ranker.csv_name]
                            + [f.label for f in filters])
        raise ValueError(f"No valid starting daynum found — check: {sources}")

    def main() -> None:
        period: int = params.get("period", 20)
        gain_df     = load_longi(f"future_gain{period}d.csv")

        n: int    = params["focusset_size"]
        step: int = params["step"]

        start_daynum = find_start_daynum(gain_df)
        min_daynum = max(
            [int(gain_df.columns[-1]), int(ranker.df.columns[-1])]
            + [int(f.df.columns[-1]) for f in filters]
        )

        print(f"--- {strategy_name} ---")
        print(f"Start daynum : {start_daynum} ({daynum_to_date(start_daynum)})")
        print(f"Min daynum   : {min_daynum}")
        print(f"Focusset size: {n}   Step: {step}   Period: {period}d   Filters: {len(filters)}")
        print()

        hop_results: list[dict] = []
        skipped = 0
        daynum = start_daynum

        while daynum >= min_daynum:
            tickers = select_focusset(daynum)
            if not tickers:
                # Record the no-pick day so it stays visible in HopData and the ladder counts
                # it as a cash slot (NaN gain -> cash, excluded from the chain).
                skipped += 1
                hop: dict = {
                    "daynum": daynum,
                    "tickers": [],
                    "gains": {},
                    "ref_values": get_reference_values(daynum),
                }
                if track_survivors:
                    hop["n_survivors"] = len(survivors(daynum))
                hop_results.append(hop)
                daynum -= step
                continue

            gains = get_gains(gain_df, tickers, daynum)
            avg = _hop_avg(gains)

            hop = {
                "daynum": daynum,
                "tickers": tickers,
                "gains": gains,
                "ref_values": get_reference_values(daynum),
            }
            if track_survivors:
                hop["n_survivors"] = len(survivors(daynum))
            hop_results.append(hop)
            daynum -= step

        print()
        if track_survivors:
            print(f"Days with no qualifying focusset: {skipped}")
        if not hop_results:
            print("No valid hops produced — no tickers passed the filters in the data range")
            sys.exit(1)

        save_report(strategy_name, params, hop_results)

        n_hops = len(hop_results)
        print(f"Done: {n_hops} hops  "
              f"daynum {hop_results[0]['daynum']} → {hop_results[-1]['daynum']}")

    def build_extension(workbook=None):
        from shared.extension import run_extension
        return run_extension(strategy_name, params, select_focusset,
                             get_reference_values, workbook=workbook)

    return main, build_extension
