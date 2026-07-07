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

# Alias -> the real param keys it fans out to (each strategy gets the ones it has).
LINKED: dict[str, list[str]] = {}

# Fixed left-to-right column order for best_strategy.xlsx (both the chained and ladder
# tables). Was previously sorted by chain_annual, but that reshuffles every time a swept
# parameter changes performance, making the report hard to read run over run. A strategy
# not listed here is placed after all listed ones (in whatever order pandas/groupby gives).
STRATEGY_ORDER: list[str] = [
    "Cross2050",
    "Cross1020",
    "Ranknow",
]

# Applied to every strategy below (where the key exists in that strategy's PARAMS).
# Multiple values offered by list format like "step": [1, 5]
DEFAULTS: dict = {
    "focusset_size":  5,
    "step":           5,            # fixed at 1: finest phase-averaging for the chain;
                                          # step is otherwise second-order for the chain metric.
    "period":         20,           # forward horizon in trading days (20 or 50). Single
                                          # value -> one column per strategy in best_strategy.
    "No_go_GSPC_rsi": 0,            # 0 = filter off; 40 = typical. Swept so Summary
                                          # metrics (chain_*, avg_gain, N_loss) reflect each.
    "from_rank":      1          # WHERE in the rank-ordered survivor set to draw the
                                          # focusset from (smaller longi_rank == better):
                                          #   1   -> the best n            (classic top-pick)
                                          #   k>1 -> skip the best k-1, take the next n
                                          #          (e.g. 4 -> ranks 4..3+n, "avoid the top")
                                          #   -1  -> the worst n           (take from the bottom)
                                          # A list sweeps it as one axis, e.g. [1, 4, -1].
}

# Strategy-specific overrides. An empty dict {} means "just use DEFAULTS".
# Keys must match each strategy's STRATEGY_NAME (see `python run_sweep.py --list`).
STRATEGIES: dict[str, dict] = {
    # --- a single cross quotient (1-step) ---
    "Cross1020": {"q10_20_min": 1.03},
    "Cross2050": {"q20_50_min": 1.05},

    # --- rank only ---
    "Ranknow": {},

    # NOTE: the plain ZOP strategy is parked in code/_not_used/ (and its reports
    # in report/_not_used/). ZOP is a good signal but too volatile intraday;
    # refining it is postponed in favour of the more stable cross strategies.
    # Move the files back to restore it. All probability-based strategies
    # (P20*, P50*, P20P50*, P??dZOP) were DELETED 2026-07-07 — the win/loss
    # probability model was retired (see longi/expAdviceModel/ report).
}
