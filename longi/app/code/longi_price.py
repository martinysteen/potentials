"""
Price Snapshot Module

Produces an exact copy of PotDat.csv as longi_price.csv.

Purpose:
(a) Allows referencing raw price data by the longi_ naming convention
(b) Records the exact PotDat.csv snapshot used to derive all other longi_*.csv
    files for this pipeline run, since PotDat.csv itself is updated
    asynchronously relative to the longi_*.csv outputs.

Reads PotDat.csv and outputs longi_price.csv as a byte-identical copy
(no reformatting, to guarantee it matches the input exactly).
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import shutil
import sys
from pathlib import Path

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_price.csv"


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Price snapshot (exact copy of PotDat.csv)")

    # Check input file exists
    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return 1

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        print(f"1. Copying {INPUT_FILE.name} -> {OUTPUT_FILE.name}")
        shutil.copyfile(INPUT_FILE, OUTPUT_FILE)

        print(f"SUCCESS: longi_price.csv written as exact copy of PotDat.csv")

        return 0

    except Exception as e:
        print(f"ERROR: Error during price snapshot copy: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
