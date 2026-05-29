"""
MACD Calculation Module

Calculates MACD (Moving Average Convergence Divergence) indicator with three components:
- MACD Line = EMA(4) - EMA(15)
- Signal Line = EMA(9) of MACD Line
- MACD Histogram = MACD Line - Signal Line

All values are normalized per ticker to [-100, +100] range using max(abs(values)).
This ensures at least one value in each row equals -100 or +100.

Reads PotDat.csv and outputs three files with identical structure:
- longi_macd_line.csv
- longi_macd_signal.csv
- longi_macd_histogram.csv

Output goes to stdout - start_longi.sh handles logging redirection.

Note: Uses exponential moving average (EMA), not simple moving average (SMA).
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_macd.csv"

# MACD Parameters
MACD_FAST = 4   # Fast EMA period
MACD_SLOW = 15  # Slow EMA period
MACD_SIGNAL = 9 # Signal line EMA period

# EMA smoothing factors
ALPHA_FAST = 2.0 / (MACD_FAST + 1)    # 0.4
ALPHA_SLOW = 2.0 / (MACD_SLOW + 1)    # 0.125
ALPHA_SIGNAL = 2.0 / (MACD_SIGNAL + 1) # 0.2


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


def format_european_decimal(value: Optional[float], decimals: int = 4) -> str:
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


def calculate_ema(prices: List[float], period: int, alpha: float) -> List[Optional[float]]:
    """
    Calculate Exponential Moving Average.

    EMA formula: EMA[t] = alpha × Price[t] + (1 - alpha) × EMA[t-1]
    where alpha = 2 / (period + 1)

    Array layout: [0]=newest (e.g., daynum 2009), [n-1]=oldest (e.g., daynum 1543)
    EMA calculation proceeds from oldest to newest (right to left in CSV).

    Args:
        prices: List of prices from newest to oldest
        period: EMA period
        alpha: Smoothing factor (2 / (period + 1))

    Returns:
        List of EMA values (same length as prices, None where calculation not possible)
    """
    n = len(prices)
    if n < period:
        return [None] * n

    ema_values = [None] * n

    # Reverse to work oldest→newest
    prices_reversed = prices[::-1]  # [0]=oldest, [n-1]=newest
    ema_reversed = [None] * n

    # Initialize first EMA as simple average of first 'period' prices
    ema_reversed[period - 1] = sum(prices_reversed[:period]) / period

    # Calculate subsequent EMA values using exponential smoothing
    for i in range(period, n):
        ema_reversed[i] = alpha * prices_reversed[i] + (1 - alpha) * ema_reversed[i - 1]

    # Reverse back to match original order (newest→oldest)
    ema_values = ema_reversed[::-1]

    return ema_values


def calculate_macd(prices: List[float]) -> tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    Calculate MACD components: MACD Line, Signal Line, and Histogram.

    MACD Line = EMA(fast) - EMA(slow)
    Signal Line = EMA(signal_period) of MACD Line
    Histogram = MACD Line - Signal Line

    Args:
        prices: List of prices from newest to oldest

    Returns:
        Tuple of (macd_line, signal_line, histogram) lists
    """
    n = len(prices)

    # Need enough data for slow EMA
    if n < MACD_SLOW:
        return ([None] * n, [None] * n, [None] * n)

    # Calculate fast and slow EMAs
    ema_fast = calculate_ema(prices, MACD_FAST, ALPHA_FAST)
    ema_slow = calculate_ema(prices, MACD_SLOW, ALPHA_SLOW)

    # Calculate MACD Line = EMA(fast) - EMA(slow)
    macd_line = []
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line.append(ema_fast[i] - ema_slow[i])
        else:
            macd_line.append(None)

    # Calculate Signal Line = EMA(signal_period) of MACD Line
    # Extract valid MACD values for signal calculation
    valid_macd = [val for val in macd_line if val is not None]

    if len(valid_macd) < MACD_SIGNAL:
        # Not enough MACD data for signal line
        return (macd_line, [None] * n, [None] * n)

    # Calculate signal line on valid MACD values
    signal_values = calculate_ema(valid_macd, MACD_SIGNAL, ALPHA_SIGNAL)

    # Map signal values back to full array
    signal_line = [None] * n
    valid_idx = 0
    for i in range(n):
        if macd_line[i] is not None:
            signal_line[i] = signal_values[valid_idx]
            valid_idx += 1

    # Calculate Histogram = MACD Line - Signal Line
    histogram = []
    for i in range(n):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram.append(macd_line[i] - signal_line[i])
        else:
            histogram.append(None)

    return (macd_line, signal_line, histogram)


def normalize_to_range(values: List[Optional[float]]) -> List[Optional[float]]:
    """
    Normalize values to [-100, 100] range based on maximum absolute value.

    Each ticker's values are normalized independently using:
    normalized_value = (value / max_abs_value) * 100

    This ensures values stay within [-100, 100] with at least one value being -100 or +100.

    Args:
        values: List of values to normalize

    Returns:
        List of normalized values (None values preserved)
    """
    # Extract non-None values
    valid_values = [v for v in values if v is not None]

    if not valid_values:
        return values

    # Find maximum absolute value
    max_abs = max(abs(v) for v in valid_values)

    if max_abs == 0:
        # All values are zero - return as is
        return values

    # Normalize to [-100, 100]
    normalized = []
    for v in values:
        if v is None:
            normalized.append(None)
        else:
            normalized.append((v / max_abs) * 100.0)

    return normalized


def process_ticker_row(ticker: str, price_strings: List[str]) -> tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    Process a single ticker row: parse prices and calculate MACD.

    Args:
        ticker: Ticker symbol
        price_strings: List of price strings from CSV

    Returns:
        Tuple of (macd_line, signal_line, histogram) lists (normalized to [-100, 100])
    """
    # Parse prices, stopping at first empty value
    prices = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            # Hit empty value - stock didn't exist for older periods
            break
        prices.append(price)

    if len(prices) < MACD_SLOW:
        # Insufficient data - return all None values matching input length
        empty = [None] * len(price_strings)
        return (empty, empty, empty)

    # Calculate MACD components
    macd_line, signal_line, histogram = calculate_macd(prices)

    # Normalize each component independently to [-100, 100] range
    macd_line = normalize_to_range(macd_line)
    signal_line = normalize_to_range(signal_line)
    histogram = normalize_to_range(histogram)

    # Pad with None for the empty values we didn't process
    remaining = len(price_strings) - len(prices)
    macd_line.extend([None] * remaining)
    signal_line.extend([None] * remaining)
    histogram.extend([None] * remaining)

    return (macd_line, signal_line, histogram)


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"MACD calculation (EMA-based), parameters: Fast={MACD_FAST}, Slow={MACD_SLOW}, Signal={MACD_SIGNAL}")

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

        # Process each ticker - we'll create three separate output files
        macd_output_rows = []
        signal_output_rows = []
        histogram_output_rows = []
        tickers_processed = 0
        tickers_skipped = 0

        print(f"3. Calculating MACD for {len(rows)} tickers...")
        for row in rows:
            ticker = row[0]
            price_strings = row[1:]

            # Calculate MACD components
            macd_line, signal_line, histogram = process_ticker_row(ticker, price_strings)

            # Format output rows
            macd_strings = [format_european_decimal(val) for val in macd_line]
            signal_strings = [format_european_decimal(val) for val in signal_line]
            histogram_strings = [format_european_decimal(val) for val in histogram]

            macd_output_rows.append([ticker] + macd_strings)
            signal_output_rows.append([ticker] + signal_strings)
            histogram_output_rows.append([ticker] + histogram_strings)

            # Count processing stats
            if any(val is not None for val in macd_line):
                tickers_processed += 1
            else:
                tickers_skipped += 1

        # Write MACD Line output
        macd_file = OUTPUT_FILE.parent / "longi_macd_line.csv"
        print(f"4a. Writing MACD Line: {macd_file.name}")
        with open(macd_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(macd_output_rows)

        # Write Signal Line output
        signal_file = OUTPUT_FILE.parent / "longi_macd_signal.csv"
        print(f"4b. Writing Signal Line: {signal_file.name}")
        with open(signal_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(signal_output_rows)

        # Write Histogram output
        histogram_file = OUTPUT_FILE.parent / "longi_macd_histogram.csv"
        print(f"4c. Writing Histogram: {histogram_file.name}")
        with open(histogram_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(histogram_output_rows)

        print(f"SUCCESS: {tickers_processed} tickers processed, {tickers_skipped} skipped (insufficient data)")
        print(f"Output: 3 files (line, signal, histogram) - all normalized to [-100, +100] per ticker")

        return 0

    except Exception as e:
        print(f"ERROR: Error during MACD calculation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
