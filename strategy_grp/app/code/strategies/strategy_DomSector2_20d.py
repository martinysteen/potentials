"""
Strategy: DomSector2_20d — like DomSector2_now, but a Sector2 sector must additionally
have held its "dominating" state on at least persistence_frac of the trailing 20 daynums
(inclusive of the current one) to qualify.

Watch this tier especially: 5-of-24 is a noisier promotion test than GICS's 10-of-93, so
the dominating set flickers more and the persistence gate may sit out far more often than
its GICS twin — which shows up as low chain_n / chain_inv% (or a MIN_CHAIN_LOTS flag)
rather than as bad returns. pick_turnover/group_turnover in the Summary sheet are there to
make that visible.

Twin: strategy_DomGICS_20d.py. See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomSector2_20d"
GROUP_COLUMN  = "Sector2"     # Stamdata.csv column to group by (50 values, ~24 tickers each)

PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN)

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_20d")


if __name__ == "__main__":
    main()
