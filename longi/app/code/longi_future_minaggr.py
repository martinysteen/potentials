"""
Future Minimum-Aggregated-Gain Module (worst drawdown ahead)

Forward-looking companion to longi_future_performance.py. Where longi_future_per{N}d.csv
answers "what will this position be worth at the END of the hold?", this module answers
"how far under water will it go BEFORE then?".

At signal daynum d it reports the LOWEST aggregated (compounded) gain reached at any point
during the hold — a drawdown, but kept in normal gain sign convention, so it is <= 0. If the
position is never under its entry price at any point in the window, the value is 0,00 (the
starting value of the aggregation).

THE SIGNAL DAY IS NOT TRADED — identical convention to longi_future_performance.py. Day d's
own close is what the decision is made on, so the entry is the NEXT trading day (d+1) and the
path examined runs to period_days after that:

    minaggr[d] = min( 0, min over k=1..period_days of (P[d+1+k] - P[d+1]) / P[d+1] * 100 )

Note there is no day-by-day compounding to do: measured against a FIXED entry price, the
cumulative (compounded) gain at day k is just the price ratio, so the running minimum of the
aggregated gain is the running minimum of the price. The implementation takes min() over the
price window directly, which is the same number and O(1) parsing per day.

This is drawdown FROM ENTRY, not peak-to-trough. A position that runs +40% and falls back to
+5% scores 0,00 here — it was never at a loss against the capital committed.

Because the whole path (entry through exit) must exist, this needs exactly the same data as
longi_future_per{N}d.csv and has exactly the same period_days+1 blank newest columns.

Periods — the two backtest horizons in use, NOT the full seven-pack:
- 20 days
- 50 days
Add a MinAggrPeriod entry below to extend (and mirror it in aux_qc_repo.BLANK_LEAD_COLS).

Array layout: [0]=newest (e.g., 2202), [n-1]=oldest (e.g., 1543)
Signal day d sits at index i, entry at index i-1, and the held path is indices i-2 down to
i-1-period_days (lower index = later in time).

Outputs longi_future_minaggr20d.csv, longi_future_minaggr50d.csv.

NOTE: these files carry the longi_ prefix but they are forward-looking, so longi_across.py
skips them by the `longi_future_` prefix. That guard is about the DAILY snapshot, which is
built at the newest daynum where these columns are blank by construction and where a value,
if one appeared, could only be foresight. It is not a claim that the data is untouchable: in a
BACKFILLED historical across_<daynum>.csv at daynum <= newest-(period+1) the window is fully
realized, and joining it in deliberately is legitimate — as the target being modelled, not as
a predictor alongside the features.

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


@dataclass
class MinAggrPeriod:
    """Definition of a holding period for minimum-aggregated-gain calculation."""
    name: str          # Display name
    days: int          # Number of trading days held
    output_file: str   # Output CSV filename


PERIODS = [
    MinAggrPeriod("20 days", 20, "longi_future_minaggr20d.csv"),
    MinAggrPeriod("50 days", 50, "longi_future_minaggr50d.csv"),
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


def calculate_future_minaggr(prices: List[float], period_days: int) -> List[Optional[float]]:
    """
    Calculate the lowest aggregated gain reached during the forward holding period.

    Array layout: [0]=newest, [n-1]=oldest. Signal day at index i is NOT traded:
    entry is the next trading day (index i-1) and the held path is the period_days
    prices after it, indices i-2 down to i-1-period_days.

    Since every point is measured against the same fixed entry price, the minimum
    aggregated gain is driven by the minimum price over that window:

        minaggr[i] = min(0, (min(window) - entry) / entry * 100)

    The min(0, ...) floor is the k=0 starting value: a position that is never below
    its entry price scores 0, not a positive number.

    Args:
        prices: List of prices from newest to oldest
        period_days: Number of trading days held

    Returns:
        List of minimum aggregated gain percentages, <= 0
        (None where calculation not possible)
    """
    n = len(prices)
    minaggr: List[Optional[float]] = [None] * n

    # Needs i-1-period_days >= 0, so the newest period_days+1 positions stay empty:
    # their entry day, part of their held path, or both have not happened yet.
    for i in range(period_days + 1, n):
        entry_price = prices[i - 1]

        if entry_price != 0:  # Avoid division by zero
            # Indices i-1-period_days .. i-2 — the period_days days held after entry
            worst_price = min(prices[i - 1 - period_days:i - 1])
            worst_gain = ((worst_price - entry_price) / entry_price) * 100
            minaggr[i] = min(0.0, worst_gain)
        # else: leave as None (can't compute a return off a zero entry)

    return minaggr


def process_ticker_row(ticker: str, price_strings: List[str], period_days: int) -> List[Optional[float]]:
    """
    Process a single ticker row: parse prices and calculate minimum aggregated gain.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV
        period_days: Number of trading days held

    Returns:
        List of minimum aggregated gain values (None where calculation not possible)
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

    # Calculate minimum aggregated gain for valid prices
    minaggr_values = calculate_future_minaggr(prices, period_days)

    # Pad with None for the empty values we didn't process
    remaining = n_columns - len(prices)
    minaggr_values.extend([None] * remaining)

    return minaggr_values


def process_period(period: MinAggrPeriod, header: List[str], rows: List[List[str]]) -> Tuple[int, int]:
    """
    Process one holding period and generate its output file.

    Args:
        period: MinAggrPeriod definition
        header: CSV header row
        rows: All ticker data rows

    Returns:
        Tuple of (tickers_processed, tickers_skipped)
    """
    output_file = OUTPUT_DIR / period.output_file

    print(f"\nProcessing future minaggr {period.name} ({period.days} days held, entry at signal+1)")

    output_rows = []
    tickers_processed = 0
    tickers_skipped = 0

    for row in rows:
        ticker = row[0]
        price_strings = row[1:]

        # Calculate minimum aggregated gain
        minaggr_values = process_ticker_row(ticker, price_strings, period.days)

        # Format output row
        minaggr_strings = [format_european_decimal(val) for val in minaggr_values]
        output_row = [ticker] + minaggr_strings
        output_rows.append(output_row)

        # Count processing stats
        if any(val is not None for val in minaggr_values):
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
    print(f"Future minimum aggregated gain (drawdown) calculation")

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

        # Process each holding period
        print(f"3. Calculating minimum aggregated gain for {len(PERIODS)} holding periods...")

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
        print(f"SUCCESS: All minimum aggregated gain calculations completed")

        return 0

    except Exception as e:
        print(f"ERROR: Error during minimum aggregated gain calculation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
