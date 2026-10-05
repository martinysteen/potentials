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
from pathlib import Path
from typing import Literal, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastmcp import FastMCP  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from fastmcp.server.dependencies import get_access_token  # noqa: E402
from fastmcp.server.middleware import Middleware, MiddlewareContext  # noqa: E402
from fastmcp.utilities.types import Image  # noqa: E402

import catalog  # noqa: E402
from catalog import DataError  # noqa: E402

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger("rtbi-mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_POINTS = 6000      # tickers x dates returned by get_series / plot_series
MAX_ROWS = 300         # rows returned by get_table
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
"""

INSTRUCTIONS = ("Read-only access to the Potentials stock-analysis repository: daily prices "
                "(PotDat / longi_price), ~80 per-ticker factor tables (longi_*), master data "
                "(Stamdata), rankings (potrank2), today's strategy picks (StrategicStocks) and "
                "yFinance fundamentals. Start with list_datasets; read resource "
                "potentials://conventions before interpreting per/future_per tables.\n\n"
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


ALLOWED = {e.strip().lower() for e in os.environ.get("RTBI_MCP_ALLOWED_EMAILS", "").split(",") if e.strip()}


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
                  freq: str, transform: str) -> tuple[pd.DataFrame, catalog.Dataset]:
    """Long-history frame: index = dates oldest-first, one column per ticker."""
    ds = catalog.get(dataset)
    if ds.kind != "matrix":
        raise DataError(f"'{ds.name}' is a table, not a time series - use get_table.")
    if not tickers:
        raise DataError("Give at least one ticker.")
    df = catalog.load(ds)
    rows = catalog.resolve_rows(df, tickers)
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
    if sub.size > MAX_POINTS:
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
) -> dict:
    """Time series for one or more tickers from a matrix dataset, oldest date first.

    dataset:   e.g. "longi_price" (closing prices), "longi_rsi", "longi_per20d" - see list_datasets.
    tickers:   e.g. ["MSFT", "MU"]; for longi_grp_* datasets these are sector names.
    start/end: "YYYY-MM-DD" or "YYYY-MM" (inclusive). Default: full history (~2.7 years).
    freq:      D = every trading day, W = last value of each week, M = last value of each month.
    transform: level = the values as stored; pct_change = % change from the previous point
               (with freq="M" on a price dataset this is the monthly gain in %).
    """
    try:
        sub, ds = _series_frame(dataset, tickers, start, end, freq, transform)
    except DataError as exc:
        _fail(exc)
    return {
        "dataset": ds.name,
        "description": ds.description,
        "freq": freq,
        "transform": transform,
        "dates": [d.strftime("%Y-%m-%d") for d in sub.index],
        "series": {t: [_round(v) for v in sub[t].tolist()] for t in sub.columns},
        "last_period_partial": sub.attrs["partial_last"],   # True = latest W/M point is to-date, not complete
    }


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
) -> dict:
    """Rows from a table dataset: Stamdata, potrank2, Google, StrategicStocks, across,
    Yfinance, StockData2_stacked (see list_datasets).

    tickers: only these rows (first column of the file). Omit for all rows, capped at `limit`.
    columns: only these columns (call once without it to see which exist).
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
    total = len(df)
    df = df.head(limit)
    return {
        "dataset": ds.name,
        "description": ds.description,
        "key_column": str(catalog.load(ds).index.name),
        "rows_total": total,
        "rows_returned": len(df),
        "rows": [{"key": k, **{c: _round(v) for c, v in row.items()}} for k, row in df.iterrows()],
    }


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
