"""
Future Gain 20-Day Calculation Module

Calculates forward-looking 20-day percentage gains for backtesting.
Unlike performance modules (which assign gain to the end date),
this assigns the gain to the START date (the date when holding begins).

This is "foresight" data - the gain that WILL happen over the next 20 days.
Useful for backtesting strategies by seeing what would have happened.

Array layout: [0]=newest (e.g., 2009), [n-1]=oldest (e.g., 1543)
For future gain at index i, we compare with index i-20 (newer/future price).

Formula: ((future_price - current_price) / current_price) * 100

Output: future_gain20d.csv
- First 20 columns (from left) are empty (no future data available)
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "future_gain20d.csv"

PERIOD_DAYS = 20


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
    return f"{value:.{decimals}f}".replace('.', ',')


def calculate_future_gain(prices: List[float], period_days: int) -> List[Optional[float]]:
    """
    Calculate future percentage gain for a given time period.

    Array layout: [0]=newest (e.g., 2009), [n-1]=oldest (e.g., 1543)
    To calculate future gain at index i, we compare with index i-period_days (future price).

    Future gain formula: ((future - current) / current) * 100

    Args:
        prices: List of prices from newest to oldest
        period_days: Number of trading days to look forward

    Returns:
        List of future gain percentages (None where calculation not possible)
    """
    n = len(prices)
    future_gain = [None] * n

    # First period_days positions have no future data (they're the newest)
    # Calculate future gain for positions where we have future price data
    for i in range(period_days, n):
        current_price = prices[i]
        future_price = prices[i - period_days]

        if current_price != 0:  # Avoid division by zero
            gain = ((future_price - current_price) / current_price) * 100
            future_gain[i] = gain

    return future_gain


def process_ticker_row(ticker: str, price_strings: List[str], period_days: int) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate future gain.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV
        period_days: Number of trading days for the future gain period

    Returns:
        List of future gain values (None where calculation not possible)
    """
    n_columns = len(price_strings)

    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            break
        prices.append(price)

    if len(prices) <= period_days:
        # Insufficient data
        return [None] * n_columns

    # Calculate future gain for valid prices
    gain_values = calculate_future_gain(prices, period_days)

    # Pad with None for the empty values we didn't process
    remaining = n_columns - len(prices)
    gain_values.extend([None] * remaining)

    return gain_values


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Future Gain {PERIOD_DAYS}-day calculation")

    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        print(f"1. Reading input file: {INPUT_FILE.name}")
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rows = list(reader)

        print(f"2. Loaded {len(rows)} tickers with {len(header)-1} daynum columns")

        print(f"3. Calculating {PERIOD_DAYS}-day future gains...")

        output_rows = []
        tickers_processed = 0
        tickers_skipped = 0

        for row in rows:
            ticker = row[0]
            price_strings = row[1:]

            gain_values = process_ticker_row(ticker, price_strings, PERIOD_DAYS)

            gain_strings = [format_european_decimal(val) for val in gain_values]
            output_row = [ticker] + gain_strings
            output_rows.append(output_row)

            if any(val is not None for val in gain_values):
                tickers_processed += 1
            else:
                tickers_skipped += 1

        print(f"4. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(output_rows)

        print(f"SUCCESS: {tickers_processed} tickers processed, {tickers_skipped} skipped")
        print(f"Note: First {PERIOD_DAYS} columns are empty (no future data)")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
