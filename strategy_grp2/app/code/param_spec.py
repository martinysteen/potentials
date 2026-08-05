"""
The schema — every parameter a control-board row can carry, its type, its default and
its legal values. This is the one place that knows what a row means; `control_board.py`
reads it to validate rows and to (re)generate the board's `Runs`/`Legend` sheets, so a
mistyped header is a hard error rather than a silently-ignored column.

See DesignVersion2.md for the process-step write-up this mirrors.

Column groups, one row per parameter (`step` is which process step reads it; `None` = a
meta column, not one of the four steps):

    meta   -> active, purpose, label, note
    step 0 -> group_expression
    step 1 -> level, persistence_window, persistence_frac, dominance_attribute,
              dominance_direction, dominance_decile, dom_count_min, tickers_per_group
              (dom_count_frac is NOT a board column -- see shared.config.DOM_COUNT_FRAC_MARGIN)
    step 2 -> post_filter, priority_attribute, priority_direction, from_rank, focusset_size
    step 3 -> period, no_go_gspc_rsi, informational_attributes, stop_loss
    step 4 -> wf_group

`from_rank` accepts more than v1's {1, -1} — see `parse_from_rank()` below: a pool-relative
"mid" / quantile window as well as v1's fixed best-n / worst-n / offset-k. This is deliberate
(SM, 2026-08-03): avoiding both the top supers and the bottom losers needs a window defined
relative to the day's pool size, not a fixed rank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# The "seven-pack" forward-horizon ladder — see shared/config.py::FUTURE_PERIODS.
FUTURE_PERIODS: tuple[int, ...] = (1, 5, 10, 20, 50, 100, 200)

LEVELS: tuple[str, ...] = ("A", "B", "C")   # today / 20d-persistent / 50d-persistent


# ---------------------------------------------------------------------------
# from_rank — the one parameter with a real parser, not just a type coercion
# ---------------------------------------------------------------------------

# A parsed from_rank is one of:
#   ("edge", 1)            best n            (v1 default)
#   ("edge", -1)           worst n
#   ("offset", k)          fixed offset, integer k >= 2 — "skip the top k-1"
#   ("quantile", f)        pool-relative window centred at quantile f in (0, 1); "mid" == 0.5
FromRank = tuple[str, int | float]


def parse_from_rank(raw: Any) -> FromRank:
    """Validate and classify a from_rank value. Raises ValueError with a message naming
    every accepted spelling — this is deliberately strict, since a silently-misread
    from_rank inverts which tickers are "best" the same way a wrong attribute direction
    does (see run_config.py in strategy_grp for that failure mode).

    Accepted spellings:
        1, -1            -> ("edge", 1) / ("edge", -1)
        "mid"            -> ("quantile", 0.5)
        a float in (0,1) -> ("quantile", f)
        an int >= 2      -> ("offset", k)
    """
    if isinstance(raw, str) and raw.strip().lower() == "mid":
        return ("quantile", 0.5)
    if isinstance(raw, bool):
        raise ValueError(f"from_rank={raw!r} is not valid — see param_spec.parse_from_rank")
    if isinstance(raw, int):
        if raw in (1, -1):
            return ("edge", raw)
        if raw >= 2:
            return ("offset", raw)
        raise ValueError(
            f"from_rank={raw} is not valid: integers must be 1, -1, or >= 2 "
            f"(1=best n, -1=worst n, k>=2=fixed offset 'skip the top k-1')."
        )
    if isinstance(raw, float):
        if 0.0 < raw < 1.0:
            return ("quantile", raw)
        if raw.is_integer():
            return parse_from_rank(int(raw))
        raise ValueError(
            f"from_rank={raw} is not valid: a float must be strictly between 0 and 1 "
            f"(a pool-relative quantile, 0.5 == 'mid')."
        )
    if isinstance(raw, str):
        s = raw.strip()
        try:
            if "." in s:
                return parse_from_rank(float(s))
            return parse_from_rank(int(s))
        except ValueError:
            pass
    raise ValueError(
        f"from_rank={raw!r} not understood. Valid: 1 (best n), -1 (worst n), "
        f"'mid' or a float in (0,1) (pool-relative window), or an integer k>=2 "
        f"(fixed offset from the top)."
    )


def format_from_rank(parsed: FromRank) -> str:
    """The canonical string a resolved row / report should display — round-trips through
    parse_from_rank()."""
    kind, value = parsed
    if kind == "edge":
        return str(value)
    if kind == "quantile":
        return "mid" if value == 0.5 else str(value)
    return str(value)


# ---------------------------------------------------------------------------
# Direction flags — spelled out on the board rather than True/False, since a bare
# boolean column reads as meaningless without opening this file (see strategy_grp's
# CLAUDE.md: a wrong direction silently inverts which tickers count as "best").
# ---------------------------------------------------------------------------

DIRECTIONS: dict[str, bool] = {"small_wins": True, "big_wins": False}


def parse_direction(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in DIRECTIONS:
        return DIRECTIONS[raw.strip().lower()]
    raise ValueError(f"direction={raw!r} must be one of {list(DIRECTIONS)}")


def format_direction(value: bool) -> str:
    return "small_wins" if value else "big_wins"


# ---------------------------------------------------------------------------
# stop_loss — Step 3a's exit level. Matches longi_future_minaggr*.csv's sign convention
# (a drawdown is <= 0), so a positive cell is almost certainly the level typed as a bare
# magnitude ("10" meaning -10%) -- rejected rather than silently negated, since guessing
# the sign is exactly the kind of silent inversion this schema exists to catch.
# ---------------------------------------------------------------------------


def parse_stop_loss(raw: Any) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"stop_loss={raw!r} is not valid — see param_spec.parse_stop_loss")
    value = float(raw)
    if value > 0:
        raise ValueError(
            f"stop_loss={value} must be <= 0 (minaggr's sign convention: a drawdown is "
            f"never positive). 0 = off; did you mean {-value}?"
        )
    return value


# ---------------------------------------------------------------------------
# The schema itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamDef:
    name: str
    step: int | None          # 0-4, or None for a meta column
    dtype: str                # "str" | "int" | "float" | "bool" | "choice" | "expr" | "from_rank" | "direction" | "list_str"
    default: Any = None
    choices: tuple[str, ...] | None = None
    required: bool = False    # must be non-blank on every row (no schema default applies)
    help: str = ""
    parser: Callable[[Any], Any] | None = None   # overrides dtype-based coercion when set


PARAMS: list[ParamDef] = [
    # --- meta -----------------------------------------------------------------
    ParamDef("active", None, "bool", default=False,
             help="x / blank — run this row this tick."),
    ParamDef("purpose", None, "choice", default="D", choices=("P", "D"),
             help="P = production (steps 0-2 only), D = development (steps 0-4)."),
    ParamDef("label", None, "str", default="",
             help="Sheet/column header on the output board. Blank = auto-derived."),
    ParamDef("note", None, "str", default="",
             help="Free text, carried through to the output board unchanged."),

    # --- step 0: group definition + data procurement --------------------------
    ParamDef("group_expression", 0, "expr", required=True,
             help="e.g. Stamdata.Zone='NY' .and. Stamdata.GICS, or #ALL. "
                  "A bare Stamdata column is a grouping dimension; a comparison is a "
                  "universe filter; .and. joins terms."),

    # --- step 1: group dominance (levels A/B/C) --------------------------------
    ParamDef("level", 1, "choice", default="A", choices=LEVELS,
             help="A = today's dominance, B = 20d-persistent, C = 50d-persistent."),
    ParamDef("persistence_window", 1, "int", default=None,
             help="Trailing daynums for B/C persistence. Default: 20 for B, 50 for C. "
                  "Ignored for level A."),
    ParamDef("persistence_frac", 1, "float", default=2 / 3,
             help="Fraction of the trailing window that must have dominated (B/C only)."),
    ParamDef("dominance_attribute", 1, "str", default="rank",
             help="Longi factor short name (longi_<name>.csv) deciding group elevation."),
    ParamDef("dominance_direction", 1, "direction", default=True, parser=parse_direction,
             help="small_wins or big_wins for dominance_attribute."),
    ParamDef("dominance_decile", 1, "float", default=0.10,
             help="Fraction of that day's own cross-sectional distribution a ticker must "
                  "be within to qualify (0.10 = best decile)."),
    ParamDef("dom_count_min", 1, "int", default=3,
             help="Absolute floor on qualifying tickers a group needs to dominate."),
    # dom_count_frac is deliberately NOT a board column (SM, 2026-08-03): a group only counts
    # as dominant when over-represented among today's qualifiers relative to the population
    # base rate, which means it must always sit above dominance_decile -- there is no
    # meaningful per-row value for it to hold independently. step1_dominance.py derives it as
    # dominance_decile + shared.config.DOM_COUNT_FRAC_MARGIN. (v1-parity testing, which used
    # dom_count_frac=0 to reproduce v1's fixed absolute count exactly, is done and recorded in
    # DesignVersion2.md -- not an ongoing board capability.)
    ParamDef("tickers_per_group", 1, "int", default=3,
             help="Top candidates drawn from EACH dominating group into the pooled "
                  "test-set (per level: A=3, B=4, C=5 is SM's proposal)."),

    # --- step 2: filtering, sorting, gross list --------------------------------
    ParamDef("post_filter", 2, "expr", default="",
             help="e.g. Longi.per1d>0. Applied after Step-1 pooling; blank = none."),
    ParamDef("priority_attribute", 2, "str", default="rank",
             help="Longi factor short name ranking candidates within/across groups."),
    ParamDef("priority_direction", 2, "direction", default=True, parser=parse_direction,
             help="small_wins or big_wins for priority_attribute."),
    ParamDef("from_rank", 2, "from_rank", default=1, parser=parse_from_rank,
             help="Window of the ranked pool to draw the focusset from: 1=best n, "
                  "-1=worst n, 'mid' or a float in (0,1)=pool-relative window, "
                  "an integer k>=2=fixed offset. See param_spec.parse_from_rank."),
    ParamDef("focusset_size", 2, "int", default=5,
             help="Tickers in the final pick (gross-list size 10-20 typical in production)."),

    # --- step 3: backtest -------------------------------------------------------
    ParamDef("period", 3, "int", default=20, choices=tuple(str(p) for p in FUTURE_PERIODS),
             help="Forward horizon in trading days; must be a member of the seven-pack "
                  "(1/5/10/20/50/100/200)."),
    ParamDef("no_go_gspc_rsi", 3, "int", default=0,
             help="Suppress picks / chain hops when GSPC RSI (at daynum) < this. 0 = off."),
    ParamDef("informational_attributes", 3, "list_str", default=(),
             help="Comma-separated Longi factor names shown for insight only; never "
                  "affects selection."),
    ParamDef("stop_loss", 3, "float", default=0.0, parser=parse_stop_loss,
             help="Step 3a exit level, e.g. -10. A ticker whose longi_future_minaggr<period>d "
                  "(worst drawdown from entry) breaches this has its lot gain capped here for "
                  "the rest of the hold. 0/blank = off (today's behaviour). Requires "
                  "period in {20, 50} -- the only horizons minaggr covers."),

    # --- step 4: forward-walk ----------------------------------------------------
    ParamDef("wf_group", 4, "str", default="",
             help="Candidate pool (by label, comma-separated) for selection-skill "
                  "scoring. Blank = every other active D-purpose row."),
]

PARAMS_BY_NAME: dict[str, ParamDef] = {p.name: p for p in PARAMS}


def format_value(name: str, value: Any) -> Any:
    """A resolved value written back in the spelling the BOARD uses.

    Every report that shows a parameter must go through this. A resolved row holds parsed
    internals — `dominance_direction` is a bool, `from_rank` is a ("edge", -1) tuple — and
    writing those straight to a sheet reintroduces exactly the unreadable forms this schema
    exists to eliminate: `big_wins` came back as Excel's FALSE (a direction cannot be false),
    and `from_rank` as a raw tuple naming an internal classifier the board never mentions.
    Both were reported from live output on 2026-08-04.
    """
    pdef = PARAMS_BY_NAME.get(name)
    if pdef is None or value is None:
        return value
    if pdef.dtype == "direction":
        return format_direction(bool(value))
    if pdef.dtype == "from_rank":
        return format_from_rank(value) if isinstance(value, tuple) else value
    if pdef.dtype == "list_str" and isinstance(value, (tuple, list)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, tuple):
        return str(value)
    return value

# Column order on the Runs sheet — meta first, then step order, declaration order within.
RUNS_COLUMNS: list[str] = [p.name for p in PARAMS]


@dataclass(frozen=True)
class SettingDef:
    name: str
    dtype: str
    default: Any
    help: str = ""


SETTINGS: list[SettingDef] = [
    SettingDef("min_chain_lots", "int", 3,
               "Lots a run's chain must realize before it may represent its row on the "
               "Step3_compare sheet (eligibility floor, not a hard stop — see strategy_grp "
               "CLAUDE.md's MIN_CHAIN_LOTS write-up)."),
    SettingDef("wf_min_train", "int", 315, "Walk-forward: minimum training window (daynums)."),
    SettingDef("wf_test_len", "int", 63, "Walk-forward: test window length (daynums)."),
    SettingDef("archive_on_run", "bool", True,
               "Move prior dated output workbooks to _archive/ once new output exists."),
    SettingDef("production_strategy_count", "int", 3,
               "How many P-purpose rows' gross lists ship in StrategicStocks.xlsx."),
    SettingDef("stop_sweep", "str", "-5,-7.5,-10,-15,-20",
               "Comma-separated stop_loss levels Step3a_stopout re-scores each D row at "
               "(period in {20,50} only), alongside its own board stop_loss. Blank = no "
               "sweep sheet."),
    SettingDef("stop_annual_tolerance", "float", 5.0,
               "Step3a_stopout's risk-first pick: the tightest stop (best Worst/N_loss) "
               "whose chain_annual gives up no more than this many percent of the "
               "unstopped baseline is flagged best."),
]

SETTINGS_BY_NAME: dict[str, SettingDef] = {s.name: s for s in SETTINGS}
