"""
Strategy: DomGICS_50d — like DomGICS_now, but a GICS sector must additionally have
held its "dominating" state (see strategy_DomGICS_now.py) on at least
persistence_frac of the trailing 50 daynums (inclusive of the current one) to
qualify. See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomGICS_50d"

_dom_attr, _dom_dir = cfg.dominance_attribute_for(STRATEGY_NAME)

PARAMS: dict = {
    "focusset_size": cfg.FOCUSSET_SIZE,
    "step": cfg.STEP,
    "period": 20,               # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": cfg.NO_GO_GSPC_RSI,
    "from_rank": cfg.FROM_RANK,
    "dominance_threshold_decile": cfg.DOMINANCE_THRESHOLD_DECILE,
    "dom_count_threshold": cfg.DOM_COUNT_THRESHOLD,
    "persistence_frac": cfg.PERSISTENCE_FRAC,
    "tickers_per_gics": cfg.TICKERS_PER_GICS,
    "dominance_attribute": _dom_attr,
    "dominance_attribute_direction": _dom_dir,
    "priority_attribute": cfg.PRIORITY_ATTRIBUTE,
    "priority_attribute_direction": cfg.PRIORITY_ATTRIBUTE_DIRECTION,
    "informational_attributes": cfg.INFORMATIONAL_ATTRIBUTES,
}

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_50d")


if __name__ == "__main__":
    main()
