"""
Sector-Aggregated Performance Module

Builds every longi_grp_{Attribute}_per{N}d.csv table: one per (group column, metric)
combination, over the same "seven-pack" of longi_per*.csv metrics as longi_performance.py
(1d/5d/10d/20d/50d/100d/200d), for each grouping attribute (GICS, Sector2).

All the actual work — reading Stamdata.csv, grouping, writing the CSV — lives in
aux_grp_shared.build_group_average(metric, group_col); this module just enumerates the
(group_col, metric) pairs and reports on them, mirroring longi_performance.py's structure.
Consolidated from 14 separate one-metric wrapper scripts 2026-07-31 (same day as the
seven-pack rename) since the per-file scripts carried no logic of their own.

Output goes to stdout - start_longi.sh handles logging redirection.
"""

import sys

from aux_grp_shared import build_group_average

GROUP_COLS = ["GICS", "Sector2"]
METRICS = ["per1d", "per5d", "per10d", "per20d", "per50d", "per100d", "per200d"]


def main() -> int:
    """
    Build every longi_grp_{group_col}_{metric}.csv table.

    Returns:
        Exit code (0 = all succeeded, 1 = at least one failed)
    """
    print(f"Sector aggregation for {len(GROUP_COLS)} attribute(s) x {len(METRICS)} metric(s)")

    succeeded = []
    failed = []

    for group_col in GROUP_COLS:
        for metric in METRICS:
            print(f"\n--- {group_col} / {metric} ---")
            exit_code = build_group_average(metric, group_col)
            label = f"longi_grp_{group_col}_{metric}.csv"
            if exit_code == 0:
                succeeded.append(label)
            else:
                failed.append(label)

    print(f"\n=== SUMMARY ===")
    print(f"Generated {len(succeeded)}/{len(succeeded) + len(failed)} output files")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1

    print("SUCCESS: All sector-aggregated performance tables completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
