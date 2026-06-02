"""
Global Decile Boundary Calculator

Calculates global decile boundaries for each numeric indicator by pooling
ALL values across ALL tickers and ALL daynums from each longi_*.csv file.

Output: app/output/aux_deciles.csv
Columns: Indicator;Decile;UpperLimit;LowerLimit

Output goes to stdout - the orchestrator handles logging redirection.
"""

import csv
import sys
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple

# Configuration
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR_GRP = Path(__file__).parent.parent / "output_grp"


def parse_european_float(value: str) -> Optional[float]:
    """Parse a European-format decimal string to float."""
    if not value or not value.strip():
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def format_european(value: float, decimals: int = 2) -> str:
    """Format a float as European decimal string."""
    return f"{value:.{decimals}f}".replace(".", ",")


def get_indicator_files() -> List[Tuple[str, Path]]:
    """
    Discover all indicator files from output/ and output_grp/ directories.

    Returns:
        List of (indicator_name, filepath) tuples, sorted by indicator name
    """
    files = []

    # Individual indicator files
    for f in sorted(OUTPUT_DIR.glob("longi_*.csv")):
        name = f.stem.removeprefix("longi_")  # e.g., "rsi", "macd_line"
        files.append((name, f))

    # Group aggregation files
    for f in sorted(OUTPUT_DIR_GRP.glob("longi_grp_*.csv")):
        name = f.stem.removeprefix("longi_")  # e.g., "grp_GICS_1yr"
        files.append((name, f))

    return files


def read_all_values(filepath: Path) -> List[float]:
    """
    Read all numeric values from a longi_*.csv file.

    Reads every cell (except header row and first column/ticker),
    parses European decimals, and returns a flat list of all values.

    Args:
        filepath: Path to the CSV file

    Returns:
        List of float values (empty/non-numeric cells excluded)
    """
    values = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # skip header
        for row in reader:
            for cell in row[1:]:  # skip ticker column
                val = parse_european_float(cell)
                if val is not None:
                    values.append(val)
    return values


def compute_deciles(values: List[float]) -> List[Tuple[int, float, float]]:
    """
    Compute decile boundaries for a list of values.

    Decile 1 = lowest values, Decile 10 = highest values.

    Returns:
        List of (decile, upper_limit, lower_limit) tuples
    """
    arr = np.array(values)
    boundaries = [float(np.percentile(arr, p)) for p in range(10, 100, 10)]
    min_val = float(np.min(arr))
    max_val = float(np.max(arr))

    result = []
    for d in range(1, 11):
        lower = min_val if d == 1 else boundaries[d - 2]
        upper = max_val if d == 10 else boundaries[d - 1]
        result.append((d, upper, lower))

    return result


def main() -> int:
    """Main execution function."""
    print("aux_deciles.py: Global decile boundary calculation")

    # Discover indicator files
    indicator_files = get_indicator_files()
    if not indicator_files:
        print("ERROR: No longi_*.csv files found in output/ or output_grp/")
        return 1

    print(f"  Found {len(indicator_files)} indicator files")

    # Process each indicator
    output_rows = []
    processed = 0
    skipped = []

    for name, filepath in indicator_files:
        values = read_all_values(filepath)

        if len(values) < 10:
            skipped.append(name)
            continue

        deciles = compute_deciles(values)
        for decile, upper, lower in deciles:
            output_rows.append((name, decile, format_european(upper), format_european(lower)))

        processed += 1

    # Write output
    output_file = OUTPUT_DIR / "aux_deciles.csv"
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Indicator", "Decile", "UpperLimit", "LowerLimit"])
        for row in output_rows:
            writer.writerow(row)

    print(f"\nSUCCESS: Decile boundaries calculated")
    print(f"  Indicators: {processed}")
    print(f"  Rows: {len(output_rows)}")
    print(f"  Output: {output_file.name}")
    if skipped:
        print(f"  Skipped (non-numeric or < 10 values): {', '.join(skipped)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
