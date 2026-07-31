"""
Performance Calculation Module

Calculates percentage gain/loss over various time periods.
Reads PotDat.csv and outputs 7 separate CSV files with performance metrics.

Time periods — the "seven-pack": literal trading-day counts, filename always
longi_per{N}d.csv for N days. Replaced the old semantic ladder (1d/1w/1m/3m/6m/1y ≈
1/5/22/66/132/264 days) 2026-07-31 because the semantic labels were unpopular and, for four
of the six, only approximated a round day count anyway:
- 1 day
- 5 days
- 10 days
- 20 days
- 50 days
- 100 days
- 200 days

Performance is calculated as: ((current_price - past_price) / past_price) * 100
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Time period definitions (in trading days)
@dataclass
class TimePeriod:
    """Definition of a time period for performance calculation."""
    name: str          # Display name
    days: int          # Number of trading days
    output_file: str   # Output CSV filename

PERIODS = [
    TimePeriod("1 day", 1, "longi_per1d.csv"),
    TimePeriod("5 days", 5, "longi_per5d.csv"),
    TimePeriod("10 days", 10, "longi_per10d.csv"),
    TimePeriod("20 days", 20, "longi_per20d.csv"),
    TimePeriod("50 days", 50, "longi_per50d.csv"),
    TimePeriod("100 days", 100, "longi_per100d.csv"),
    TimePeriod("200 days", 200, "longi_per200d.csv"),
]


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


def calculate_performance(prices: List[float], period_days: int) -> List[Optional[float]]:
    """
    Calculate percentage performance for a given time period.

    Array layout: [0]=newest (e.g., 2015), [n-1]=oldest (e.g., 1543)
    To calculate performance at index i, we compare with index i+period_days (older price).

    Performance formula: ((current - past) / past) * 100

    Args:
        prices: List of prices from newest to oldest
        period_days: Number of trading days to look back

    Returns:
        List of performance percentages (None where calculation not possible)
    """
    n = len(prices)
    performance = [None] * n

    # Calculate performance for each position where we have enough historical data
    for i in range(n - period_days):
        current_price = prices[i]
        past_price = prices[i + period_days]

        # Calculate percentage change
        if past_price != 0:  # Avoid division by zero
            perf = ((current_price - past_price) / past_price) * 100
            performance[i] = perf
        # else: leave as None (can't calculate if past_price is 0)

    # Remaining positions (last period_days entries) stay as None - insufficient historical data
    return performance


def process_ticker_row(ticker: str, price_strings: List[str], period_days: int) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate performance.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV
        period_days: Number of trading days for the performance period

    Returns:
        List of performance values (None where calculation not possible)
    """
    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) <= period_days:
        # Insufficient data - need at least period_days + 1 prices
        return [None] * len(price_strings)

    # Calculate performance for valid prices
    perf_values = calculate_performance(prices, period_days)

    # Pad with None for the empty values we didn't process
    remaining = len(price_strings) - len(prices)
    perf_values.extend([None] * remaining)

    return perf_values


def process_period(period: TimePeriod, header: List[str], rows: List[List[str]]) -> Tuple[int, int]:
    """
    Process one time period and generate its output file.

    Args:
        period: TimePeriod definition
        header: CSV header row
        rows: All ticker data rows

    Returns:
        Tuple of (tickers_processed, tickers_skipped)
    """
    output_file = OUTPUT_DIR / period.output_file

    print(f"\n--- Processing {period.name} ({period.days} days) ---")

    output_rows = []
    tickers_processed = 0
    tickers_skipped = 0

    for row in rows:
        ticker = row[0]
        price_strings = row[1:]

        # Calculate performance
        perf_values = process_ticker_row(ticker, price_strings, period.days)

        # Format output row
        perf_strings = [format_european_decimal(val) for val in perf_values]
        output_row = [ticker] + perf_strings
        output_rows.append(output_row)

        # Count processing stats
        if any(val is not None for val in perf_values):
            tickers_processed += 1
        else:
            tickers_skipped += 1

    # Write output CSV
    print(f"Writing output file: {period.output_file}")
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(header)  # Same header as input
        writer.writerows(output_rows)

    print(f"✓ {period.name}: {tickers_processed} tickers processed, {tickers_skipped} skipped")

    return tickers_processed, tickers_skipped


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Performance calculation for multiple periods")

    # Check input file exists
    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return 1

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Read input CSV
        print(f"1. Reading input file: {INPUT_FILE.name}")
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rows = list(reader)

        print(f"2. Loaded {len(rows)} tickers with {len(header)-1} daynum columns")

        # Process each time period
        print(f"3. Calculating performance for {len(PERIODS)} time periods...")

        total_processed = 0
        total_skipped = 0

        for period in PERIODS:
            processed, skipped = process_period(period, header, rows)
            total_processed += processed
            total_skipped += skipped

        # Summary
        print(f"\n=== SUMMARY ===")
        print(f"Generated {len(PERIODS)} output files:")
        for period in PERIODS:
            print(f"  - {period.output_file} ({period.name})")
        print(f"SUCCESS: All performance calculations completed")

        return 0

    except Exception as e:
        print(f"ERROR: Error during performance calculation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
