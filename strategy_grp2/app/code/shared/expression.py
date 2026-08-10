"""
The free logical-expression engine — DesignVersion2.md's core idea: group definition (and,
for Step 2, the post-selection filter) is just another parameter, not a fixed Stamdata
column name.

Grammar, informally:

    expr       := term (".and." term)*
    term       := namespace "." column [ op value ]
    namespace  := "Stamdata" | "Longi"
    op         := "=" | "!=" | ">=" | "<=" | ">" | "<"

A term with no operator is a bare reference — for `group_expression` this means "group by
this column's values" (a grouping DIMENSION); a term with an operator restricts the
universe (a FILTER). `#ALL` means every ticker, one group. Examples (all valid
group_expression values):

    #ALL                                  -> every ticker, one group
    Stamdata.Homeland='US'                -> US tickers, one group
    Stamdata.GICS                         -> all tickers, grouped by GICS (13 groups)
    Stamdata.Zone .and. Stamdata.GICS      -> all tickers, grouped by Zone x GICS (composite)
    Stamdata.Zone='NY' .and. Stamdata.GICS -> NY tickers, grouped by GICS

`Longi.<factor><op><value>` (e.g. `Longi.per1d>0`) is the post_filter spelling — evaluated
per ticker, per daynum, against a Longi matrix — and is not legal inside group_expression
(step0_data.parse_group_expression restricts the allowed namespace).

Unknown column, unparseable syntax, or a filter matching zero tickers/candidates is always
a hard failure with the reason (ExpressionError) — never a silent empty result, per the
project's "wrong-but-plausible is worse than stopping" rule (see strategy_grp's CLAUDE.md).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import pandas as pd

from shared.data_loader import load_longi


class ExpressionError(ValueError):
    """A group_expression / post_filter string that cannot be parsed or resolved."""


@dataclass(frozen=True)
class Term:
    namespace: str          # "Stamdata" | "Longi"
    column: str
    op: str | None          # None = bare reference (a grouping dimension)
    value: str | None


_AND_RE = re.compile(r"\.and\.", re.IGNORECASE)
_TERM_RE = re.compile(
    r"^(Stamdata|Longi)\.([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(?:(=|!=|>=|<=|>|<)\s*(.+))?$"
)

_OPS = {
    "=":  lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def parse_terms(expr_str: str, allowed_namespaces: tuple[str, ...]) -> list[Term]:
    """Split on `.and.` and parse each part as a Term. `#ALL` and blank both parse to [].
    Raises ExpressionError naming the offending part, or a namespace this caller does not
    permit (group_expression never allows Longi; post_filter never allows a bare reference)."""
    expr_str = expr_str.strip()
    if not expr_str or expr_str == "#ALL":
        return []
    parts = [p.strip() for p in _AND_RE.split(expr_str) if p.strip()]
    if not parts:
        raise ExpressionError(f"empty expression: {expr_str!r}")
    terms: list[Term] = []
    for part in parts:
        m = _TERM_RE.match(part)
        if not m:
            raise ExpressionError(f"unparseable term {part!r} in expression {expr_str!r}")
        ns, column, op, value = m.groups()
        if ns not in allowed_namespaces:
            raise ExpressionError(
                f"{ns}.{column}: namespace '{ns}' not allowed here (allowed: "
                f"{list(allowed_namespaces)}) — expression {expr_str!r}"
            )
        terms.append(Term(ns, column, op, _strip_quotes(value) if value is not None else None))
    return terms


# ---------------------------------------------------------------------------
# group_expression — Stamdata only, dimensions + universe filters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupSpec:
    raw: str
    universe_filters: list[Term] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)   # bare-reference columns, in order


def parse_group_expression(raw: str) -> GroupSpec:
    terms = parse_terms(raw, allowed_namespaces=("Stamdata",))
    dimensions: list[str] = []
    filters: list[Term] = []
    for t in terms:
        if t.op is None:
            if t.column not in dimensions:
                dimensions.append(t.column)
        else:
            filters.append(t)
    return GroupSpec(raw=raw.strip(), universe_filters=filters, dimensions=dimensions)


def resolve_stamdata_column(name: str, stamdata: pd.DataFrame) -> str:
    """The real Stamdata column a board spelling refers to.

    Exact match wins; failing that, a unique case-insensitive match. The board is hand-typed
    in Excel, so `Stamdata.ZONE` and `Stamdata.Fkgrade` are the same intent as the actual
    `Zone` / `FKgrade` columns — a case slip is a typing accident, not a different request,
    and letting it stop a whole row taught nothing (the message did not even say which
    columns exist). A genuinely unknown name is still a hard failure, now naming the near
    misses and the full column list."""
    columns = [str(c) for c in stamdata.columns]
    if name in columns:
        return name
    hits = [c for c in columns if c.lower() == name.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:                       # cannot happen with today's Stamdata, but the
        raise ExpressionError(              # spelling would be genuinely ambiguous if it did
            f"Stamdata.{name}: ambiguous, matches {hits} case-insensitively — "
            f"write the exact column name."
        )
    close = difflib.get_close_matches(name, columns, n=3, cutoff=0.6)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ExpressionError(
        f"Stamdata.{name}: no such column.{hint} Known columns: {', '.join(columns)}"
    )


def canonicalize_group_spec(spec: GroupSpec, stamdata: pd.DataFrame) -> GroupSpec:
    """`spec` with every dimension and filter column replaced by its real Stamdata spelling.
    Idempotent, and the single point where a board spelling becomes a column name — so
    downstream code (Step 0's GICS/Sector2 twin binding, group cache keys, reports) always
    sees the canonical name rather than whatever case the board happened to use."""
    dimensions = [resolve_stamdata_column(d, stamdata) for d in spec.dimensions]
    filters = [Term(t.namespace, resolve_stamdata_column(t.column, stamdata), t.op, t.value)
               for t in spec.universe_filters]
    if dimensions == spec.dimensions and filters == spec.universe_filters:
        return spec
    return GroupSpec(raw=spec.raw, universe_filters=filters, dimensions=dimensions)


def _coerce_compare(series: pd.Series, value: str) -> tuple[pd.Series, object]:
    """Numeric comparison when the literal parses as a number; string comparison otherwise
    (Stamdata columns are a mix of categorical text and the occasional numeric one)."""
    try:
        return series.astype(float), float(value)
    except (TypeError, ValueError):
        return series.astype(str), value


def apply_stamdata_filters(stamdata: pd.DataFrame, filters: list[Term]) -> pd.Index:
    """Stamdata.index, filtered by every `.and.`-joined universe filter -- with
    caret-prefixed benchmark/index tickers (^GSPC, ^VIX, ^BTC, ...) excluded first,
    unconditionally, even under `#ALL` or an explicit filter that would otherwise admit
    them. They are reference instruments, not tradeable stocks, and have no place in a
    lot simulation's universe (SM, 2026-08-05) -- this was a real bug, not a design
    choice: a GICS/Sector2 value on a caret ticker in Stamdata was forming a spurious
    ~14-member "Index" pseudo-sector (see DesignVersion2.md's 2026-08-05 correction).
    Reference use elsewhere (market context rows, benchmark returns in shared/market.py)
    reads these by ticker name directly and never goes through group_expression, so it
    is unaffected."""
    mask = ~stamdata.index.to_series().astype(str).str.startswith("^")
    for t in filters:
        column = resolve_stamdata_column(t.column, stamdata)
        op_fn = _OPS.get(t.op)
        if op_fn is None:
            raise ExpressionError(f"Stamdata.{column}{t.op}: unsupported operator")
        col_series, value = _coerce_compare(stamdata[column], t.value)
        mask &= op_fn(col_series, value)
    return stamdata.index[mask]


def _group_key_values(series: pd.Series) -> pd.Series:
    """A Stamdata column as group keys. Whole numbers lose the float tail pandas gives them:
    a numeric grading column (`FKgrade` = -1..5) must name its groups `4`, not `4.0`, since
    that key is what every label, sheet heading and chart legend downstream shows."""
    if pd.api.types.is_numeric_dtype(series):
        return series.map(
            lambda v: str(int(v)) if float(v).is_integer() else str(v)
        ).astype(str)
    return series.astype(str)


def resolve_universe_and_groups(spec: GroupSpec, stamdata: pd.DataFrame) -> tuple[pd.Index, pd.Series]:
    """(universe, groups): groups is a ticker -> group-key Series (partition — one key per
    ticker). No `dimensions` -> every filtered ticker is one group, "ALL". A ticker missing
    any dimension value is dropped from the universe — it cannot be unambiguously grouped."""
    spec = canonicalize_group_spec(spec, stamdata)
    universe = apply_stamdata_filters(stamdata, spec.universe_filters)
    if not spec.dimensions:
        groups = pd.Series("ALL", index=universe)
        return universe, groups
    sub = stamdata.loc[universe, spec.dimensions].dropna()
    keys = [_group_key_values(sub[dim]) for dim in spec.dimensions]
    if len(keys) > 1:
        key = pd.concat(keys, axis=1).agg("|".join, axis=1)
    else:
        key = keys[0]
    return key.index, key


# ---------------------------------------------------------------------------
# post_filter — Longi only, per-daynum, comparisons only (no bare references)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostFilterSpec:
    raw: str
    terms: list[Term] = field(default_factory=list)


def parse_post_filter(raw: str) -> PostFilterSpec:
    raw = raw.strip() if raw else ""
    if not raw:
        return PostFilterSpec(raw="", terms=[])
    terms = parse_terms(raw, allowed_namespaces=("Longi",))
    for t in terms:
        if t.op is None:
            raise ExpressionError(
                f"Longi.{t.column}: post_filter terms must be comparisons (e.g. "
                f"Longi.{t.column}>0), not a bare reference."
            )
    return PostFilterSpec(raw=raw, terms=terms)


def apply_post_filter(spec: PostFilterSpec, daynum: int, tickers: list[str]) -> list[str]:
    """Surviving tickers at one daynum. [] (not an error) when a referenced factor has no
    column for this daynum — a clean no-pick hop, the same contract every other Step-2/3
    lookup in this project uses for a missing daynum."""
    if not spec.terms:
        return tickers
    col = str(daynum)
    survivors = set(tickers)
    for t in spec.terms:
        df = load_longi(f"longi_{t.column}.csv")
        if col not in df.columns:
            return []
        op_fn = _OPS.get(t.op)
        if op_fn is None:
            raise ExpressionError(f"Longi.{t.column}{t.op}: unsupported operator")
        series = df[col]
        qualifying = set(series.index[op_fn(series, float(t.value))])
        survivors &= qualifying
        if not survivors:
            return []
    return [t for t in tickers if t in survivors]
