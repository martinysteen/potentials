"""
Strategy: DomGICS_50d — like DomGICS_now, but a GICS sector must additionally have
held its "dominating" state (see strategy_DomGICS_now.py) on at least
persistence_frac of the trailing 50 daynums (inclusive of the current one) to
qualify.

Twin: strategy_DomSector2_50d.py. See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomGICS_50d"
GROUP_COLUMN  = "GICS"        # Stamdata.csv column to group by (13 values, ~93 tickers each)

PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN)

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_50d")


if __name__ == "__main__":
    main()
