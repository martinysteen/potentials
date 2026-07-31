"""
Strategy: DomSector2_now — the DomGICS_now pipeline on the finer Sector2 grouping.

Sector2 is a genuine sub-partition of GICS: 48 of its 50 values sit inside exactly one GICS
(the exceptions, `Holiday` and `Other[Indu]`, leak by one or two tickers and look like
misclassifications). So this family is not a rival taxonomy but a **sharpening of which
groups get promoted through dominance** — a dominating `Indu` can be resolved ten ways,
while `Tele`/`Index` have a single child each and cannot be sharpened at all.

dom_count_threshold is therefore NOT the GICS value: Sector2 sectors average ~24 tickers
against GICS's ~93, and an absolute count does not transfer between them. See
run_config.DOM_COUNT_THRESHOLD.

Twin: strategy_DomGICS_now.py. See shared/dominance.py for the pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomSector2_now"
GROUP_COLUMN  = "Sector2"     # Stamdata.csv column to group by (50 values, ~24 tickers each)

PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN, period=20)

main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_now")


if __name__ == "__main__":
    main()
