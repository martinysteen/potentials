"""
MA20 / MA50 Quotient Module (speed indicator)

Calculates the ratio of the 20-day to the 50-day moving average, expressed as
percentage. Measures medium-term momentum acceleration ("Cross2050 as a
quotient"): the faster MA pulling away above the slower one.

Formula: quot2050 = (ma20 / ma50) * 100

Values > 100: MA20 above MA50 (accelerating / bullish)
Values < 100: MA20 below MA50 (decelerating / bearish)

Depends on: longi_ma20.py and longi_ma50.py (needs longi_ma20.csv, longi_ma50.csv)
Reads both MA files, outputs longi_quot2050.csv with identical structure.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_MA_FAST_FILE = Path(__file__).parent.parent / "output" / "longi_ma20.csv"
INPUT_MA_SLOW_FILE = Path(__file__).parent.parent / "output" / "longi_ma50.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_quot2050.csv"
LABEL_FAST = "MA20"
LABEL_SLOW = "MA50"


def parse_european_decimal(value: str) -> Optional[float]:
    """
    Parse European decimal format (comma as decimal separator).

    Args:
        value: String value to parse (e.g., "123,45")

    Returns:
        Float value or None if empty/invalid
    """
    value = value.strip()
    if not value:
        return None
    try:
        # Replace comma with dot for Python float parsing
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def format_european_decimal(value: Optional[float], decimals: int = 2) -> str:
    """
    Format float to European decimal format (comma as decimal separator).

    Args:
        value: Float value to format
        decimals: Number of decimal places

    Returns:
        Formatted string or empty string if value is None
    """
    if value is None:
        return ""
    # Format with specified decimals and replace dot with comma
    return f"{value:.{decimals}f}".replace('.', ',')


def calculate_ma_quotient(fast_values: List[Optional[float]], slow_values: List[Optional[float]]) -> List[Optional[float]]:
    """
    Calculate ratio of fast MA to slow MA, expressed as percentage.

    Args:
        fast_values: List of fast MA values (shorter window)
        slow_values: List of slow MA values (longer window)

    Returns:
        List of quotients (None where either input is None)
    """
    if len(fast_values) != len(slow_values):
        raise ValueError("Fast and slow MA arrays must have same length")

    quotients = []
    for fast, slow in zip(fast_values, slow_values):
        if fast is not None and slow is not None and slow > 0:
            quotient = (fast / slow) * 100
            quotients.append(quotient)
        else:
            quotients.append(None)

    return quotients


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"{LABEL_FAST} / {LABEL_SLOW} quotient calculation")

    # Check input files exist
    if not INPUT_MA_FAST_FILE.exists():
        print(f"ERROR: {LABEL_FAST} file not found: {INPUT_MA_FAST_FILE}")
        print(f"       Run the {LABEL_FAST} module first to generate this file")
        return 1

    if not INPUT_MA_SLOW_FILE.exists():
        print(f"ERROR: {LABEL_SLOW} file not found: {INPUT_MA_SLOW_FILE}")
        print(f"       Run the {LABEL_SLOW} module first to generate this file")
        return 1

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read fast MA CSV
        print(f"1. Reading {LABEL_FAST} file: {INPUT_MA_FAST_FILE.name}")
        with open(INPUT_MA_FAST_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            fast_header = next(reader)
            fast_rows = list(reader)

        # Read slow MA CSV
        print(f"2. Reading {LABEL_SLOW} file: {INPUT_MA_SLOW_FILE.name}")
        with open(INPUT_MA_SLOW_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            slow_header = next(reader)
            slow_rows = list(reader)

        # Validate headers match
        if fast_header != slow_header:
            print(f"ERROR: Headers don't match between {LABEL_FAST} and {LABEL_SLOW} files")
            return 1

        print(f"3. Loaded {len(fast_rows)} tickers with {len(fast_header)-1} daynum columns")

        # Create ticker lookup for slow MA data
        slow_dict = {row[0]: row[1:] for row in slow_rows}

        # Process each ticker
        output_rows = []
        tickers_processed = 0
        tickers_skipped = 0

        print(f"4. Calculating {LABEL_FAST}/{LABEL_SLOW} quotients for {len(fast_rows)} tickers...")
        for fast_row in fast_rows:
            ticker = fast_row[0]
            fast_strings = fast_row[1:]

            # Get corresponding slow MA values
            if ticker not in slow_dict:
                print(f"WARNING: Ticker {ticker} not found in {LABEL_SLOW} file, skipping")
                # Output empty row
                output_row = [ticker] + [''] * len(fast_strings)
                output_rows.append(output_row)
                tickers_skipped += 1
                continue

            slow_strings = slow_dict[ticker]

            # Parse values
            fast_values = [parse_european_decimal(s) for s in fast_strings]
            slow_values = [parse_european_decimal(s) for s in slow_strings]

            # Calculate quotients
            quotients = calculate_ma_quotient(fast_values, slow_values)

            # Format output row
            quotient_strings = [format_european_decimal(val) for val in quotients]
            output_row = [ticker] + quotient_strings
            output_rows.append(output_row)

            # Count processing stats
            if any(val is not None for val in quotients):
                tickers_processed += 1
            else:
                tickers_skipped += 1

        # Write output CSV
        print(f"5. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(fast_header)  # Same header as input
            writer.writerows(output_rows)

        print(f"SUCCESS: {tickers_processed} tickers processed, {tickers_skipped} skipped (insufficient data)")

        return 0

    except Exception as e:
        print(f"ERROR: Error during MA quotient calculation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
