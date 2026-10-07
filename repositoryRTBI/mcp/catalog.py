"""
catalog.py - which repositoryRTBI files the MCP server exposes, what they mean,
and how to load them.

Read-only consumer of the local mirror (repositoryRTBI/data/). Never Google
Drive, never writes. Files are discovered on every call, so a new longi_*.csv
shows up without a code change; the descriptions below only add meaning.

Two kinds:
  matrix  rows = tickers (or sector names for longi_grp_*), columns = daynums
          as strings, newest LEFT. PotDat.csv and Longi/longi_*.csv.
  table   ordinary rows, keyed by their first column (ticker), e.g. Stamdata.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "app" / "code"))
import repository  # noqa: E402  - stdlib-only; reused for MIRROR_ROOT
import potdat_gatekeeper as gatekeeper  # noqa: E402  - every PotDat read goes through it

DATA = repository.MIRROR_ROOT


class DataError(Exception):
    """A request the data cannot answer - message is meant for the LLM caller."""


@dataclass(frozen=True)
class Dataset:
    name: str
    path: Path
    kind: str          # "matrix" | "table"
    description: str


# --------------------------------------------------------------------------- #
# descriptions                                                                #
# --------------------------------------------------------------------------- #

_SEVEN = "seven-pack horizon (1/5/10/20/50/100/200 trading days)"

# (regex on dataset name, description template) - first match wins.
_MATRIX_DESCRIPTIONS: list[tuple[str, str]] = [
    (r"PotDat$", "Daily closing prices, the system's root price table (source of everything else)."),
    (r"longi_price$", "Daily closing prices - longi's snapshot of PotDat.csv for its latest run."),
    (r"longi_future_per(\d+)d$", "FORWARD {0}-day % gain, entering at signal day + 1. This is the "
     "OUTCOME (look-ahead) - never use it as a predictor for the same day."),
    (r"longi_future_minaggr(\d+)d$", "FORWARD worst drawdown % (<= 0) within {0} days after entry "
     "at signal day + 1. Outcome / look-ahead, the risk twin of longi_future_per{0}d."),
    (r"longi_grp_(\w+)_per(\d+)d$", "SECTOR-level trailing {1}-day % gain, grouped by Stamdata "
     "column {0}. Rows are sector names, not tickers."),
    (r"longi_per(\d+)d$", "Trailing {0}-day % gain (" + _SEVEN + ")."),
    (r"longi_rank$", "Average rank across the seven trailing per* horizons (lower = stronger)."),
    (r"longi_median_(\d+)d$", "{0}-day rolling median of longi_rank (lower = stronger)."),
    (r"longi_stepup(\d+)$", "Step-up count 0-3 on the rank-median ladder up to {0}d (3 = clean uptrend)."),
    (r"longi_spr(\d+)d$", "Spread to the {0}-day high: % gain needed to get back to it."),
    (r"longi_vola(\d+)d$", "{0}-day volatility, stdev of daily returns in %."),
    (r"longi_ma(\d+)$", "{0}-day simple moving average of price."),
    (r"longi_PdivMA(\d+)$", "Price / MA{0} x 100 (>100 = above the average)."),
    (r"longi_sh(\w+)$", "Sharpe ratio over {0} (return / volatility)."),
    (r"longi_quot(\d\d)(\d\d)$", "MA{0} / MA{1} x 100, momentum speed (>100 = accelerating)."),
    (r"longi_rsi$", "RSI14 (Wilder)."),
    (r"longi_macd_(line|signal|histogram)$", "MACD(4,15,9) {0}."),
    (r"longi_macd_Z$", "MACD histogram zero-crossings: ZOP = crossed up, ZNED = crossed down, blank = none. Text, not numbers."),
    (r"longi_coreindexRSI$", "RSI of the ticker's CoreIndex (from Stamdata), copied onto the ticker."),
    (r"longi_coreindex$", "Price of the ticker's CoreIndex (from Stamdata), copied onto the ticker."),
    (r"longi_beta(\w+)$", "Beta vs the ticker's own CoreIndex over {0}."),
    (r"longi_regrfit(\d+)d$", "R^2 x 100 of a log-price trend fit over {0} days (how well constant growth describes it)."),
    (r"longi_regr(\d+)d$", "Trend gain % over {0} days from an OLS fit of log(price) on time."),
    (r"longi_trump$", "Price rebased to 1.0 at daynum 1863 (2 Apr 2025, tariff announcement); blank before."),
    (r"longi_iran$", "Price rebased to 1.0 at daynum 2094 (27 Feb 2026, before the Iran war); blank before."),
    (r"longi_conf_(\w+)$", "Conformity: rolling leave-one-out correlation of the ticker's daily gain with its {0} group."),
    (r"longi_sectorbeta_(\w+)$", "Beta of the ticker vs its {0} group."),
]

# table name -> (relative path or glob for the newest daynum, description)
_TABLES: dict[str, tuple[str, str]] = {
    "Stamdata": ("Stamdata.csv", "Master data, one row per ticker: Name, Sector, Sector2, GICS, "
                 "Homeland, Zone, CoreIndex, Valuta, notes. The system-wide ticker list."),
    "potrank2": ("potrank2.csv", "PotRank snapshot, one row per ticker: RankNow, Close, trailing "
                 "gains, Sharpe, beta, P/MA, PE, yield. The header's first cell is the as-of time."),
    "Google": ("Google.csv", "Latest Google Finance quote per ticker: Close, Yesterday, ChgPct, EPS, PE, DPS, Yield."),
    "StrategicStocks": ("Strategy/StrategicStocks_*.csv", "Today's strategy picks from strategy_grp2 "
                        "--production (newest daynum): label, priority, ticker, name, group, attributes."),
    "across": ("Longi/across_*.csv", "Every longi factor for every ticker on the newest daynum, one row per ticker."),
    "Yfinance": ("Yfinance/Yfinance.csv", "Analyst targets and recommendations per ticker (latest yFinance fetch)."),
    "StockData2_stacked": ("Yfinance/StockData2_stacked.csv", "yFinance fundamentals HISTORY, "
                           "many rows per ticker (Symbol, Daynum, Date, PE, EPS, targets, ...). Filter by ticker."),
}


def _describe_matrix(name: str) -> str:
    for pattern, template in _MATRIX_DESCRIPTIONS:
        m = re.match(pattern, name)
        if m:
            return template.format(*m.groups())
    return "Longi factor table (no description registered)."


# --------------------------------------------------------------------------- #
# discovery                                                                   #
# --------------------------------------------------------------------------- #

def datasets() -> dict[str, Dataset]:
    found: dict[str, Dataset] = {}
    matrix_paths = [DATA / "PotDat.csv", *sorted((DATA / "Longi").glob("longi_*.csv"))]
    for p in matrix_paths:
        if p.exists():
            found[p.stem] = Dataset(p.stem, p, "matrix", _describe_matrix(p.stem))
    for name, (rel, desc) in _TABLES.items():
        hits = sorted(DATA.glob(rel))
        if hits:
            found[name] = Dataset(name, hits[-1], "table", desc)
    return found


def get(name: str) -> Dataset:
    all_ds = datasets()
    if name in all_ds:
        return all_ds[name]
    stem = name[:-4] if name.lower().endswith(".csv") else name
    for key, ds in all_ds.items():
        if key.lower() == stem.lower():
            return ds
    close = [k for k in all_ds if stem.lower() in k.lower()][:10]
    raise DataError(f"Unknown dataset '{name}'. "
                    + (f"Did you mean: {', '.join(close)}? " if close else "")
                    + "Call list_datasets for the full list.")


# --------------------------------------------------------------------------- #
# loading - cached on (path, mtime), guarded against mid-write files          #
# --------------------------------------------------------------------------- #

_cache: dict[Path, tuple[float, pd.DataFrame]] = {}


def load(ds: Dataset) -> pd.DataFrame:
    mtime = ds.path.stat().st_mtime
    hit = _cache.get(ds.path)
    if hit and hit[0] == mtime:
        return hit[1]
    problem = (gatekeeper.admit(ds.path).problem if ds.name == "PotDat"
               else gatekeeper.looks_intact(ds.path))
    if problem:
        raise DataError(f"{problem} - the file is probably being rewritten right now; retry in a minute.")
    df = pd.read_csv(ds.path, sep=";", decimal=",", index_col=0, encoding="utf-8-sig",
                     low_memory=False)
    df.index = df.index.astype(str)
    if ds.kind == "matrix":
        df.columns = [str(c) for c in df.columns]
    _cache[ds.path] = (mtime, df)
    return df


_carry_cache: dict[Path, tuple[float, gatekeeper.CarryMarker]] = {}


def carried_newest(ds: Dataset, tickers: list[str]) -> list[str]:
    """Which of `tickers` have a PROVISIONAL newest value in `ds`: their market had not
    traded on that day yet (or is closed), so the price is the previous close copied and
    longi's readings are the previous day's carried. Judged by the PotDat gatekeeper on
    the price file the dataset was built from - PotDat itself, or longi_price.csv (longi's
    exact PotDat snapshot) for the longi_* tables. Sector and forward tables don't apply."""
    if ds.kind != "matrix" or ds.name.startswith(("longi_grp_", "longi_future_")):
        return []
    ref = ds.path if ds.name == "PotDat" else DATA / "Longi" / "longi_price.csv"
    try:
        mtime = ref.stat().st_mtime
        hit = _carry_cache.get(ref)
        if not (hit and hit[0] == mtime):
            adm = gatekeeper.admit(ref)
            if not adm.ok:
                return []
            hit = (mtime, adm.carry)
            _carry_cache[ref] = hit
    except OSError:
        return []
    return [t for t in tickers if hit[1].carried(t)]


def calendar() -> pd.Series:
    """daynum (int) -> Timestamp."""
    cal = pd.read_csv(DATA / "Cal.csv", sep=";", decimal=",")
    return pd.Series(pd.to_datetime(cal["Date"]).values, index=cal["Daynum"].astype(int))


def resolve_rows(df: pd.DataFrame, wanted: list[str]) -> list[str]:
    """Case-insensitive row-label match; unknown labels raise with a hint."""
    lookup = {label.upper(): label for label in df.index}
    rows, missing = [], []
    for w in wanted:
        hit = lookup.get(w.strip().upper())
        (rows if hit else missing).append(hit or w)
    if missing:
        raise DataError(f"Not found in this dataset: {', '.join(missing)}. Tickers are Yahoo-style "
                        "(e.g. NOVO-B.CO, ^GSPC); use search_tickers to find the right one.")
    return rows
