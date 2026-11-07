"""
server.py - Potentials data as an MCP server, for LLM chats and agent platforms.

    https://mcp.innovia.dk/mcp   (Caddy -> uvicorn 127.0.0.1:8766, systemd rtbi-mcp)

Tools answer questions instead of handing over files: daynums become dates,
newest-left becomes oldest-first, and resampling happens here - so "monthly gain
for MSFT and MU" is ~70 numbers, not two 700-column rows.

Auth is Google OAuth (FastMCP's OAuth proxy) plus an email allowlist, both from
.env next to this file. Without GOOGLE_CLIENT_ID the HTTP server refuses to start
unless RTBI_MCP_NO_AUTH=1 - an unauthenticated public server is never an accident.
In-memory use (smoke_test.py) imports `mcp` directly and needs no auth.
"""
from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path
from typing import Literal, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from dotenv import dotenv_values, load_dotenv  # noqa: E402
from fastmcp import FastMCP  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from fastmcp.server.dependencies import get_access_token  # noqa: E402
from fastmcp.server.middleware import Middleware, MiddlewareContext  # noqa: E402
from fastmcp.utilities.types import Image  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, PlainTextResponse  # noqa: E402

import catalog  # noqa: E402
import exports  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tunnel" / "app" / "code"))
import tunnel_ondemand  # noqa: E402  (stdlib + pandas only; runs tunnel_diag.py as a subprocess)
import tunnel_hist  # noqa: E402
from catalog import DataError  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger("rtbi-mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_POINTS = 6000      # tickers x dates returned by get_series / plot_series
MAX_ROWS = 300         # rows returned by get_table
PREVIEW_ROWS = 10      # inline preview (dates / tickers / rows) when download=true: the file is the answer
MAX_PLOT_SERIES = 8

CONVENTIONS = """\
Potentials data - conventions

- Tickers are Yahoo-style: MSFT, NOVO-B.CO, 0700.HK, ^GSPC (indices start with ^).
  Use search_tickers to go from a company name or sector to a ticker.
- A "daynum" is the system's trading-day counter; tools translate it to dates.
  The calendar is trading days only, so "20 days" means 20 trading days.
- Horizons come in a "seven-pack": 1/5/10/20/50/100/200 trading days. 20 is primary.
- longi_per{N}d = TRAILING N-day % gain (known on that day).
  longi_future_per{N}d = FORWARD N-day % gain, entering the day AFTER the signal day.
  The future_* tables are outcomes: never treat them as information available on that day.
- longi_grp_* tables have sector names as rows (GICS or Sector2), not tickers.
- Gains in this system are additive when chained (sum of lot gains), not compounded.
- Prices are in each ticker's own currency (Stamdata column Valuta).
- Data refreshes hourly 0-22 CET; get_series reports the newest date it saw.
- The newest day can be PROVISIONAL for a ticker whose market has not traded yet that day
  (or is closed): its price is the previous close copied, its longi readings are the
  previous day's carried. get_series lists such tickers in "provisional_newest".
"""

INSTRUCTIONS = ("Read-only access to the Potentials stock-analysis repository: daily prices "
                "(PotDat / longi_price), ~80 per-ticker factor tables (longi_*), master data "
                "(Stamdata), rankings (potrank2), today's strategy picks (StrategicStocks) and "
                "yFinance fundamentals. Start with list_datasets; read resource "
                "potentials://conventions before interpreting per/future_per tables.\n\n"
                + "\n\nBig answers: get_series, get_table and tunnel_history return small results inline; "
                "when the result is bigger than the inline limit (or download=true) they also return "
                "download_url - the COMPLETE result as a CSV (download=true = file only, with a 10-row preview). Fetching it needs the member's personal API "
                "key (create_api_key tool) as 'Authorization: Bearer <key>'.\n\n"
                + CONVENTIONS)


# --------------------------------------------------------------------------- #
# auth                                                                        #
# --------------------------------------------------------------------------- #

def _build_auth():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        return None
    from fastmcp.server.auth.providers.google import GoogleProvider
    return GoogleProvider(
        client_id=client_id,
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        base_url=os.environ.get("RTBI_MCP_BASE_URL", "https://mcp.innovia.dk"),
        jwt_signing_key=os.environ["RTBI_MCP_JWT_KEY"],
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    )


def _parse_emails(text: str) -> set[str]:
    return {e.strip().lower() for e in (text or "").split(",") if e.strip()}


ALLOWED = _parse_emails(os.environ.get("RTBI_MCP_ALLOWED_EMAILS", ""))


def _allowed_now() -> set[str]:
    """The allowlist as .env says RIGHT NOW (downloads must not wait for a restart: removing a
    member from .env kills their downloads at once). Falls back to the startup list."""
    env = Path(__file__).parent / ".env"
    try:
        if env.exists():
            return _parse_emails(dotenv_values(env).get("RTBI_MCP_ALLOWED_EMAILS", ""))
    except OSError:
        pass
    return ALLOWED


class AllowlistMiddleware(Middleware):
    """Google proves who the caller is; this decides whether they get in.
    Also the audit log: one line per tool call, with the caller's email."""

    async def on_request(self, context: MiddlewareContext, call_next):
        token = get_access_token()
        email = (token.claims.get("email") or "").lower() if token else ""
        if email not in ALLOWED:
            log.warning("refused %s (%s)", email or "<no email>", context.method)
            raise ToolError(f"Access denied for {email or 'unknown user'}. Ask sm@innovia.dk to be added.")
        if context.method == "tools/call":
            log.info("call %s %s %s", email, context.message.name, context.message.arguments)
        return await call_next(context)


_auth = _build_auth()
mcp = FastMCP("Potentials", instructions=INSTRUCTIONS, auth=_auth,
              middleware=[AllowlistMiddleware()] if _auth else [])


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #

def _fail(exc: DataError):
    raise ToolError(str(exc)) from exc


def _parse_date(value: Optional[str], end: bool) -> Optional[pd.Timestamp]:
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
    except ValueError:
        raise DataError(f"Cannot read date '{value}'. Use YYYY-MM-DD or YYYY-MM.")
    if end and len(value) <= 7:          # "2026-03" as an end means the whole month
        ts = ts + pd.offsets.MonthEnd(0)
    return ts


def _series_frame(dataset: str, tickers: list[str], start: Optional[str], end: Optional[str],
                  freq: str, transform: str, limit: bool = True) -> tuple[pd.DataFrame, catalog.Dataset]:
    """Long-history frame: index = dates oldest-first, one column per ticker.
    limit=False (get_series) skips the MAX_POINTS cap - the caller then truncates the inline
    part and offers the whole frame as a download."""
    ds = catalog.get(dataset)
    if ds.kind != "matrix":
        raise DataError(f"'{ds.name}' is a table, not a time series - use get_table.")
    if not tickers:
        raise DataError("Give at least one ticker.")
    df = catalog.load(ds)
    rows = list(df.index) if [t.strip() for t in tickers] == ["*"] else catalog.resolve_rows(df, tickers)
    cal = catalog.calendar()
    sub = df.loc[rows].T
    sub.index = [cal.get(int(d), pd.NaT) for d in sub.index]
    sub = sub[sub.index.notna()].sort_index()
    sub.index = pd.DatetimeIndex(sub.index)

    numeric = sub.apply(pd.to_numeric, errors="coerce")
    is_text = numeric.isna().all().all() and sub.notna().any().any()
    if is_text:
        if freq != "D" or transform != "level":
            raise DataError(f"'{ds.name}' holds text values; only freq='D', transform='level' apply.")
    else:
        sub = numeric

    s, e = _parse_date(start, end=False), _parse_date(end, end=True)
    partial_label = None
    # Resample/pct_change before cutting at `start`, so the first returned gain
    # is measured from the period before it rather than dropped as NaN.
    if freq != "D":
        rule = {"W": "W-FRI", "M": "ME"}[freq]
        last_day = sub.dropna(how="all").index.max()
        period = "W-FRI" if freq == "W" else "M"
        later = cal[(cal > last_day) & (cal.dt.to_period(period) == last_day.to_period(period))]
        sub = sub.resample(rule).last().dropna(how="all")
        if not later.empty:            # trading days of the latest period still to come
            partial_label = sub.index.max()
    if transform == "pct_change":
        sub = sub.pct_change(fill_method=None) * 100
    if s is not None:
        sub = sub[sub.index >= s]
    if e is not None:
        sub = sub[sub.index <= e]
    sub = sub.dropna(how="all")
    if sub.empty:
        raise DataError("No data in that date range.")
    if limit and sub.size > MAX_POINTS:
        raise DataError(f"{sub.size} values requested (limit {MAX_POINTS}). Narrow the date range, "
                        "use fewer tickers, or resample with freq='W' or 'M'.")
    sub.attrs["partial_last"] = partial_label is not None and sub.index[-1] == partial_label
    return sub, ds


def _round(v):
    if isinstance(v, float):
        return None if pd.isna(v) else round(v, 4)
    return None if pd.isna(v) else v


# --------------------------------------------------------------------------- #
# tools                                                                       #
# --------------------------------------------------------------------------- #

@mcp.resource("potentials://conventions")
def conventions() -> str:
    """How to read Potentials data: tickers, daynums, horizons, trailing vs forward gains."""
    return CONVENTIONS


@mcp.tool(annotations={"readOnlyHint": True})
def list_datasets(kind: Optional[Literal["matrix", "table"]] = None) -> list[dict]:
    """List the available datasets with what each one means.

    matrix = a time series per ticker (query with get_series / plot_series).
    table  = ordinary rows per ticker (query with get_table).
    """
    out = []
    for ds in catalog.datasets().values():
        if kind and ds.kind != kind:
            continue
        out.append({"name": ds.name, "kind": ds.kind, "description": ds.description})
    if kind is None and tunnel_hist.available():
        out.append({"name": "tunnel_history", "kind": "search",
                    "description": "Price tunnel of every ticker for every trading day (status, length, "
                                   "width, slope, close position). Not for get_series/get_table: "
                                   "use the tunnel_history tool (filters across all tickers and dates)."})
    return out


@mcp.tool(annotations={"readOnlyHint": True})
def search_tickers(query: str, limit: int = 25) -> list[dict]:
    """Find tickers by ticker, company name, sector, GICS group, homeland country or zone.

    Every word in the query must match somewhere (case-insensitive), e.g. "semiconductor US"
    or "novo". Returns ticker, name, sector, GICS, homeland, currency and core index.
    """
    try:
        df = catalog.load(catalog.get("Stamdata"))
    except DataError as exc:
        _fail(exc)
    cols = [c for c in ["Name", "Sector", "Sector2", "GICS", "Homeland", "Zone", "Valuta", "CoreIndex"]
            if c in df.columns]
    haystack = (df.index.to_series() + " " + df[cols].fillna("").astype(str).agg(" ".join, axis=1)).str.lower()
    mask = pd.Series(True, index=df.index)
    for word in query.lower().split():
        mask &= haystack.str.contains(word, regex=False)
    hits = df[mask].head(max(1, min(limit, 100)))
    return [{"ticker": t, **{c: _round(row[c]) for c in cols}} for t, row in hits.iterrows()]


@mcp.tool(annotations={"readOnlyHint": True})
def get_series(
    dataset: str,
    tickers: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    freq: Literal["D", "W", "M"] = "D",
    transform: Literal["level", "pct_change"] = "level",
    download: bool = False,
) -> dict:
    """Time series for one or more tickers from a matrix dataset, oldest date first.

    dataset:   e.g. "longi_price" (closing prices), "longi_rsi", "longi_per20d" - see list_datasets.
    tickers:   e.g. ["MSFT", "MU"]; for longi_grp_* datasets these are sector names.
               ["*"] = every row of the dataset (use with download).
    start/end: "YYYY-MM-DD" or "YYYY-MM" (inclusive). Default: full history (~2.7 years).
    freq:      D = every trading day, W = last value of each week, M = last value of each month.
    transform: level = the values as stored; pct_change = % change from the previous point
               (with freq="M" on a price dataset this is the monthly gain in %).
    download:  false (default) = the data comes inline when it is at most 6000 values (tickers x
               dates). Bigger results are cut to the NEWEST dates inline (truncated=true) and the
               COMPLETE result is offered as download_url - a CSV (dates oldest first, one column
               per ticker) for callers that can fetch files or run code; the fetch needs the
               member's API key (create_api_key). true = the file is the answer, for scripts and
               agents: the reply carries download_url, the totals and only a PREVIEW (newest 10
               dates, first 10 tickers), not the data itself.
    """
    try:
        sub, ds = _series_frame(dataset, tickers, start, end, freq, transform, limit=False)
    except DataError as exc:
        _fail(exc)
    full = sub
    truncated = sub.size > MAX_POINTS
    if download:                        # file is the answer: only a small preview inline
        sub = sub.iloc[-PREVIEW_ROWS:, :PREVIEW_ROWS]
    elif truncated:                     # whole dates, newest ones
        sub = sub.tail(max(1, MAX_POINTS // max(1, len(sub.columns))))
    res = {
        "dataset": ds.name,
        "description": ds.description,
        "freq": freq,
        "transform": transform,
        "dates": [d.strftime("%Y-%m-%d") for d in sub.index],
        "series": {t: [_round(v) for v in sub[t].tolist()] for t in sub.columns},
        "last_period_partial": full.attrs["partial_last"],   # True = latest W/M point is to-date, not complete
        # tickers whose newest value is a carried copy (market not traded yet / closed)
        "provisional_newest": catalog.carried_newest(ds, list(full.columns)),
        "truncated": truncated or (download and sub.shape != full.shape),
        "dates_total": len(full),
        "tickers_total": len(full.columns),
    }
    if download:
        res["note"] = (f"download=true: the complete result ({len(full)} dates x {len(full.columns)} tickers) "
                       f"is in download_url; only a preview is shown here (newest {len(sub)} dates, "
                       f"first {len(sub.columns)} tickers).")
    elif truncated:
        res["note"] = (f"Only the newest {len(sub)} of {len(full)} dates are shown ({full.size} values "
                       f"exceed the inline limit of {MAX_POINTS}). The complete result is in download_url.")
    if truncated or download:
        out = full.copy()
        out.index = out.index.strftime("%Y-%m-%d")
        label = "_".join([ds.name, freq, transform])
        if all(pd.api.types.is_numeric_dtype(t) for t in out.dtypes):
            out = out.round(4)
        try:
            res.update(exports.write_csv(out, label, index=True, index_label="date",
                                         what="The COMPLETE result, one row per date, one column per ticker"))
        except exports.ExportError as exc:
            raise ToolError(str(exc)) from exc
    return res


@mcp.tool(annotations={"readOnlyHint": True}, output_schema=None)  # image + text, not JSON
def plot_series(
    dataset: str,
    tickers: list[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    freq: Literal["D", "W", "M"] = "D",
    transform: Literal["level", "pct_change"] = "level",
    title: Optional[str] = None,
) -> list:
    """Same arguments as get_series, but returns a PNG chart (plus the numbers as text).

    Monthly or weekly pct_change is drawn as grouped bars; everything else as lines.
    Up to 8 tickers.
    """
    if len(tickers) > MAX_PLOT_SERIES:
        raise ToolError(f"At most {MAX_PLOT_SERIES} tickers per chart.")
    try:
        sub, ds = _series_frame(dataset, tickers, start, end, freq, transform)
    except DataError as exc:
        _fail(exc)
    if not all(pd.api.types.is_numeric_dtype(t) for t in sub.dtypes):
        raise ToolError(f"'{ds.name}' holds text values and cannot be plotted.")

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=110)
    bars = transform == "pct_change" and freq in ("W", "M")
    if bars:
        labels = sub.index.strftime("%Y-%m" if freq == "M" else "%Y-%m-%d")
        width = 0.8 / len(sub.columns)
        for i, t in enumerate(sub.columns):
            ax.bar([x + i * width for x in range(len(sub))], sub[t], width=width, label=t)
        step = max(1, len(labels) // 18)
        ax.set_xticks([x + 0.4 - width / 2 for x in range(0, len(sub), step)])
        ax.set_xticklabels(labels[::step], rotation=45, ha="right")
        ax.axhline(0, color="#888", linewidth=0.8)
    else:
        for t in sub.columns:
            ax.plot(sub.index, sub[t], label=t, linewidth=1.4)
        fig.autofmt_xdate()
    unit = {"pct_change": "% change"}.get(transform, "value")
    period = {"D": "daily", "W": "weekly", "M": "monthly"}[freq]
    partial_note = f" (last {period[:-2]} is to-date)" if sub.attrs["partial_last"] else ""
    ax.set_title((title or f"{ds.name} - {period} {unit}") + partial_note)
    ax.set_ylabel(unit)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)

    table = sub.round(2).to_string(max_rows=60)
    return [Image(data=buf.getvalue(), format="png"),
            f"{ds.name} ({ds.description}) - {period} {unit}, "
            f"{sub.index[0]:%Y-%m-%d} to {sub.index[-1]:%Y-%m-%d}{partial_note}:\n{table}"]


@mcp.tool(annotations={"readOnlyHint": True})
def get_table(
    dataset: str,
    tickers: Optional[list[str]] = None,
    columns: Optional[list[str]] = None,
    limit: int = 100,
    download: bool = False,
) -> dict:
    """Rows from a table dataset: Stamdata, potrank2, Google, StrategicStocks, across,
    Yfinance, StockData2_stacked (see list_datasets).

    tickers: only these rows (first column of the file). Omit for all rows, capped at `limit`.
    columns: only these columns (call once without it to see which exist).
    limit:   rows shown inline, 1-300.
    download: false (default) = rows beyond `limit` are not shown, but when there are any the
              reply carries download_url: the COMPLETE selection (your tickers/columns) as a
              CSV for callers that can fetch files or run code; the fetch needs the member's
              API key (create_api_key). true = the file is the answer, for scripts and agents:
              download_url, rows_total and only a PREVIEW of the first 10 rows inline.
    """
    try:
        ds = catalog.get(dataset)
        if ds.kind != "table":
            raise DataError(f"'{ds.name}' is a time series - use get_series.")
        df = catalog.load(ds)
        if tickers:
            df = df.loc[catalog.resolve_rows(df, tickers)]
        if columns:
            unknown = [c for c in columns if c not in df.columns]
            if unknown:
                raise DataError(f"Unknown columns {unknown}. Available: {list(df.columns)}")
            df = df[columns]
    except DataError as exc:
        _fail(exc)
    limit = max(1, min(limit, MAX_ROWS))
    if download:
        limit = min(limit, PREVIEW_ROWS)        # the file is the answer: preview only
    total = len(df)
    shown = df.head(limit)
    res = {
        "dataset": ds.name,
        "description": ds.description,
        "key_column": str(catalog.load(ds).index.name),
        "rows_total": total,
        "rows_returned": len(shown),
        "rows": [{"key": k, **{c: _round(v) for c, v in row.items()}} for k, row in shown.iterrows()],
    }
    if total > len(shown) or download:
        if total > len(shown):
            res["note"] = (f"Only the first {len(shown)} of {total} rows are shown"
                           f"{' (download=true: preview only)' if download else ''}. "
                           "The complete selection is in download_url.")
        out = df.copy()
        out.index.name = "key"          # the file's own header cell can be a creation stamp
        out = out.apply(lambda s: s.round(4) if pd.api.types.is_float_dtype(s) else s)
        try:
            res.update(exports.write_csv(out, ds.name, index=True,
                                         what="The COMPLETE selection, one row per key"))
        except exports.ExportError as exc:
            raise ToolError(str(exc)) from exc
    return res


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def tunnel_report(
    tickers: list[str],
    end_date: Optional[str] = None,
    name: Optional[str] = None,
) -> dict:
    """Price-tunnel report: for each ticker the longest log-linear trend channel ending at
    end_date (default: newest day). Writes CSV + PDF (A4, 18 panels/page) + one tall PNG
    (+ one PNG per ticker when 6 or fewer) into a fresh folder and returns download links
    plus the table. Links work for anyone holding them and expire after 7 days.

    tickers: Yahoo-style, 1-200 (use search_tickers to find them).
    end_date: YYYY-MM-DD; the newest trading day on or before it is used (tunnels for past
      dates, and searches across all tickers and dates, are in tunnel_history).
    name: optional label put in the folder name (letters, digits, _ and -).

    Table columns: status (tunnel/old_tunnel/no_tunnel/insufficient_data), length_td (trading
    days), width_pct (lower->upper line), slope20_pct (% gain per 20 trading days along the
    lines), supports_upper/lower, close_pos (0 = on lower line, 1 = on upper line; outside
    0..1 = the close has left the tunnel; empty for old_tunnel).
    old_tunnel = no tunnel ends on the report date, but one ended up to 50 trading days
    earlier: its numbers and end_date are that old tunnel's, age_td = trading days since.
    """
    try:
        df = catalog.load(catalog.get("Stamdata"))
        resolved = catalog.resolve_rows(df, tickers)
    except DataError as exc:
        _fail(exc)
    try:
        out = tunnel_ondemand.make_report(resolved, end_date, name)
    except RuntimeError as exc:
        raise ToolError(f"Tunnel report failed: {exc}") from exc
    keep = ["ticker", "status", "length_td", "width_pct", "slope20_pct", "supports_upper",
            "supports_lower", "start_date", "end_date", "last_close", "close_pos", "age_td"]
    return {"folder_url": out["url"], "files": out["links"],
            "rows": [{k: r.get(k, "") for k in keep} for r in out["rows"]]}


@mcp.tool(annotations={"readOnlyHint": True})
def tunnel_history(
    tickers: Optional[list[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    where: Optional[list[str]] = None,
    columns: Optional[list[str]] = None,
    sort: Optional[str] = None,
    limit: int = 100,
    summarize: Optional[Literal["date", "month", "ticker", "status"]] = None,
    extended: bool = False,
) -> dict:
    """Search the full tunnel history: for EVERY trading day since 2024 and every ticker, the
    longest price tunnel ending that day (the same numbers tunnel_report gives for one date).
    ~0.9M rows, so ask a narrow question: filter across all tickers and dates, then either read
    the matching rows (max 500 shown; the full match is offered as a download link) or summarize
    them. Every answer reports rows_matched.

    tickers:   only these (optional; omit to search all ~1,235).
    start/end: "YYYY-MM-DD" or "YYYY-MM" (inclusive), on the tunnel's end date.
    where:     list of filters, all must hold, each 'column operator value' with operators
               > >= < <= = != , e.g. ["status = tunnel", "length_td >= 60", "close_pos >= 0.9"].
    columns:   what to return (default = the core columns below).
    sort:      column name, "-" in front for descending (e.g. "-length_td"). Without it rows are
               in date order, and when there are more matches than `limit` the NEWEST ones are shown.
    limit:     rows to show, 1-500. When more rows match, the reply carries download_url: the
               COMPLETE result as a CSV (standard comma/point) for callers that can fetch files or
               run code - the fetch needs the member's API key (create_api_key); chat-only
               callers should narrow the filter or use summarize.
    summarize: instead of rows, count + mean per date / month / ticker / status (means of
               `columns`, default length_td, width_pct, slope20_pct, close_pos). Use this for
               "how many ... per month" style questions.
    extended:  false (default) = only the core columns exist for columns/where/sort, which is
               enough for most table analyses. true = also the detail columns: supports_upper,
               supports_lower (touch clusters per line), daynum, start_date, start_daynum,
               end_daynum, lower_start, upper_start, lower_end, upper_end (line prices at the
               tunnel's start/end), last_close.

    Core columns: end_date, ticker, status (tunnel / no_tunnel / insufficient_data = too little
    price history that day), length_td (tunnel length in trading days), width_pct (lower->upper
    line %), slope20_pct (% gain per 20 trading days along the lines), close_pos (0 on the lower
    line, 1 on the upper; always 0..1 because the tunnel contains every close of its window;
    blank without a tunnel). The first 19 days of the price history are not in the file (no
    ticker could have a tunnel). Outcomes after a day: use get_series on longi_future_per20d
    etc. (look-ahead data).
    """
    try:
        return tunnel_hist.query(tickers, start, end, where, columns, sort, limit, summarize, extended)
    except DataError as exc:
        _fail(exc)


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def create_api_key() -> dict:
    """Create YOUR personal API key for downloading complete CSV results (download_url from
    get_series, get_table, tunnel_history). Shown ONCE - it cannot be shown again, so save it
    now. Calling this again replaces the old key, which stops working at once (use that if a key
    is lost or leaked). The key belongs to the Google account you signed in with; it stops working
    the moment that account is removed from the allowlist.
    """
    token = get_access_token()
    email = (token.claims.get("email") or "").lower() if token else ""
    if not email:
        raise ToolError("An API key can only be created over the signed-in connection.")
    try:
        key = exports.create_key(email)
    except exports.ExportError as exc:
        raise ToolError(str(exc)) from exc
    log.info("api key created for %s", email)
    return {
        "api_key": key,
        "belongs_to": email,
        "shown_once": "Save it now (a password manager or an environment variable). Do not share it: "
                      "every download made with it is logged under your name.",
        "use": "Send it with each download: header 'Authorization: Bearer <api_key>' (or 'X-API-Key: "
               "<api_key>'), e.g.  curl -H 'Authorization: Bearer $POTENTIALS_KEY' -O <download_url>",
        "replaces": "Any key you had before no longer works.",
    }


# --------------------------------------------------------------------------- #
# authenticated download of complete results                                  #
# --------------------------------------------------------------------------- #

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


@mcp.custom_route("/dl/{token}/{name}", methods=["GET"])
async def download(request: Request):
    """GET /dl/<token>/<name>.csv with the member's API key. The link alone is useless: the key
    is checked against the allowlist as it stands now, on every fetch, and every fetch is logged
    with the member's email."""
    auth = request.headers.get("authorization", "")
    key = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-api-key", "").strip()
    ip = _client_ip(request)
    try:
        email = exports.owner_of(key)
    except exports.ExportError:
        return PlainTextResponse("Service error.", status_code=503)
    if not email or email not in _allowed_now():
        log.warning("download refused: %s key=%s ip=%s %s", email or "<no valid key>",
                    "present" if key else "absent", ip, request.url.path)
        return PlainTextResponse("API key missing, invalid or revoked. Get one with the create_api_key "
                                 "tool, then send it as 'Authorization: Bearer <key>'.", status_code=401)
    path = exports.resolve(request.path_params["token"], request.path_params["name"])
    if path is None:
        log.info("download not found: %s %s", email, request.url.path)
        return PlainTextResponse("Not found, or expired (links last "
                                 f"{exports.TTL_HOURS} hours). Ask for the result again.", status_code=404)
    log.info("download %s %s %d bytes ip=%s", email, path.name, path.stat().st_size, ip)
    return FileResponse(path, media_type="text/csv", filename=path.name,
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


# --------------------------------------------------------------------------- #
# HTTP entry point (systemd: uvicorn server:app)                              #
# --------------------------------------------------------------------------- #

if _auth is None and os.environ.get("RTBI_MCP_NO_AUTH") != "1":
    app = None   # importing for in-memory tests is fine; serving over HTTP is not
else:
    app = mcp.http_app(path="/mcp")


def _require_app():
    if app is None:
        raise SystemExit("Refusing to serve without auth: set GOOGLE_CLIENT_ID etc. in .env "
                         "(or RTBI_MCP_NO_AUTH=1 for a local-only test).")


if __name__ == "__main__":
    _require_app()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8766)
