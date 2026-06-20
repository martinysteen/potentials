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
Some strategies have two win-thresholds that must stay equal
(p20d_win_min == p50d_win_min). Rather than set them twice — which a grid would
also let drift apart — set the single alias `p_win_min`. The driver writes its
value to whichever of the two a strategy actually has:
    - both present  (cross1020, cross2050, P20dP50dZOP) -> both set equal
    - only one      (P20dWin/P20dZOP -> 20d; P50dWin/P50dZOP -> 50d)
    - neither       (ZOP, Ranknow) -> ignored
`p_win_min` may itself be a list to sweep the threshold as ONE axis (the pair
stays equal at every value), e.g. "p_win_min": [0.8, 0.9].

Only strategies that appear as keys in STRATEGIES are touched. Their existing
run*.xlsx are archived (moved to <strategy>/_archive/<timestamp>/) and rebuilt
fresh; strategies not listed here are left completely alone.

Tip: `python run_sweep.py --list` prints every strategy name you can use as a
key here; `python run_sweep.py --dry-run` shows how many runs each will produce
without touching any files.
"""

# Alias -> the real param keys it fans out to (each strategy gets the ones it has).
LINKED: dict[str, list[str]] = {
    "p_win_min": ["p20d_win_min", "p50d_win_min"],
}

# Applied to every strategy below (where the key exists in that strategy's PARAMS).
# No_go_GSPC_rsi is intentionally NOT here, so each strategy keeps its own value
# unless you override it per-strategy (or add it here to force one value on all).
DEFAULTS: dict = {
    "focusset_size": [1, 3, 5],
    "step":          [1, 5],
    "p_win_min":     [0.8, 0.9],          # -> p20d_win_min / p50d_win_min, kept equal
}

# Strategy-specific overrides. An empty dict {} means "just use DEFAULTS".
# Keys must match each strategy's STRATEGY_NAME (see `python run_sweep.py --list`).
STRATEGIES: dict[str, dict] = {
    # --- have both win-thresholds + the golden-cross quotient ---
    "P20P50cross1020": {"q10_20_min": [1.03, 1.10]},
    "P20P50cross2050": {"q20_50_min": [1.03, 1.10]},

    # --- have both win-thresholds, no quotient ---
    "P20dP50dZOP": {},

    # --- have a single win-threshold (p_win_min sets whichever exists) ---
    "P20dWin": {},
    "P20dZOP": {},
    "P50dWin": {},
    "P50dZOP": {},

    # --- no win-threshold (p_win_min ignored) ---
    "ZOP": {},
    "Ranknow": {},
}
