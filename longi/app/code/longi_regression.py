"""
Log-Price Regression Module — trend growth rate and fit quality

Builds two families of tables, one pair per rolling window, by fitting an OLS
regression line to log(price) against time (days):

    log P(t) = log P0 + t * log(1+r)

so the fitted slope is log(1+r), r being the ticker's implied constant growth
rate over that window. Unlike longi_per*.csv (which is exact but reads only
the two endpoints), the regression uses every price in the window, so a
single noisy close moves it far less and a one-off jump reads differently
from a steady climb to the same place.

Window sizes: 20 / 50 / 100 / 200 trading days (the seven-pack long end).
Each fit is assigned to the window's NEWEST day — never the midpoint, which
would leak information from days after the assignment day into that column
(the same look-ahead hazard longi_across.py's longi_future_ skip-guard
exists to prevent).

Outputs, per window N:
- longi_regr{N}d.csv     annualized growth rate (%): (exp(slope * 265) - 1) * 100
                          265 = longi's trading year (see longi_sh1yr.py)
- longi_regrfit{N}d.csv  R^2 * 100 (0-100): how well "constant growth"
                          actually describes the ticker over that window —
                          a numeric cousin of longi_stepup*.csv

These are per-ticker features like longi_per*.csv, NOT a replacement for it:
per* is a realized endpoint return, regr* is a smoothed trend estimate, and
the two answer different questions. See longi/CLAUDE.md.

Reads PotDat.csv once, outputs 8 files (4 windows x {rate, fit}).
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

import numpy as np

# Configuration
INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

TRADING_DAYS_PER_YEAR = 265  # matches longi_sh1yr.py's window convention


@dataclass
class RegrPeriod:
    """Definition of a regression window."""
    name: str          # Display name
    window: int        # Trading days in the window (N)
    rate_file: str      # Output CSV filename: annualized growth rate
    fit_file: str        # Output CSV filename: R^2 x100


PERIODS = [
    RegrPeriod("20 days", 20, "longi_regr20d.csv", "longi_regrfit20d.csv"),
    RegrPeriod("50 days", 50, "longi_regr50d.csv", "longi_regrfit50d.csv"),
    RegrPeriod("100 days", 100, "longi_regr100d.csv", "longi_regrfit100d.csv"),
    RegrPeriod("200 days", 200, "longi_regr200d.csv", "longi_regrfit200d.csv"),
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


def format_european_decimal(value: Optional[float], decimals: int = 2) -> str:
    """Format float to European decimal format (comma as decimal separator)."""
    if value is None:
        return ""
    return f"{value:.{decimals}f}".replace('.', ',')


def parse_ticker_prices(price_strings: List[str]) -> List[float]:
    """
    Parse a ticker's price row, stopping at the first empty cell.

    Array layout: [0]=newest, [n-1]=oldest. Empty cells only occur as a
    contiguous tail toward the oldest end (see CLAUDE.md), so the first
    empty value marks the end of this ticker's history.
    """
    prices: List[float] = []
    for price_str in price_strings:
        price = parse_european_decimal(price_str)
        if price is None:
            break
        prices.append(price)
    return prices


def calculate_regression(
    prices: List[float], period: RegrPeriod
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """
    OLS-regress log(price) on time over every rolling window of length
    period.window, assigning each fit to the window's newest day.

    For the window covering prices[i : i+N] (k=0..N-1, k=0 newest):
        y_k   = ln(price[i+k])
        u_k   = (N-1)/2 - k                     centred time, sum(u_k) == 0
        SU2   = N*(N**2-1)/12                   == sum(u_k**2), constant per N
        slope = sum(u_k*y_k) / SU2               log-price units per day
        rate  = (exp(slope * 265) - 1) * 100     <- longi_regr{N}d.csv
        R^2   = sum(u_k*y_k)**2 / (SU2 * Syy)    <- longi_regrfit{N}d.csv (x100)

    Vectorized with a sliding-window view rather than a Python loop: at
    ~3000 tickers x ~470 columns x up to 200-wide windows, a pure-Python
    nested loop would run past the pipeline's 600s module timeout.

    Returns (rate_values, fit_values), each aligned to `prices` (same
    length, newest-first). None where the window lacks N full, valid (>0)
    prices, or (for fit only) where the window is perfectly flat (R^2 is a
    0/0 there, not a zero).
    """
    n_total = len(prices)
    rate_values: List[Optional[float]] = [None] * n_total
    fit_values: List[Optional[float]] = [None] * n_total

    N = period.window
    if n_total < N:
        return rate_values, fit_values

    price_arr = np.asarray(prices, dtype=float)
    y = np.full(n_total, np.nan)
    positive = price_arr > 0
    y[positive] = np.log(price_arr[positive])
    # Any non-positive price flows into every window that touches it as NaN,
    # which NaN-poisons that window's sums below -> blank output, matching
    # the ">0" guards used throughout the rest of the longi_* family.

    u = (N - 1) / 2.0 - np.arange(N, dtype=float)  # k=0 (newest) has largest u
    su2 = N * (N ** 2 - 1) / 12.0  # == sum(u_k**2), constant for this window size

    windows = np.lib.stride_tricks.sliding_window_view(y, N)  # (n_total-N+1, N)
    with np.errstate(invalid='ignore'):
        sw = windows @ u
        s1 = windows.sum(axis=1)
        s2 = (windows * windows).sum(axis=1)

    slope = sw / su2
    with np.errstate(over='ignore', invalid='ignore'):
        rate = (np.exp(slope * TRADING_DAYS_PER_YEAR) - 1.0) * 100.0

    sstot = s2 - (s1 ** 2) / N  # == Syy, the total sum of squares
    flat = sstot <= 0
    with np.errstate(divide='ignore', invalid='ignore'):
        r2 = np.where(flat, np.nan, (sw ** 2) / (su2 * sstot))
    fit = r2 * 100.0

    # windows[i] covers prices[i : i+N]; assign the fit to column i, the
    # window's newest day (never the midpoint - see module docstring).
    for i in range(len(sw)):
        r = rate[i]
        if np.isfinite(r):
            rate_values[i] = float(r)
        f = fit[i]
        if np.isfinite(f):
            fit_values[i] = float(min(100.0, max(0.0, f)))  # clamp float rounding only

    return rate_values, fit_values


def process_period(period: RegrPeriod, header: List[str], rows: List[List[str]]) -> Tuple[int, int]:
    """Process one regression window and write its rate + fit output files."""
    rate_path = OUTPUT_DIR / period.rate_file
    fit_path = OUTPUT_DIR / period.fit_file

    print(f"\nProcessing regression {period.name} (window {period.window} days)")

    rate_rows = []
    fit_rows = []
    tickers_with_data = 0

    for row in rows:
        ticker = row[0].strip()
        price_strings = row[1:]

        prices = parse_ticker_prices(price_strings)
        rate_values, fit_values = calculate_regression(prices, period)

        # Pad back out to the full row length (prices stopped at the first
        # empty cell; that unprocessed tail is blank too).
        remaining = len(price_strings) - len(prices)
        rate_values = rate_values + [None] * remaining
        fit_values = fit_values + [None] * remaining

        if any(v is not None for v in rate_values):
            tickers_with_data += 1

        rate_rows.append([ticker] + [format_european_decimal(v) for v in rate_values])
        fit_rows.append([ticker] + [format_european_decimal(v) for v in fit_values])

    print(f"Writing output files: {period.rate_file}, {period.fit_file}")
    for path, output_rows in ((rate_path, rate_rows), (fit_path, fit_rows)):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(output_rows)

    tickers_skipped = len(rows) - tickers_with_data
    print(f"SUCCESS: {period.name}: {tickers_with_data} tickers with data, {tickers_skipped} skipped")

    return tickers_with_data, tickers_skipped


def main() -> int:
    print(f"Log-price regression for {len(PERIODS)} window(s)")

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

        print(f"2. Loaded {len(rows)} tickers with {len(header) - 1} daynum columns")

        print(f"3. Calculating regression for {len(PERIODS)} window(s)...")
        for period in PERIODS:
            process_period(period, header, rows)

        print(f"\nGenerated {len(PERIODS) * 2} output files:")
        for period in PERIODS:
            print(f"  - {period.rate_file}, {period.fit_file} ({period.name})")
        print(f"SUCCESS: All regression calculations completed")

        return 0

    except Exception as e:
        print(f"ERROR: Error during regression calculation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
