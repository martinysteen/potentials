"""
The potrank2.csv column specification — the single source of truth.

Derived from potrank/schema.xlsx (SM's design), cross-checked against the live
repositoryRTBI/data/PotRank.csv export during the 2026-08-25 planning session. schema.xlsx
is authoritative: PerfPoint / Either / RSI-3d / RSI-4d / MACD-3d / MACD-4d (present in the
old manual export, absent from schema.xlsx) are dropped; P/MA20 and P/MA200 (in schema.xlsx,
absent from the old export) are added.

Both potrank.py (the builder) and preflight.py (the input-file guard) import COLUMNS, so the
required-files list can never drift from what the builder actually reads — see
`required_files()` at the bottom.

Column kinds
------------
  ticker   the row key itself (handled specially by potrank.py, not a COLUMNS entry)
  longi    `Longi/longi_<arg>.csv`, column at position `offset` (0=newest/today,
           1=one trading day back, 2=two back — matrices are newest-left, so this is a
           plain positional read, no daynum arithmetic)
  stam     Stamdata.csv column named `arg`
  yf       Yfinance/Yfinance.csv column named `arg`
  calc     computed here: "GICS" or "Sector2" top-100 membership count (see potrank.py)
  yahoo    the ticker repeated (schema.xlsx's Yahoo1/2/3 — GS hyperlink helper columns,
           SM chose to keep them for potrank2.csv column-count parity with schema.xlsx)
  empty    always blank (schema.xlsx's Mrk column)

`fmt` says how potrank.py renders the value: "num" -> f"{v:.3f}" with a comma decimal,
NaN -> ""; "text" -> passthrough, NaN -> "".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    header: str          # output CSV header (schema.xlsx's "Col-header")
    kind: str             # "longi" | "stam" | "yf" | "calc" | "yahoo" | "empty"
    arg: str = ""          # longi metric name / Stamdata column / Yfinance column / calc group
    offset: int = 0        # longi only: 0/1/2 trading days back
    fmt: str = "num"       # "num" | "text"


# Column 1 (the ticker / row key) is handled specially by potrank.py — its header is the
# build timestamp + daynum, not a fixed name — and is therefore not listed here. COLUMNS
# holds columns 2-68 of schema.xlsx, in schema order.
COLUMNS: list[Column] = [
    Column("RankNow", "longi", "rank", 0),
    Column("RankYd", "longi", "rank", 1),
    Column("Close", "longi", "price", 0),
    Column("Chg", "longi", "per1d", 0),
    Column("Name", "stam", "Name", fmt="text"),
    Column("Stamnote", "stam", "StamNote", fmt="text"),
    Column("SR3md", "longi", "sh3m", 0),
    Column("SR6md", "longi", "sh6m", 0),
    Column("SR1yr", "longi", "sh1yr", 0),
    Column("Beta3md", "longi", "beta3m", 0),
    Column("Beta6md", "longi", "beta6m", 0),
    Column("Beta1yr", "longi", "beta1yr", 0),
    Column("Per1d", "longi", "per1d", 0),
    Column("Per1w", "longi", "per5d", 0),
    Column("Per2w", "longi", "per10d", 0),
    Column("Per1m", "longi", "per20d", 0),
    Column("Per3m", "longi", "per50d", 0),
    Column("Per6m", "longi", "per100d", 0),
    Column("Per1y", "longi", "per200d", 0),
    Column("Yahoo1", "yahoo", fmt="text"),
    Column("Link_Summary", "stam", "Link_Summary", fmt="text"),
    Column("Homeland", "stam", "Homeland", fmt="text"),
    Column("Zone", "stam", "Zone", fmt="text"),
    Column("PE", "stam", "PE", fmt="text"),
    Column("FK_analyse", "stam", "FK_analyse", fmt="text"),
    Column("FKplus", "stam", "FKplus", fmt="text"),
    Column("Yield", "stam", "Yield", fmt="text"),
    Column("GrType", "stam", "GrType", fmt="text"),
    Column("P/MA20", "longi", "PdivMA20", 0),
    Column("P/MA50", "longi", "PdivMA50", 0),
    Column("P/MA200", "longi", "PdivMA200", 0),
    Column("Cr1020", "longi", "quot1020", 0),
    Column("Cr2050", "longi", "quot2050", 0),
    Column("Spr100", "longi", "spr100d", 0),
    Column("Spr250", "longi", "spr250d", 0),
    Column("Vola20", "longi", "vola20d", 0),
    Column("Vola100", "longi", "vola100d", 0),
    Column("Trump", "longi", "trump", 0),
    Column("Iran", "longi", "iran", 0),
    Column("Yahoo2", "yahoo", fmt="text"),
    Column("GICS", "stam", "GICS", fmt="text"),
    Column("GICS i top100", "calc", "GICS"),
    Column("Sector2", "stam", "Sector2", fmt="text"),
    Column("Sector2 i top100", "calc", "Sector2"),
    Column("Sgrp1", "stam", "Sgrp1", fmt="text"),
    Column("RSI-today", "longi", "rsi", 0),
    Column("RSI-1d", "longi", "rsi", 1),
    Column("RSI-2d", "longi", "rsi", 2),
    Column("MACD-today", "longi", "macd_histogram", 0),
    Column("MACD-1d", "longi", "macd_histogram", 1),
    Column("MACD-2d", "longi", "macd_histogram", 2),
    # Z-today/Z-1d: longi_macd_Z.csv legitimately carries non-numeric marker strings
    # ("ZOP", "ZNED") instead of a score for some cells -- confirmed with SM, not a data
    # error. fmt stays "num"; potrank.py's _fmt_num passes anything that fails float()
    # through as-is rather than blanking it, so these markers reach potrank2.csv intact.
    Column("Z-today", "longi", "macd_Z", 0),
    Column("Z-1d", "longi", "macd_Z", 1),
    Column("median_10d", "longi", "median_10d", 0),
    Column("median_20d", "longi", "median_20d", 0),
    Column("median_30d", "longi", "median_30d", 0),
    Column("median_50d", "longi", "median_50d", 0),
    Column("median_100d", "longi", "median_100d", 0),
    Column("StepUp40", "longi", "stepup40", 0),
    Column("StepUp100", "longi", "stepup100", 0),
    Column("Yahoo3", "yahoo", fmt="text"),
    Column("Close", "longi", "price", 0),  # intentional repeat of column 4, per schema.xlsx
    Column("Target_Median", "yf", "Target_Median"),
    Column("Target_High", "yf", "Target_High"),
    Column("Recomm_Mean", "yf", "Recomm_Mean"),
    Column("Recomm_Key", "yf", "Recomm_Key", fmt="text"),
    Column("Mrk", "empty", fmt="text"),
]

# Top-100 cut for the two "i top100" calc columns: rank <= this is a member (SM, 2026-08-25).
TOP100_RANK = 100


def required_longi_files() -> list[str]:
    """Every `Longi/longi_*.csv` potrank reads, deduplicated, repo-relative."""
    names = {c.arg for c in COLUMNS if c.kind == "longi"}
    names.add("rank")  # also needed for the two calc columns' top-100 cut
    return sorted(f"Longi/longi_{name}.csv" for name in names)


def required_files() -> tuple[list[str], list[str]]:
    """(required, optional) repo-relative paths, for preflight.py.

    Stamdata.csv and every longi_* file are required — the run cannot produce a coherent
    row without them. Yfinance/Yfinance.csv is optional: yf3 runs on its own schedule (see
    root CLAUDE.md's daily chain) and a stale or missing snapshot should degrade the four
    Yfinance-sourced columns to blank rather than block the whole file.
    """
    required = ["Stamdata.csv"] + required_longi_files()
    optional = ["Yfinance/Yfinance.csv"]
    return required, optional
