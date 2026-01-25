"""
RSI14 Calculation Module - Wilder's Method

Calculates 14-period Relative Strength Index using Wilder's smoothing method.
Reads PotDat.csv and outputs longi_rsi.csv with identical structure.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_rsi.csv"
RSI_PERIOD = 14


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


def calculate_rsi_wilder(prices: List[float]) -> List[Optional[float]]:
    """
    Calculate RSI using Wilder's smoothing method.

    Wilder's RSI must be calculated sequentially from oldest to newest because
    each calculation depends on the previous smoothed average.

    Process:
    1. Start from the oldest data (rightmost in array)
    2. Calculate first 14 changes
    3. First RSI uses simple average of those 14 changes
    4. Subsequent RSI values use Wilder's smoothing moving toward newer data

    Array layout: [0]=newest (2009), [n-1]=oldest (1543)
    Calculation proceeds from right to left (oldest to newest)

    Args:
        prices: List of prices from newest to oldest (left to right in CSV)

    Returns:
        List of RSI values (same length as prices, None where calculation not possible)
    """
    n = len(prices)
    if n < RSI_PERIOD + 1:  # Need at least 15 prices
        return [None] * n

    rsi_values = [None] * n

    # Reverse arrays to work oldest→newest (easier to think about)
    prices_reversed = prices[::-1]  # Now [0]=oldest, [n-1]=newest

    # Calculate price changes oldest→newest
    # change[i] = prices_reversed[i+1] - prices_reversed[i] (newer - older)
    changes = []
    for i in range(n - 1):
        changes.append(prices_reversed[i + 1] - prices_reversed[i])

    # Separate into gains and losses
    gains = [max(change, 0) for change in changes]
    losses = [abs(min(change, 0)) for change in changes]

    # Start at position 14 in reversed array (has 14 prior periods of data)
    # Calculate first average using changes at indices 0-13 (14 oldest changes)
    avg_gain = sum(gains[:RSI_PERIOD]) / RSI_PERIOD
    avg_loss = sum(losses[:RSI_PERIOD]) / RSI_PERIOD

    # Calculate first RSI at position 14 in reversed array
    if avg_loss == 0:
        rsi_reversed_14 = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_reversed_14 = 100 - (100 / (1 + rs))

    # Calculate remaining RSI values moving toward newer data (increasing index)
    rsi_values_reversed = [None] * n
    rsi_values_reversed[RSI_PERIOD] = rsi_reversed_14

    for i in range(RSI_PERIOD + 1, n):
        # Wilder's smoothing: update with the change at index i-1
        avg_gain = (avg_gain * 13 + gains[i - 1]) / RSI_PERIOD
        avg_loss = (avg_loss * 13 + losses[i - 1]) / RSI_PERIOD

        if avg_loss == 0:
            rsi_values_reversed[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values_reversed[i] = 100 - (100 / (1 + rs))

    # Reverse back to match original order (newest→oldest)
    rsi_values = rsi_values_reversed[::-1]

    return rsi_values


def process_ticker_row(ticker: str, price_strings: List[str]) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate RSI.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV

    Returns:
        List of RSI values (None where calculation not possible)
    """
    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) < RSI_PERIOD + 1:
        # Insufficient data - return all None values matching input length
        return [None] * len(price_strings)

    # Calculate RSI for valid prices
    rsi_values = calculate_rsi_wilder(prices)

    # Pad with None for the empty values we didn't process
    remaining = len(price_strings) - len(prices)
    rsi_values.extend([None] * remaining)

    return rsi_values


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"RSI14 calculation (Wilder's method)")

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

        print(f"3. Calculating RSI14 for {len(rows)} tickers...")
        for row in rows:
            ticker = row[0]
            price_strings = row[1:]

            # Calculate RSI
            rsi_values = process_ticker_row(ticker, price_strings)

            # Format output row
            rsi_strings = [format_european_decimal(val) for val in rsi_values]
            output_row = [ticker] + rsi_strings
            output_rows.append(output_row)

            # Count processing stats
            if any(val is not None for val in rsi_values):
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
        print(f"ERROR: Error during RSI calculation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
