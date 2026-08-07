"""
Strategy: DomSector2_50d — like DomSector2_now, but a Sector2 sector must additionally
have held its "dominating" state on at least persistence_frac of the trailing 50 daynums
(inclusive of the current one) to qualify.

The strictest tier on the noisiest promotion test — see strategy_DomSector2_20d.py's note
on flicker and why a thin chain here is the expected failure mode rather than a bad one.

Twin: strategy_DomGICS_50d.py. See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomSector2_50d"
GROUP_COLUMN  = "Sector2"     # Stamdata.csv column to group by (50 values, ~24 tickers each)

PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN)

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_50d")


if __name__ == "__main__":
    main()
