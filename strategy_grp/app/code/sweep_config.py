"""
Curated parameter sweep — the single place you edit to decide *what gets run*.

How it is read by run_sweep.py
------------------------------
For every strategy listed in STRATEGIES:

    effective params = strategy's own PARAMS
                       overlaid with DEFAULTS        (common to all strategies)
                       overlaid with its own entry   (strategy-specific)

    Only keys the strategy actually defines in its PARAMS are kept, so putting
    e.g. q20_50_min in DEFAULTS is harmless for strategies that don't use it.

A value may be a single number OR a list:
    "focusset_size": 3          -> one value
    "focusset_size": [1, 3, 5]  -> a grid axis

All list-valued params are expanded as a cartesian product, so

    DEFAULTS = {"focusset_size": [1, 3, 5], "step": [1, 5]}

yields 3 x 2 = 6 runs per strategy (times any other grid axis).

Linked params (LINKED)
----------------------
Some strategies may define two params that must stay equal. Rather than set
them twice — which a grid would also let drift apart — declare a single alias
in LINKED; the driver writes its value to whichever of the real keys a
strategy actually has. An alias may itself be a list to sweep the pair as ONE
axis (they stay equal at every value). Currently no aliases are needed.

Sweeping priority_attribute
----------------------------
priority_attribute is the Step-2 test-set-construction attribute (see run_config.py) —
it is NOT a plain grid axis like the ones above, because it is paired with
priority_attribute_direction (True = smaller wins, False = bigger wins), and getting
that pairing wrong silently inverts which tickers are "best" within each dominating
group. So:

    DEFAULTS = {"priority_attribute": ["rank", "beta3m", "vola100d"]}

tries each name in its own run, deriving priority_attribute_direction for each from
run_config.PRIORITY_ATTRIBUTE_DICTIONARY — it is never read from DEFAULTS/
STRATEGIES directly while priority_attribute is being swept (setting it there
too is a hard error), and sweeping a name absent from that dict is also a hard
error rather than a silent wrong default. Add the name's direction to
PRIORITY_ATTRIBUTE_DICTIONARY in run_config.py before adding it here.

Only strategies that appear as keys in STRATEGIES are touched. Their existing
run*.xlsx are archived (moved to <strategy>/_archive/<timestamp>/) and rebuilt
fresh; strategies not listed here are left completely alone.

Tip: `python run_sweep.py --list` prints every strategy name you can use as a
key here; `python run_sweep.py --dry-run` shows how many runs each will produce
without touching any files.
"""

import run_config as cfg

# Params whose value is a fixed multi-item list, never a sweep grid — do NOT add these
# to DEFAULTS or a STRATEGIES override entry. expand_runs() can't tell "list = grid axis"
# from "list = one run's fixed multi-value param" by looking at the value alone, so
# run_sweep.build_plan() hard-fails if one of these ever shows up in a sweep spec.
# informational_attributes: a list here means several Step-3 display-only factors shown
# in ONE run's report (see shared/report.py / shared/extension.py) — never feeds
# selection (shared/dominance.select_focusset); it is set once via run_config.py, not swept.
# group_column is here for a second reason: its value is a plain string, so a list WOULD
# expand as a grid axis — but sweeping it would drop two different group criteria into one
# strategy's report directory, where the comparison sheet has no way to tell them apart. The
# group criterion defines the family and is fixed in the strategy module (see run_config.py's
# "fourth role" note); the way to test another one is another strategy, not another run.
NON_SWEEPABLE: set[str] = {"informational_attributes", "group_column"}

# Alias -> the real param keys it fans out to (each strategy gets the ones it has).
LINKED: dict[str, list[str]] = {}

# Fixed left-to-right column order for best_strategy.xlsx (both the chained and ladder
# tables). Was previously sorted by chain_annual, but that reshuffles every time a swept
# parameter changes performance, making the report hard to read run over run. A strategy
# not listed here is placed after all listed ones (in whatever order pandas/groupby gives).
STRATEGY_ORDER: list[str] = ["DomGICS_now", "DomGICS_20d", "DomGICS_50d",
                             "DomSector2_now", "DomSector2_20d", "DomSector2_50d"]

# Applied to every strategy below (where the key exists in that strategy's PARAMS).
# Values default to run_config.py — the single source of truth for a resting value — so
# changing e.g. run_config.NO_GO_GSPC_RSI takes effect here automatically. Overwrite an
# entry with a literal or a list ONLY when a sweep run should deliberately diverge from
# that resting value (a list expands as a grid axis, e.g. "step": [1, 5]).
DEFAULTS: dict = {
    "focusset_size":  cfg.FOCUSSET_SIZE,
    "step":           cfg.STEP,     # fixed at 1: finest phase-averaging for the chain;
                                          # step is otherwise second-order for the chain metric.
    "period":         cfg.PERIOD,   # forward horizon in trading days; must be a member of
                                          # shared.config.FUTURE_PERIODS, the "seven-pack"
                                          # (1/5/10/20/50/100/200). Single value -> one column
                                          # per strategy in best_strategy.
    "No_go_GSPC_rsi": cfg.NO_GO_GSPC_RSI,  # 0 = filter off; 40-50 = typical.
    "from_rank":      cfg.FROM_RANK,  # Which end of the priority_attribute ranking to draw
                                          # the focusset from (direction-aware — see
                                          # PRIORITY_ATTRIBUTE_DICTIONARY):
                                          #   1   -> the best n            (classic top-pick)
                                          #   -1  -> the worst n           (take from the bottom)
                                          # A list sweeps it as one axis, e.g. [1, -1].
    "priority_attribute": list(cfg.PRIORITY_ATTRIBUTE_DICTIONARY),  # try every registered
                                          # name, one run each — direction is derived per
                                          # name from cfg.PRIORITY_ATTRIBUTE_DICTIONARY (see
                                          # "Sweeping priority_attribute" above). Trim this
                                          # list to test fewer of them.
}

# Strategy-specific overrides. An empty dict {} means "just use DEFAULTS".
# Keys must match each strategy's STRATEGY_NAME (see `python run_sweep.py --list`).
STRATEGIES: dict[str, dict] = {
    # Two families, same three-step pipeline, different group criterion (see run_config.py).
    # They compete as six columns in one best_strategy.xlsx — Sector2 is an alternative to
    # GICS, not a replacement for it.
    "DomGICS_now": {},
    "DomGICS_20d": {},
    "DomGICS_50d": {},
    "DomSector2_now": {},
    "DomSector2_20d": {},
    "DomSector2_50d": {},
}
