"""
Future Performance Calculation Module

Forward-looking twin of longi_performance.py. Calculates the percentage gain/loss
that WILL happen over the next N trading days and assigns it to the SIGNAL date
(the day the decision to buy is made), whereas longi_performance.py assigns a
trailing gain to the end date.

This is "foresight" data, used for backtesting: at daynum d it answers "what would
a position opened on the strength of day d's data have returned?".

THE SIGNAL DAY IS NOT TRADED. Day d's own close is what the decision is made on,
so it cannot also be the entry price — the entry is the NEXT trading day (d+1) and
the exit is period_days after that:

    gain[d] = (P[d+1+period_days] - P[d+1]) / P[d+1] * 100

This deliberately differs from the retired future_gain20d/50d.csv, which entered at
P[d] and so quietly assumed you could trade the very close you were reading.

Time periods — IDENTICAL day counts to longi_performance.py, deliberately (the "seven-pack",
literal trading-day counts, replacing the old semantic 1d/1w/1m/3m/6m/1y ladder 2026-07-31):
- 1 day
- 5 days
- 10 days
- 20 days
- 50 days
- 100 days
- 200 days

Array layout: [0]=newest (e.g., 2202), [n-1]=oldest (e.g., 1543)
Signal day d sits at index i, so entry is index i-1 and exit is index i-1-period_days.
The newest period_days+1 columns are therefore empty — that future has not happened yet.

Outputs longi_future_per{1d,5d,10d,20d,50d,100d,200d}.csv.

NOTE: these files carry the longi_ prefix but are NOT usable as per-ticker features.
longi_across.py skips them by the `longi_future_` prefix; putting a realized forward
gain into a cross-sectional snapshot would leak the answer into the features.

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
    """Definition of a time period for future performance calculation."""
    name: str          # Display name
    days: int          # Number of trading days held
    output_file: str   # Output CSV filename


PERIODS = [
    TimePeriod("1 day", 1, "longi_future_per1d.csv"),
    TimePeriod("5 days", 5, "longi_future_per5d.csv"),
    TimePeriod("10 days", 10, "longi_future_per10d.csv"),
    TimePeriod("20 days", 20, "longi_future_per20d.csv"),
    TimePeriod("50 days", 50, "longi_future_per50d.csv"),
    TimePeriod("100 days", 100, "longi_future_per100d.csv"),
    TimePeriod("200 days", 200, "longi_future_per200d.csv"),
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


def calculate_future_gain(prices: List[float], period_days: int) -> List[Optional[float]]:
    """
    Calculate future percentage gain for a given holding period.

    Array layout: [0]=newest, [n-1]=oldest. Signal day at index i is NOT traded:
    entry is the next trading day (index i-1), exit is period_days later
    (index i-1-period_days).

    Future gain formula: ((exit - entry) / entry) * 100

    Args:
        prices: List of prices from newest to oldest
        period_days: Number of trading days held

    Returns:
        List of future gain percentages (None where calculation not possible)
    """
    n = len(prices)
    future_gain: List[Optional[float]] = [None] * n

    # Needs i-1-period_days >= 0, so the newest period_days+1 positions stay empty:
    # their entry day, their exit day, or both have not happened yet.
    for i in range(period_days + 1, n):
        entry_price = prices[i - 1]
        exit_price = prices[i - 1 - period_days]

        if entry_price != 0:  # Avoid division by zero
            future_gain[i] = ((exit_price - entry_price) / entry_price) * 100
        # else: leave as None (can't compute a return off a zero entry)

    return future_gain


def process_ticker_row(ticker: str, price_strings: List[str], period_days: int) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate future gain.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV
        period_days: Number of trading days held

    Returns:
        List of future gain values (None where calculation not possible)
    """
    n_columns = len(price_strings)

    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) <= period_days + 1:
        # Insufficient data - the oldest signal day needs an entry day plus
        # period_days of holding after it
        return [None] * n_columns

    # Calculate future gain for valid prices
    gain_values = calculate_future_gain(prices, period_days)

    # Pad with None for the empty values we didn't process
    remaining = n_columns - len(prices)
    gain_values.extend([None] * remaining)

    return gain_values


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

    print(f"\nProcessing future {period.name} ({period.days} days held, entry at signal+1)")

    output_rows = []
    tickers_processed = 0
    tickers_skipped = 0

    for row in rows:
        ticker = row[0]
        price_strings = row[1:]

        # Calculate future gain
        gain_values = process_ticker_row(ticker, price_strings, period.days)

        # Format output row
        gain_strings = [format_european_decimal(val) for val in gain_values]
        output_row = [ticker] + gain_strings
        output_rows.append(output_row)

        # Count processing stats
        if any(val is not None for val in gain_values):
            tickers_processed += 1
        else:
            tickers_skipped += 1

    # Write output CSV
    print(f"Writing output file: {period.output_file}")
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(header)  # Same header as input
        writer.writerows(output_rows)

    print(f"✓ {period.output_file}: {tickers_processed} tickers processed, "
          f"{tickers_skipped} skipped, newest {period.days + 1} columns empty")

    return tickers_processed, tickers_skipped


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Future performance calculation for multiple periods")

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
        print(f"3. Calculating future performance for {len(PERIODS)} time periods...")

        total_processed = 0
        total_skipped = 0

        for period in PERIODS:
            processed, skipped = process_period(period, header, rows)
            total_processed += processed
            total_skipped += skipped

        # Summary
        print(f"\nGenerated {len(PERIODS)} output files:")
        for period in PERIODS:
            print(f"  - {period.output_file} ({period.name}, {period.days} days)")
        print(f"SUCCESS: All future performance calculations completed")

        return 0

    except Exception as e:
        print(f"ERROR: Error during future performance calculation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
