"""
tunnel_hist.py - query layer over Tunnel/history/tunnels_history_LB100.csv for the MCP tool
`tunnel_history`.

The file is long format (one row per daynum x ticker, ~0.9M rows, 80 MB). It is far too big to
hand to a model whole (tens of millions of tokens), so the caller asks a NARROW question and the
server does the scanning: filter on any column across all tickers and dates, then either return up
to MAX_ROWS matching rows (the newest; the COMPLETE match goes to a download link), or a summary (count + means) grouped by date / month / ticker / status.
Every answer says how many rows matched, so the caller knows when it has seen only part.

Read-only consumer of the local mirror (like catalog.py). Parsed once per file version and kept
in memory (one entry only, so a nightly rewrite replaces it rather than doubling it).
"""
from __future__ import annotations

import operator
import re

import pandas as pd

from catalog import DATA, DataError, gatekeeper

MAX_ROWS = 500
MAX_GROUPS = 500
CORE_COLUMNS = ["end_date", "ticker", "status", "length_td", "width_pct", "slope20_pct", "close_pos"]
SUMMARY_COLUMNS = ["length_td", "width_pct", "slope20_pct", "close_pos"]
SUMMARY_KEYS = ("date", "month", "ticker", "status")

_DIR = DATA / "Tunnel" / "history"
_COND = re.compile(r"^\s*([A-Za-z_0-9]+)\s*(>=|<=|==|!=|=|>|<)\s*(.+?)\s*$")
_cache: dict = {}          # at most one entry: {"path", "mtime", "df"}


def path():
    hits = sorted(_DIR.glob("tunnels_history_LB*.csv"))
    if not hits:
        return None
    return next((p for p in hits if p.name.endswith("LB100.csv")), hits[-1])


def available() -> bool:
    return path() is not None


def load() -> pd.DataFrame:
    p = path()
    if p is None:
        raise DataError("The tunnel history file is not in the mirror yet.")
    mtime = p.stat().st_mtime
    if _cache.get("path") == p and _cache.get("mtime") == mtime:
        return _cache["df"]
    problem = gatekeeper.looks_intact(p)
    if problem:
        raise DataError(f"{problem} - the file is probably being rewritten right now; retry in a minute.")
    df = pd.read_csv(p, sep=";", decimal=",", encoding="utf-8-sig", low_memory=False)
    df = df.rename(columns={df.columns[0]: "daynum"})       # header cell of col 0 is the creation stamp
    df["ticker"] = df["ticker"].astype("category")
    df["status"] = df["status"].astype("category")
    for c in ("start_date", "end_date"):
        df[c] = pd.to_datetime(df[c])
    _cache.clear()
    _cache.update(path=p, mtime=mtime, df=df)
    return df


def _date(value: str, end: bool) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except ValueError:
        raise DataError(f"Cannot read date '{value}'. Use YYYY-MM-DD or YYYY-MM.")
    return ts + pd.offsets.MonthEnd(0) if end and len(value) <= 7 else ts


def _unknown(bad, df: pd.DataFrame, visible: list) -> str:
    bad = [bad] if isinstance(bad, str) else bad
    extra = [c for c in bad if c in df.columns]          # real columns, just not in the core set
    if extra:
        return (f"Column(s) {extra} are only available with extended=true. "
                f"Core columns: {CORE_COLUMNS}")
    return f"Unknown column(s) {bad}. Available: {visible}"


def _condition(df: pd.DataFrame, text: str, visible: list) -> pd.Series:
    m = _COND.match(text)
    if not m:
        raise DataError(f"Cannot read filter '{text}'. Use 'column operator value', e.g. 'close_pos >= 0.9' "
                        "or 'status = tunnel' (operators: > >= < <= = !=).")
    col, op, raw = m.groups()
    if col not in visible:
        raise DataError(_unknown(col, df, visible))
    op = "==" if op == "=" else op
    s = df[col]
    raw = raw.strip("'\"")
    if pd.api.types.is_datetime64_any_dtype(s):
        v = _date(raw, end=False)
    elif pd.api.types.is_numeric_dtype(s):
        try:
            v = float(raw.replace(",", "."))
        except ValueError:
            raise DataError(f"'{col}' is numeric; '{raw}' is not a number.")
    else:
        if op not in ("==", "!="):
            raise DataError(f"'{col}' is text; only = and != apply.")
        v = raw if col != "ticker" else raw.upper() if raw.upper() in set(s.cat.categories) else raw
    return {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
            "==": operator.eq, "!=": operator.ne}[op](s, v)


def query(tickers=None, start=None, end=None, where=None, columns=None, sort=None,
          limit=100, summarize=None, extended=False) -> dict:
    df = load()
    visible = list(df.columns) if extended else CORE_COLUMNS
    mask = pd.Series(True, index=df.index)
    if tickers:
        known = {t.upper(): t for t in df["ticker"].cat.categories}
        wanted = [known.get(t.strip().upper()) for t in tickers]
        missing = [t for t, w in zip(tickers, wanted) if w is None]
        if missing:
            raise DataError(f"Not in the tunnel history: {', '.join(missing)}. Use search_tickers "
                            "to find the Yahoo-style ticker.")
        mask &= df["ticker"].isin(wanted)
    if start:
        mask &= df["end_date"] >= _date(start, end=False)
    if end:
        mask &= df["end_date"] <= _date(end, end=True)
    for cond in where or []:
        mask &= _condition(df, cond, visible)
    sub = df[mask]
    matched = len(sub)
    meta = {"rows_matched": matched,
            "history_from": df["end_date"].min().strftime("%Y-%m-%d"),
            "history_to": df["end_date"].max().strftime("%Y-%m-%d")}

    if summarize:
        if summarize not in SUMMARY_KEYS:
            raise DataError(f"summarize must be one of {SUMMARY_KEYS}.")
        if matched == 0:
            return {**meta, "summary_by": summarize, "columns": [], "rows": []}
        keycol = {"date": sub["end_date"].dt.strftime("%Y-%m-%d"),
                  "month": sub["end_date"].dt.strftime("%Y-%m"),
                  "ticker": sub["ticker"], "status": sub["status"]}[summarize]
        cols = columns or SUMMARY_COLUMNS
        bad = [c for c in cols if c not in visible or not pd.api.types.is_numeric_dtype(df[c])]
        if bad:
            raise DataError(f"Summary columns must be numeric columns; not usable: {bad}.")
        g = sub[cols].groupby(keycol.rename(summarize), observed=True)
        out = g.mean().round(2)
        out.insert(0, "n", g.size())
        if len(out) > MAX_GROUPS:
            raise DataError(f"{len(out)} groups (limit {MAX_GROUPS}). Narrow the dates, or summarize "
                            "by 'month' instead of 'date'.")
        out = out.reset_index()
        out.columns = [summarize, "n"] + [f"mean_{c}" for c in cols]
        rows = out.astype(object).where(out.notna(), None).values.tolist()
        return {**meta, "summary_by": summarize, "groups": len(rows),
                "columns": list(out.columns), "rows": rows}

    cols = columns or CORE_COLUMNS
    unknown = [c for c in cols if c not in visible]
    if unknown:
        raise DataError(_unknown(unknown, df, visible))
    if sort:
        desc = sort.startswith("-")
        key = sort.lstrip("-+")
        if key not in visible:
            raise DataError(_unknown(key, df, visible))
        sub = sub.sort_values(key, ascending=not desc, kind="stable", na_position="last")
    else:
        sub = sub.sort_values(["end_date", "ticker"], kind="stable")      # oldest first
    limit = max(1, min(limit, MAX_ROWS))
    # Truncated without an explicit sort: the NEWEST rows are returned (SM, 2026-10-29), still
    # in date order. With a sort, the first rows of that sort.
    shown = sub.head(limit) if sort else sub.tail(limit)
    out = _present(shown[cols])
    res = {**meta, "rows_returned": len(out), "columns": cols,
           "rows": out.astype(object).where(out.notna(), None).values.tolist()}
    if matched > len(out):
        link = _export(_present(sub[cols]), matched)
        res["note"] = (f"Only {len(out)} of {matched} matching rows are shown "
                       f"({'first by ' + sort if sort else 'the newest'}). Narrow the filter or dates, "
                       "use summarize (date/month/ticker/status) for counts and means, or fetch the "
                       "complete result from download_url if you can download files / run code.")
        res.update(link)
    return res


def _present(frame: pd.DataFrame) -> pd.DataFrame:
    """Dates as YYYY-MM-DD text, floats rounded - the same shape in the reply and in the export."""
    frame = frame.copy()
    for c in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[c]):
            frame[c] = frame[c].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_float_dtype(frame[c]):
            frame[c] = frame[c].round(4)
    return frame


def _export(frame: pd.DataFrame, n: int) -> dict:
    """The COMPLETE result as a CSV in a folder of its own, served read-only like tunnel_report's
    (random token in the link, deleted after 7 days). Standard CSV: comma, decimal point."""
    import secrets
    import tunnel_ondemand as ondemand        # shares the served root, URL and the 7-day cleanup
    ondemand.ROOT.mkdir(parents=True, exist_ok=True)
    ondemand._cleanup(ondemand.ROOT)
    folder = ondemand.ROOT / f"tunnel_history_{secrets.token_urlsafe(9)}"
    folder.mkdir()
    name = f"tunnel_history_{n}rows.csv"
    frame.to_csv(folder / name, index=False)
    return {"download_url": f"{ondemand.URL}/{folder.name}/{name}",
            "download_note": f"All {n} matching rows, columns as above, standard CSV (comma, decimal "
                             "point), same order as the rows here. The link works for anyone holding "
                             "it and expires after 7 days."}
