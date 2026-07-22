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

Only strategies that appear as keys in STRATEGIES are touched. Their existing
run*.xlsx are archived (moved to <strategy>/_archive/<timestamp>/) and rebuilt
fresh; strategies not listed here are left completely alone.

Tip: `python run_sweep.py --list` prints every strategy name you can use as a
key here; `python run_sweep.py --dry-run` shows how many runs each will produce
without touching any files.
"""

import run_config as cfg

# Alias -> the real param keys it fans out to (each strategy gets the ones it has).
LINKED: dict[str, list[str]] = {}

# Fixed left-to-right column order for best_strategy.xlsx (both the chained and ladder
# tables). Was previously sorted by chain_annual, but that reshuffles every time a swept
# parameter changes performance, making the report hard to read run over run. A strategy
# not listed here is placed after all listed ones (in whatever order pandas/groupby gives).
STRATEGY_ORDER: list[str] = ["DomGICS_now", "DomGICS_20d", "DomGICS_50d"]

# Applied to every strategy below (where the key exists in that strategy's PARAMS).
# Values default to run_config.py — the single source of truth for a resting value — so
# changing e.g. run_config.NO_GO_GSPC_RSI takes effect here automatically. Overwrite an
# entry with a literal or a list ONLY when a sweep run should deliberately diverge from
# that resting value (a list expands as a grid axis, e.g. "step": [1, 5]).
DEFAULTS: dict = {
    "focusset_size":  cfg.FOCUSSET_SIZE,
    "step":           cfg.STEP,     # fixed at 1: finest phase-averaging for the chain;
                                          # step is otherwise second-order for the chain metric.
    "period":         20,           # forward horizon in trading days (20 or 50). Single
                                          # value -> one column per strategy in best_strategy.
    "No_go_GSPC_rsi": cfg.NO_GO_GSPC_RSI,  # 0 = filter off; 40-50 = typical.
    "from_rank":      cfg.FROM_RANK,  # Which end of the info_attribute ranking to draw the
                                          # focusset from (info_attribute is always "bigger wins"):
                                          #   1   -> the best n            (classic top-pick)
                                          #   -1  -> the worst n           (take from the bottom)
                                          # A list sweeps it as one axis, e.g. [1, -1].
}

# Strategy-specific overrides. An empty dict {} means "just use DEFAULTS".
# Keys must match each strategy's STRATEGY_NAME (see `python run_sweep.py --list`).
STRATEGIES: dict[str, dict] = {
    "DomGICS_now": {},
    "DomGICS_20d": {},
    "DomGICS_50d": {},
}
