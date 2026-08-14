"""
1-Month Beta Module

Calculates beta (market sensitivity) over a 1-month period (23 trading days).

Beta = Cov(stock_returns, index_returns) / Var(index_returns)

Where:
- stock_returns = daily returns of the stock over 23 days
- index_returns = daily returns of the stock's core index over the same 23 days
- Core index is looked up from Stamdata.csv (Index column)

Beta > 1: Stock moves more than the index (higher risk/reward)
Beta < 1: Stock moves less than the index (lower risk/reward)
Beta < 0: Stock moves opposite to the index

Reads PotDat.csv and Stamdata.csv, outputs longi_beta1m.csv.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Dict

# Configuration
INPUT_DIR = Path(__file__).parent.parent / "input"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"
STAMDATA_FILE = INPUT_DIR / "Stamdata.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_beta1m.csv"
WINDOW_SIZE = 23  # 1 month = 1 × 22 + 1 trading days


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


def main() -> int:
    print(f"1-month beta calculation (Cov/Var over {WINDOW_SIZE} days)")

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

    # Calculate beta for each ticker
    print(f"4. Calculating 1-month beta for {len(rows)} tickers...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output_rows = []
    tickers_processed = 0
    tickers_no_index = 0
    tickers_skipped = 0

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
                    # Need WINDOW_SIZE daily returns = WINDOW_SIZE+1 prices
                    if i + WINDOW_SIZE + 1 > len(stock_prices) or i + WINDOW_SIZE + 1 > len(index_prices):
                        beta_values.append(None)
                        continue

                    stock_window = stock_prices[i:i + WINDOW_SIZE + 1]
                    index_window = index_prices[i:i + WINDOW_SIZE + 1]

                    stock_rets = calculate_daily_returns(stock_window, WINDOW_SIZE)
                    index_rets = calculate_daily_returns(index_window, WINDOW_SIZE)

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

    # Write output
    print(f"5. Writing {OUTPUT_FILE.name}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(header)
        writer.writerows(output_rows)

    print(f"SUCCESS: {tickers_processed} tickers with beta, {tickers_no_index} without index mapping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
