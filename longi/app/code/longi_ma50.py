"""
50-day Simple Moving Average Module

Calculates 50-day SMA (Simple Moving Average) of stock prices.

Formula: SMA = sum(prices_over_50_days) / 50

Reads PotDat.csv and outputs longi_ma50.csv with identical structure.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_ma50.csv"
WINDOW_SIZE = 50


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


def calculate_ma50(prices: List[float]) -> List[Optional[float]]:
    """
    Calculate 50-day simple moving average.

    Array layout: [0]=newest (2009), [n-1]=oldest (1543)
    For day at index i, the 50-day window includes [i:i+50] (current day + 49 preceding days)

    Args:
        prices: List of prices from newest to oldest (left to right in CSV)

    Returns:
        List of MA50 values (same length as prices, None where calculation not possible)
    """
    n = len(prices)
    if n < WINDOW_SIZE:
        return [None] * n

    ma_values = []

    for i in range(n):
        # Get 50-day window: current day + 49 preceding days
        window_end = min(i + WINDOW_SIZE, n)
        window = prices[i:window_end]

        # Need full window to calculate
        if len(window) < WINDOW_SIZE:
            ma_values.append(None)
            continue

        # Calculate simple moving average
        ma = sum(window) / WINDOW_SIZE
        ma_values.append(ma)

    return ma_values


def process_ticker_row(ticker: str, price_strings: List[str]) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate 50-day MA.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV

    Returns:
        List of MA50 values (None where calculation not possible)
    """
    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) < WINDOW_SIZE:
        # Insufficient data - return all None values matching input length
        return [None] * len(price_strings)

    # Calculate MA for valid prices
    ma_values = calculate_ma50(prices)

    # Pad with None for the empty values we didn't process
    remaining = len(price_strings) - len(prices)
    ma_values.extend([None] * remaining)

    return ma_values


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"50-day simple moving average calculation")

    # Check input file exists
    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return 1

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read input CSV
        print(f"1. Reading input file: {INPUT_FILE.name}")
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rows = list(reader)

        print(f"2. Loaded {len(rows)} tickers with {len(header)-1} daynum columns")

        # Process each ticker
        output_rows = []
        tickers_processed = 0
        tickers_skipped = 0

        print(f"3. Calculating 50-day MA for {len(rows)} tickers...")
        for row in rows:
            ticker = row[0]
            price_strings = row[1:]

            # Calculate MA
            ma_values = process_ticker_row(ticker, price_strings)

            # Format output row
            ma_strings = [format_european_decimal(val) for val in ma_values]
            output_row = [ticker] + ma_strings
            output_rows.append(output_row)

            # Count processing stats
            if any(val is not None for val in ma_values):
                tickers_processed += 1
            else:
                tickers_skipped += 1

        # Write output CSV
        print(f"4. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)  # Same header as input
            writer.writerows(output_rows)

        print(f"SUCCESS: {tickers_processed} tickers processed, {tickers_skipped} skipped (insufficient data)")

        return 0

    except Exception as e:
        print(f"ERROR: Error during MA calculation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
