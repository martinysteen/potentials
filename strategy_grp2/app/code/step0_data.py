"""
Step 0 — group definition and data procurement.

Resolves one board row's `group_expression` into a ticker universe and a group-key
Series (shared.expression does the parsing), binds any group-specific Longi factor
(conf/sectorbeta) to the row's own grouping, and hosts the ad-hoc-builder registry for
whatever Longi cannot supply directly. See DesignVersion2.md's Step 0 write-up.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import expression as expr
from shared.config import DERIVED_ROOT
from shared.data_loader import load_longi, load_stamdata

# ---------------------------------------------------------------------------
# Group-specific Longi factors — twins that exist only for Stamdata.GICS / Stamdata.Sector2
# ---------------------------------------------------------------------------
# Mirrors strategy_grp v1's run_config.GROUP_SPECIFIC_FACTORS / resolve_attribute, but the
# "criterion" here is no longer a fixed group_column parameter — it is whatever
# GroupSpec.dimensions came out of parsing group_expression. A twin only binds when that
# grouping is EXACTLY one of the two known dimensions; anything else (a composite grouping,
# #ALL, a Homeland grouping, ...) has no twin to read, and that is a hard failure naming
# the stem and the expression — not a fallback to GICS.
GROUP_SPECIFIC_FACTORS: tuple[str, ...] = ("conf", "sectorbeta")
_TWIN_CRITERIA: tuple[str, ...] = ("GICS", "Sector2")


def split_group_specific(attribute: str) -> tuple[str, str] | None:
    """(stem, group_column) for a group-specific factor name, else None. A bare stem
    ("conf") returns ("conf", "") and binds to the run's own grouping; an explicit
    "conf_Sector2" pins the twin regardless of it."""
    for stem in GROUP_SPECIFIC_FACTORS:
        if attribute == stem:
            return stem, ""
        if attribute.startswith(f"{stem}_"):
            return stem, attribute[len(stem) + 1:]
    return None


def _twin_criterion(name: str) -> str | None:
    """The canonical twin criterion a written name refers to, case-insensitively, else None.
    Case-tolerant for the same reason shared.expression.resolve_stamdata_column is — and
    needed independently of it, because preflight resolves twins from the raw board spelling
    before any Stamdata is loaded to canonicalize against."""
    for criterion in _TWIN_CRITERIA:
        if name.lower() == criterion.lower():
            return criterion
    return None


def resolve_group_specific(attribute: str, dimensions: list[str]) -> str:
    """The Longi factor short name a row must actually read. An ordinary factor passes
    through untouched. A group-specific one (bare stem or either twin) is bound to this
    row's own grouping — which must be EXACTLY Stamdata.GICS or Stamdata.Sector2 for a
    twin to exist. Raises ExpressionError otherwise; falling back to GICS would produce a
    complete, plausible, wrong run, which this project treats as worse than stopping."""
    if not attribute:
        return attribute
    split = split_group_specific(attribute)
    if split is None:
        return attribute
    stem, written = split
    criterion = _twin_criterion(dimensions[0]) if len(dimensions) == 1 else None
    if criterion is None:
        raise expr.ExpressionError(
            f"'{attribute}' is a group-specific factor (longi_{stem}_<criterion>.csv), but "
            f"this row's grouping ({dimensions or ['ALL']}) is not exactly one of "
            f"{list(_TWIN_CRITERIA)} — there is no twin to bind it to."
        )
    if written and _twin_criterion(written) is None:
        raise expr.ExpressionError(
            f"'{attribute}' names criterion '{written}', which is not one of "
            f"{list(_TWIN_CRITERIA)}. Write the bare stem '{stem}' to get this row's own "
            f"twin automatically."
        )
    return f"{stem}_{criterion}"


# ---------------------------------------------------------------------------
# Step 0 resolution
# ---------------------------------------------------------------------------


@dataclass
class Step0Result:
    universe: pd.Index
    groups: pd.Series                        # ticker -> group key (a partition)
    group_sizes: dict[str, int]
    dominance_attribute: str                 # resolved (twin-bound if needed)
    priority_attribute: str                  # resolved
    informational_attributes: list[str] = field(default_factory=list)   # resolved
    post_filter: "expr.PostFilterSpec" = None


def resolve_step0(row_resolved: dict) -> Step0Result:
    """Universe + groups + resolved attribute names for one board row. Raises
    shared.expression.ExpressionError with the reason on any failure — unknown column,
    unparseable expression, zero-match filter, or an unbindable group-specific factor.
    """
    gspec = expr.parse_group_expression(row_resolved["group_expression"])
    stamdata = load_stamdata()
    gspec = expr.canonicalize_group_spec(gspec, stamdata)   # board spelling -> column name
    universe, groups = expr.resolve_universe_and_groups(gspec, stamdata)
    if universe.empty:
        raise expr.ExpressionError(
            f"group_expression={row_resolved['group_expression']!r} matches zero tickers"
        )
    group_sizes = groups.value_counts().to_dict()

    dominance_attribute = resolve_group_specific(row_resolved["dominance_attribute"], gspec.dimensions)
    priority_attribute = resolve_group_specific(row_resolved["priority_attribute"], gspec.dimensions)
    informational = [resolve_group_specific(a, gspec.dimensions)
                      for a in row_resolved.get("informational_attributes", ())]
    post_filter = expr.parse_post_filter(row_resolved.get("post_filter", ""))

    return Step0Result(
        universe=universe, groups=groups, group_sizes=group_sizes,
        dominance_attribute=dominance_attribute, priority_attribute=priority_attribute,
        informational_attributes=informational, post_filter=post_filter,
    )


# ---------------------------------------------------------------------------
# Ad-hoc builder registry — for factors Longi cannot supply directly
# ---------------------------------------------------------------------------
# Phase 1 (this module) ships exactly one builder: a group-level mean aggregate of any
# per-ticker Longi factor, for the CURRENT (possibly ad-hoc) grouping — the
# longi_grp_{GICS,Sector2}_per*.csv idea, generalized to whatever grouping a row defines.
# Cached under app/data/derived/ since it is cheap to rebuild but no need to redo it for
# every hop. Not yet consumed by step1/2 (their selection math is per-ticker); it exists
# for Step-3 informational display and the market-rotation-rate diagnostic DesignVersion2.md
# and strategy_grp's CLAUDE.md both flag as still open — wiring that in is later work.


def build_group_aggregate(factor: str, groups: pd.Series) -> pd.DataFrame:
    """group-key x daynum mean of longi_<factor>.csv for the given grouping."""
    df = load_longi(f"longi_{factor}.csv")
    common = df.index.intersection(groups.index)
    return df.loc[common].groupby(groups.loc[common]).mean()


def cached_group_aggregate(factor: str, groups: pd.Series, cache_key: str) -> pd.DataFrame:
    """Same as build_group_aggregate, but cached to app/data/derived/grp_<factor>__<cache_key>.csv
    (European CSV, matching every other file in this project). `cache_key` must uniquely
    identify the grouping (the group_expression string is enough)."""
    safe_key = "".join(c if c.isalnum() else "_" for c in cache_key)
    path = DERIVED_ROOT / f"grp_{factor}__{safe_key}.csv"
    if path.exists():
        return pd.read_csv(path, sep=";", decimal=",", index_col=0)
    result = build_group_aggregate(factor, groups)
    DERIVED_ROOT.mkdir(parents=True, exist_ok=True)
    result.to_csv(path, sep=";", decimal=",")
    return result
