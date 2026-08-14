"""
Beta (Market Sensitivity) Module

Builds every longi_beta{N}.csv table: beta of each ticker against its own CoreIndex
(from Stamdata.csv), over five trailing windows.

Beta = Cov(stock_returns, index_returns) / Var(index_returns)

Beta > 1: Stock moves more than the index (higher risk/reward)
Beta < 1: Stock moves less than the index (lower risk/reward)
Beta < 0: Stock moves opposite to the index

Window sizes follow the same months x 22 + 1 trading-day rule as the rest of the
system's month-based windows (e.g. sh3m/sh6m/sh1yr): 1m=23, 2m=45, 3m=67, 6m=133, 1yr=265.

Consolidated 2026-08-14 from five near-identical one-window scripts (longi_beta1m.py,
longi_beta2m.py, longi_beta3m.py, longi_beta6m.py, longi_beta1yr.py, moved to
_not_used/), mirroring how longi_future_performance.py loops PERIODS internally rather
than being one script per window.

Reads PotDat.csv and Stamdata.csv once, outputs longi_beta{1m,2m,3m,6m,1yr}.csv.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

# Configuration
INPUT_DIR = Path(__file__).parent.parent / "input"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"
STAMDATA_FILE = INPUT_DIR / "Stamdata.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


@dataclass
class BetaPeriod:
    """Definition of a beta window."""
    name: str          # Display name
    window: int        # Trading days in the window
    output_file: str   # Output CSV filename


PERIODS = [
    BetaPeriod("1 month", 23, "longi_beta1m.csv"),
    BetaPeriod("2 months", 45, "longi_beta2m.csv"),
    BetaPeriod("3 months", 67, "longi_beta3m.csv"),
    BetaPeriod("6 months", 133, "longi_beta6m.csv"),
    BetaPeriod("1 year", 265, "longi_beta1yr.csv"),
]


def parse_european_decimal(value: str) -> Optional[float]:
    """Parse European decimal format (comma as decimal separator)."""
    value = value.strip()
    if not value:
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def format_european_decimal(value: Optional[float], decimals: int = 4) -> str:
    """Format float to European decimal format (comma as decimal separator)."""
    if value is None:
        return ""
    return f"{value:.{decimals}f}".replace('.', ',')


def load_ticker_to_index() -> Dict[str, str]:
    """Load ticker→CoreIndex mapping from Stamdata.csv (Index at column 23)."""
    ticker_to_index: Dict[str, str] = {}
    try:
        with open(STAMDATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip header
            for row in reader:
                if len(row) > 23:
                    ticker = row[0].strip()
                    index_ticker = row[23].strip()
                    if ticker and index_ticker:
                        ticker_to_index[ticker] = index_ticker
    except Exception as e:
        print(f"ERROR: Failed to load Stamdata.csv: {e}")
    return ticker_to_index


def calculate_daily_returns(prices: List[float], count: int) -> Optional[List[float]]:
    """
    Calculate daily returns for the first 'count' days.

    Array layout: [0]=newest, [n-1]=oldest.
    Daily return[j] = (price[j] - price[j+1]) / price[j+1] * 100

    Returns None if any price is invalid.
    """
    if len(prices) < count + 1:
        return None
    returns = []
    for j in range(count):
        older = prices[j + 1]
        newer = prices[j]
        if older <= 0:
            return None
        returns.append(((newer - older) / older) * 100)
    return returns


def calculate_beta(stock_returns: List[float], index_returns: List[float]) -> Optional[float]:
    """
    Calculate beta = Cov(stock, index) / Var(index).

    Both lists must be the same length.
    """
    n = len(stock_returns)
    if n == 0 or n != len(index_returns):
        return None

    mean_s = sum(stock_returns) / n
    mean_i = sum(index_returns) / n

    cov = sum((stock_returns[j] - mean_s) * (index_returns[j] - mean_i) for j in range(n)) / n
    var_i = sum((index_returns[j] - mean_i) ** 2 for j in range(n)) / n

    if var_i <= 0:
        return None

    return cov / var_i


def process_period(
    period: BetaPeriod,
    header: List[str],
    rows: List[List[str]],
    ticker_to_index: Dict[str, str],
    ticker_prices: Dict[str, List[Optional[float]]],
) -> Tuple[int, int]:
    """Process one beta window and generate its output file."""
    output_file = OUTPUT_DIR / period.output_file

    print(f"\nProcessing beta {period.name} (window {period.window} days)")

    output_rows = []
    tickers_processed = 0
    tickers_no_index = 0

    for row in rows:
        ticker = row[0].strip()
        stock_price_strs = row[1:]

        # Parse stock prices (stop at first empty = stock didn't exist)
        stock_prices: List[float] = []
        for val in stock_price_strs:
            p = parse_european_decimal(val)
            if p is None:
                break
            stock_prices.append(p)

        # Get the core index for this ticker
        index_ticker = ticker_to_index.get(ticker)

        # Index tickers (^XXX) don't have their own beta
        if not index_ticker or ticker.startswith('^'):
            beta_values = [None] * len(stock_price_strs)
            if not index_ticker and not ticker.startswith('^'):
                tickers_no_index += 1
        else:
            # Get index prices
            index_prices_raw = ticker_prices.get(index_ticker)
            if index_prices_raw is None:
                beta_values = [None] * len(stock_price_strs)
                tickers_no_index += 1
            else:
                # Parse index prices (stop at first None)
                index_prices: List[float] = []
                for p in index_prices_raw:
                    if p is None:
                        break
                    index_prices.append(p)

                # Calculate beta for each day
                beta_values = []
                for i in range(len(stock_price_strs)):
                    # Need window daily returns = window+1 prices
                    if i + period.window + 1 > len(stock_prices) or i + period.window + 1 > len(index_prices):
                        beta_values.append(None)
                        continue

                    stock_window = stock_prices[i:i + period.window + 1]
                    index_window = index_prices[i:i + period.window + 1]

                    stock_rets = calculate_daily_returns(stock_window, period.window)
                    index_rets = calculate_daily_returns(index_window, period.window)

                    if stock_rets is not None and index_rets is not None:
                        beta_values.append(calculate_beta(stock_rets, index_rets))
                        tickers_processed += 1 if i == 0 else 0
                    else:
                        beta_values.append(None)

                # Pad remaining columns with None
                while len(beta_values) < len(stock_price_strs):
                    beta_values.append(None)

        output_row = [ticker] + [format_european_decimal(v) for v in beta_values]
        output_rows.append(output_row)

    print(f"Writing output file: {period.output_file}")
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(header)
        writer.writerows(output_rows)

    print(f"SUCCESS: {period.output_file}: {tickers_processed} tickers with beta, "
          f"{tickers_no_index} without index mapping")

    return tickers_processed, tickers_no_index


def main() -> int:
    print(f"Beta calculation for {len(PERIODS)} window(s)")

    if not POTDAT_FILE.exists():
        print(f"ERROR: Input file not found: {POTDAT_FILE}")
        return 1

    # Load ticker→index mapping
    print(f"1. Loading CoreIndex mappings from Stamdata.csv")
    ticker_to_index = load_ticker_to_index()
    print(f"   {len(ticker_to_index)} tickers mapped to indices")

    # Read PotDat.csv: header + all rows
    print(f"2. Reading {POTDAT_FILE.name}")
    try:
        with open(POTDAT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rows = list(reader)
    except Exception as e:
        print(f"ERROR: Failed to read PotDat.csv: {e}")
        return 1

    num_daynums = len(header) - 1
    print(f"   {len(rows)} tickers, {num_daynums} daynum columns")

    # Build price lookup: ticker → list of parsed prices
    print(f"3. Parsing prices for all tickers")
    ticker_prices: Dict[str, List[Optional[float]]] = {}
    for row in rows:
        ticker = row[0].strip()
        prices: List[Optional[float]] = []
        for val in row[1:]:
            prices.append(parse_european_decimal(val))
        ticker_prices[ticker] = prices

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"4. Calculating beta for {len(rows)} tickers x {len(PERIODS)} window(s)...")
    for period in PERIODS:
        process_period(period, header, rows, ticker_to_index, ticker_prices)

    print(f"\nGenerated {len(PERIODS)} output files:")
    for period in PERIODS:
        print(f"  - {period.output_file} ({period.name}, {period.window} days)")
    print(f"SUCCESS: All beta calculations completed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
