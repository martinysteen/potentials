"""
Strategy: DomGICS_now — on each daynum, a GICS sector is "dominating" when at least
dom_count_threshold of its tickers score below dominance_threshold_decile on dominance_attribute
(longi_{dominance_attribute}.csv, default "rank") THAT day. Dominating sectors contribute
their tickers_per_group best tickers by priority_attribute (longi_{priority_attribute}.csv);
the pool is re-ranked globally and focusset_size/from_rank applied.

Twin: strategy_DomSector2_now.py — the identical pipeline on the finer Sector2 grouping.
Every parameter comes from run_config.dom_params(); see shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomGICS_now"
GROUP_COLUMN  = "GICS"        # Stamdata.csv column to group by (13 values, ~93 tickers each)

PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN)

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_now")


if __name__ == "__main__":
    main()
