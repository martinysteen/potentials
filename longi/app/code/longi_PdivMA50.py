"""
Price / MA50 Ratio Module

Calculates the ratio of current price to 50-day moving average, expressed as percentage.

Formula: P/MA50 = (current_price / ma50) * 100

Values > 100: price above MA50 (bullish)
Values < 100: price below MA50 (bearish)

Depends on: longi_ma50.py (needs longi_ma50.csv)
Reads PotDat.csv and longi_ma50.csv, outputs longi_PdivMA50.csv with identical structure.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_PRICE_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
INPUT_MA_FILE = Path(__file__).parent.parent / "output" / "longi_ma50.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_PdivMA50.csv"


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


def calculate_price_ma_ratio(prices: List[Optional[float]], ma_values: List[Optional[float]]) -> List[Optional[float]]:
    """
    Calculate ratio of price to MA50, expressed as percentage.

    Args:
        prices: List of prices
        ma_values: List of MA50 values

    Returns:
        List of P/MA ratios (None where either input is None)
    """
    if len(prices) != len(ma_values):
        raise ValueError("Price and MA arrays must have same length")

    ratios = []
    for price, ma in zip(prices, ma_values):
        if price is not None and ma is not None and ma > 0:
            ratio = (price / ma) * 100
            ratios.append(ratio)
        else:
            ratios.append(None)

    return ratios


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"=== longi_PdivMA50.py START: Price / MA50 ratio calculation ===")

    # Check input files exist
    if not INPUT_PRICE_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_PRICE_FILE}")
        return 1

    if not INPUT_MA_FILE.exists():
        print(f"ERROR: MA50 file not found: {INPUT_MA_FILE}")
        print(f"       Run longi_ma50.py first to generate this file")
        return 1

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read price CSV
        print(f"1. Reading price file: {INPUT_PRICE_FILE.name}")
        with open(INPUT_PRICE_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            price_rows = list(reader)

        # Read MA50 CSV
        print(f"2. Reading MA50 file: {INPUT_MA_FILE.name}")
        with open(INPUT_MA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            ma_header = next(reader)
            ma_rows = list(reader)

        # Validate headers match
        if header != ma_header:
            print(f"ERROR: Headers don't match between price and MA files")
            return 1

        print(f"3. Loaded {len(price_rows)} tickers with {len(header)-1} daynum columns")

        # Create ticker lookup for MA data
        ma_dict = {row[0]: row[1:] for row in ma_rows}

        # Process each ticker
        output_rows = []
        tickers_processed = 0
        tickers_skipped = 0

        print(f"4. Calculating P/MA50 ratios for {len(price_rows)} tickers...")
        for price_row in price_rows:
            ticker = price_row[0]
            price_strings = price_row[1:]

            # Get corresponding MA values
            if ticker not in ma_dict:
                print(f"WARNING: Ticker {ticker} not found in MA file, skipping")
                # Output empty row
                output_row = [ticker] + [''] * len(price_strings)
                output_rows.append(output_row)
                tickers_skipped += 1
                continue

            ma_strings = ma_dict[ticker]

            # Parse values
            prices = [parse_european_decimal(s) for s in price_strings]
            ma_values = [parse_european_decimal(s) for s in ma_strings]

            # Calculate ratios
            ratios = calculate_price_ma_ratio(prices, ma_values)

            # Format output row
            ratio_strings = [format_european_decimal(val) for val in ratios]
            output_row = [ticker] + ratio_strings
            output_rows.append(output_row)

            # Count processing stats
            if any(val is not None for val in ratios):
                tickers_processed += 1
            else:
                tickers_skipped += 1

        # Write output CSV
        print(f"5. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)  # Same header as input
            writer.writerows(output_rows)

        print(f"SUCCESS: {tickers_processed} tickers processed, {tickers_skipped} skipped (insufficient data)")

        return 0

    except Exception as e:
        print(f"ERROR: Error during P/MA ratio calculation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
