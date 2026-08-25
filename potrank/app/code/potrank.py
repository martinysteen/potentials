"""
Build potrank2.csv — the wide, one-row-per-ticker snapshot that replaces the PotRank Google
Sheet's own calculations. See potrank/CLAUDE.md for the column spec's rationale; the spec
itself lives in columns.py, imported here and by preflight.py so the two can never drift.

    python potrank.py               # preflight -> snapshot -> build -> write app/output/potrank2.csv
    python potrank.py --stale-ok    # fall back to the last good snapshot if live data is incoherent
    python potrank.py --live        # read the live repository unguarded (ad-hoc inspection only)

Exit 0 on a written file, 1 on DataUnavailable (preflight already printed the full table).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from shared import config, data_loader
from shared.datacheck import DataUnavailable
import columns
import preflight


def _longi_col(name: str, offset: int) -> pd.Series:
    """Column `offset` of longi_<name>.csv — 0=newest, 1=one trading day back, 2=two back.
    Matrices are newest-left (system convention), so this is a plain positional read, no
    daynum arithmetic. Returns an all-NaN series if the matrix is somehow narrower than
    `offset` needs — defensive; every file in columns.py's spec has thousands of columns."""
    mat = data_loader.load_longi(f"longi_{name}.csv")
    if offset >= mat.shape[1]:
        return pd.Series(index=mat.index, dtype="float64")
    return mat.iloc[:, offset]


def _stamdata_by_ticker() -> pd.DataFrame:
    """Stamdata.csv indexed by ticker. Its own first column's header is a timestamp, not a
    label (see longi/app/code/aux_grp_shared.py's load_ticker_to_group for the same idiom) —
    addressed by position, not by name. A duplicated ticker keeps its first occurrence;
    ^-prefixed index tickers (^GSPC, ^VIX, ...) are dropped — potrank ranks tradeable stocks,
    not benchmarks, matching the row set the old PotRank.csv export already had."""
    stam = data_loader.load_stamdata()
    ticker_col = stam.columns[0]
    df = stam.rename(columns={ticker_col: "ticker"})
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df = df[df["ticker"] != ""]
    df = df.drop_duplicates(subset="ticker", keep="first")
    df = df[~df["ticker"].str.startswith("^")]
    return df.set_index("ticker")


def _top100_counts(group_col: str, tickers: list[str], stam: pd.DataFrame,
                    rank: pd.Series) -> pd.Series:
    """schema.xlsx's 'GICS i top100' / 'Sector2 i top100': every ticker carries the count of
    top-`columns.TOP100_RANK`-ranked tickers sharing its own `group_col` value (so all
    members of one group show the same number). A group with no top-100 member gets 0, not
    blank — confirmed against the same convention in the live PotRank.csv sample
    (";Basi;35,000;Gold;18,000;" — the count is written with the file's usual 3-decimal
    formatting, not as a bare int)."""
    top100 = rank[rank <= columns.TOP100_RANK].index
    group = stam[group_col].reindex(tickers)
    counts = group.reindex(top100).value_counts()
    return group.map(counts).fillna(0).astype(int)


def _fmt_num(v) -> str:
    """Format a numeric cell. `longi_macd_Z.csv` legitimately carries non-numeric marker
    strings ("ZOP", "ZNED") instead of a Z-score for some ticker/daynum cells -- confirmed
    with SM, not a data error. Those (and anything else that fails float()) pass through
    as-is rather than blanking or crashing: they are meaningful content in Z-today/Z-1d,
    not missing data."""
    if pd.isna(v):
        return ""
    try:
        return f"{float(v):.3f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def _fmt_text(v) -> str:
    if pd.isna(v):
        return ""
    return str(v)


def build() -> pd.DataFrame:
    """Returns the fully formatted, sorted, string-valued DataFrame ready to write."""
    stam = _stamdata_by_ticker()
    unsorted_tickers = stam.index.tolist()

    rank = _longi_col("rank", 0).reindex(unsorted_tickers)
    # Ascending by RankNow, worst/unranked last — matches the old PotRank.csv export.
    tickers = rank.sort_values(na_position="last").index.tolist()
    rank = rank.reindex(tickers)

    yf = data_loader.load_yfinance()
    daynum = int(data_loader.load_longi("longi_rank.csv").columns[0])

    header1 = f"{datetime.now():%d-%m-%y %H.%M} ({daynum})"
    series_out: list[tuple[str, pd.Series]] = [(header1, pd.Series(tickers, index=tickers))]

    for col in columns.COLUMNS:
        if col.kind == "longi":
            raw = _longi_col(col.arg, col.offset).reindex(tickers)
        elif col.kind == "stam":
            raw = stam[col.arg].reindex(tickers)
        elif col.kind == "yf":
            raw = yf[col.arg].reindex(tickers)
        elif col.kind == "yahoo":
            raw = pd.Series(tickers, index=tickers)
        elif col.kind == "calc":
            raw = _top100_counts(col.arg, tickers, stam, rank)
        elif col.kind == "empty":
            raw = pd.Series([""] * len(tickers), index=tickers)
        else:
            raise ValueError(f"unknown column kind: {col.kind!r}")

        fmt_fn = _fmt_num if col.fmt == "num" else _fmt_text
        series_out.append((col.header, raw.map(fmt_fn)))

    df = pd.concat([s for _, s in series_out], axis=1)
    df.columns = [h for h, _ in series_out]  # tolerates the intentional duplicate "Close"
    return df.reset_index(drop=True)


def main() -> int:
    mode = preflight.mode_from_argv()
    try:
        preflight.ensure_data(mode=mode)
    except DataUnavailable as exc:
        print(f"ERROR: {exc}")
        return 1

    df = build()

    config.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.POTRANK2_PATH, sep=";", index=False, encoding="utf-8")
    print(f"Wrote {config.POTRANK2_PATH} ({len(df)} rows, {len(df.columns)} columns)")
    print(data_loader.load_manifest_line())
    return 0


if __name__ == "__main__":
    sys.exit(main())
