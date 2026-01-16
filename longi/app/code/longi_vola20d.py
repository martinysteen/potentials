"""
20-day Volatility Module (Returns-based)

Calculates volatility as standard deviation of daily returns over a 20-day rolling window.
Returns are calculated as percentage changes: (price[t] - price[t-1]) / price[t-1] * 100

Volatility = stdev(daily_returns_over_20_days)

Output is in percentage points (e.g., 2.5 means 2.5% daily volatility).

Reads PotDat.csv and outputs longi_vola20d.csv with identical structure.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional
import math

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_vola20d.csv"
WINDOW_SIZE = 20


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


def calculate_vola_20d(prices: List[float]) -> List[Optional[float]]:
    """
    Calculate 20-day volatility as standard deviation of daily returns.

    Array layout: [0]=newest (2009), [n-1]=oldest (1543)
    For day at index i, we need prices at indices [i:i+20] to calculate 20 returns
    (20 prices give 19 returns, but we include price[i+20] to get 20 returns)

    Daily return calculation (percentage):
    return[i] = (price[i] - price[i+1]) / price[i+1] * 100
    (newer price - older price) / older price

    Args:
        prices: List of prices from newest to oldest (left to right in CSV)

    Returns:
        List of volatility values (same length as prices, None where calculation not possible)
    """
    n = len(prices)
    if n < WINDOW_SIZE + 1:  # Need 21 prices to calculate 20 returns
        return [None] * n

    vola_values = []

    for i in range(n):
        # Need 21 prices to calculate 20 returns
        window_end = min(i + WINDOW_SIZE + 1, n)
        window = prices[i:window_end]

        # Need full window (21 prices for 20 returns)
        if len(window) < WINDOW_SIZE + 1:
            vola_values.append(None)
            continue

        # Calculate 20 daily returns
        returns = []
        for j in range(WINDOW_SIZE):
            older_price = window[j + 1]
            newer_price = window[j]
            if older_price > 0:
                daily_return = ((newer_price - older_price) / older_price) * 100
                returns.append(daily_return)
            else:
                # Invalid price, cannot calculate volatility
                vola_values.append(None)
                break
        else:
            # All returns calculated successfully
            # Calculate standard deviation
            if len(returns) == WINDOW_SIZE:
                mean_return = sum(returns) / len(returns)
                variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                volatility = math.sqrt(variance)
                vola_values.append(volatility)
            else:
                vola_values.append(None)

    return vola_values


def process_ticker_row(ticker: str, price_strings: List[str]) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate 20-day volatility.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV

    Returns:
        List of volatility values (None where calculation not possible)
    """
    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) < WINDOW_SIZE + 1:
        # Insufficient data - return all None values matching input length
        return [None] * len(price_strings)

    # Calculate volatility for valid prices
    vola_values = calculate_vola_20d(prices)

    # Pad with None for the empty values we didn't process
    remaining = len(price_strings) - len(prices)
    vola_values.extend([None] * remaining)

    return vola_values


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"=== longi_vola20d.py START: 20-day volatility calculation (returns-based) ===")

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

        print(f"3. Calculating 20-day volatility for {len(rows)} tickers...")
        for row in rows:
            ticker = row[0]
            price_strings = row[1:]

            # Calculate volatility
            vola_values = process_ticker_row(ticker, price_strings)

            # Format output row
            vola_strings = [format_european_decimal(val) for val in vola_values]
            output_row = [ticker] + vola_strings
            output_rows.append(output_row)

            # Count processing stats
            if any(val is not None for val in vola_values):
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
        print(f"ERROR: Error during volatility calculation: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
