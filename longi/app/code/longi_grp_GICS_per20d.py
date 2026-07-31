#!/usr/bin/env python3
"""
GICS sector-aggregated 20-day performance.

Reads:
- ../input/Stamdata.csv (ticker -> GICS mapping)
- ../output/longi_per20d.csv (per-ticker 20-day performance)

Writes:
- ../output/longi_grp_GICS_per20d.csv

Rows are GICS sector names, columns are the daynums of longi_per20d.csv, each
cell the mean of that sector's tickers. See aux_grp_shared.build_group_average.
"""

import sys

from aux_grp_shared import build_group_average

METRIC = "per20d"
GROUP_COL = "GICS"


def main() -> int:
    """Build longi_grp_GICS_per20d.csv. Returns 0 on success, 1 on failure."""
    return build_group_average(METRIC, group_col=GROUP_COL)


if __name__ == "__main__":
    sys.exit(main())
