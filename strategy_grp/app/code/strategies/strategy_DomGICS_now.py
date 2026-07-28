"""
Strategy: DomGICS_now — on each daynum, a GICS sector is "dominating" when at least
dom_count_threshold of its tickers score below dominance_threshold_decile on dominance_attribute
(longi_{dominance_attribute}.csv, default "rank") THAT day. Dominating sectors contribute
their tickers_per_gics best tickers by priority_attribute (longi_{priority_attribute}.csv);
the pool is re-ranked globally and focusset_size/from_rank applied.
See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomGICS_now"

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

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_now")


if __name__ == "__main__":
    main()
