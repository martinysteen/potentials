"""
Uptrend Grading Module

Grades the strength of uptrend for each stock on each day based on BOTH:
- RSI values in the 5 preceding days
- MACD Histogram values in the 5 preceding days

CRUCIAL RULE: If ANY of the 5 preceding MACD histogram values is negative,
the uptrend grade is blank (empty). No histogram-negative day is allowed.

Reads longi_rsi.csv and longi_macd_histogram.csv, outputs longi_uptrend.csv.
Output goes to stdout - start_longi.sh handles logging redirection.

Grading criteria (evaluated ONLY if all 5 MACD histogram values >= 0):
1. VeryGood: average(5 preceding RSI values) >= 70
2. Good: minimum(5 preceding RSI values) > 50
3. Maybe: average(5 preceding RSI values) > 50
4. Empty: None of the above or insufficient data or any negative histogram
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Callable, Tuple, Dict
from statistics import mean

# Configuration
INPUT_RSI_FILE = Path(__file__).parent.parent / "output" / "longi_rsi.csv"
INPUT_MACD_HIST_FILE = Path(__file__).parent.parent / "output" / "longi_macd_histogram.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_uptrend.csv"
LOOKBACK_PERIOD = 5  # Number of preceding days to analyze


# Grade definitions: (name, test_function)
# test_function takes List[float] of RSI values and returns bool
# Evaluated in order - first match wins
GRADE_RULES: List[Tuple[str, Callable[[List[float]], bool]]] = [
    ("VeryGood", lambda rsi_list: mean(rsi_list) >= 70.0),
    ("Good", lambda rsi_list: min(rsi_list) > 50.0),
    ("Maybe", lambda rsi_list: mean(rsi_list) > 50.0),
    # Add more grades here - they will be evaluated in order
]


def parse_european_decimal(value: str) -> Optional[float]:
    """
    Parse European decimal format (comma as decimal separator).

    Args:
        value: String value to parse (e.g., "70,45")

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


def grade_uptrend(rsi_values: List[Optional[float]], macd_hist_values: List[Optional[float]], day_index: int) -> str:
    """
    Grade uptrend strength for a specific day based on 5 preceding RSI and MACD histogram values.

    CRUCIAL: If ANY of the 5 preceding MACD histogram values is negative, return empty grade.

    Array layout: [0]=newest (e.g., daynum 2009), [n-1]=oldest (e.g., daynum 1543)
    For day at index i, preceding days are at indices [i+1, i+2, i+3, i+4, i+5]

    Args:
        rsi_values: List of RSI values (newest to oldest)
        macd_hist_values: List of MACD histogram values (newest to oldest)
        day_index: Index of the day to grade

    Returns:
        Grade string: one of the configured grades, or "" (empty)
    """
    # Need 5 preceding days - check if we have enough data
    if day_index + LOOKBACK_PERIOD >= len(rsi_values):
        return ""  # Not enough preceding data
    if day_index + LOOKBACK_PERIOD >= len(macd_hist_values):
        return ""  # Not enough MACD histogram data

    # Extract 5 preceding MACD histogram values (indices i+1 through i+5)
    # CRUCIAL CHECK: All must be >= 0 (no negative values allowed)
    preceding_macd_hist = []
    for offset in range(1, LOOKBACK_PERIOD + 1):
        macd_hist = macd_hist_values[day_index + offset]
        if macd_hist is None:
            return ""  # Missing MACD histogram data
        preceding_macd_hist.append(macd_hist)

    # Check if ANY histogram value is negative - if so, return empty grade
    if any(hist < 0 for hist in preceding_macd_hist):
        return ""  # Negative histogram detected - no uptrend grade

    # Extract 5 preceding RSI values (indices i+1 through i+5)
    preceding_rsi = []
    for offset in range(1, LOOKBACK_PERIOD + 1):
        rsi = rsi_values[day_index + offset]
        if rsi is None:
            return ""  # Missing RSI data
        preceding_rsi.append(rsi)

    # Check if we have exactly 5 valid values
    if len(preceding_rsi) != LOOKBACK_PERIOD:
        return ""

    # Evaluate grade rules in order - first match wins
    for grade_name, test_func in GRADE_RULES:
        try:
            if test_func(preceding_rsi):
                return grade_name
        except Exception:
            # If test function fails, skip to next rule
            continue

    # No rules matched
    return ""


def process_ticker_row(ticker: str, rsi_strings: List[str], macd_hist_strings: List[str]) -> List[str]:
    """
    Process a single ticker row: parse RSI and MACD histogram values, then grade uptrend.

    Args:
        ticker: Ticker symbol
        rsi_strings: List of RSI strings from CSV
        macd_hist_strings: List of MACD histogram strings from CSV

    Returns:
        List of uptrend grades (empty string where grading not possible)
    """
    # Parse RSI values
    rsi_values = []
    for rsi_str in rsi_strings:
        rsi = parse_european_decimal(rsi_str)
        rsi_values.append(rsi)

    # Parse MACD histogram values
    macd_hist_values = []
    for macd_str in macd_hist_strings:
        macd_hist = parse_european_decimal(macd_str)
        macd_hist_values.append(macd_hist)

    # Grade each day
    grades = []
    for i in range(len(rsi_values)):
        grade = grade_uptrend(rsi_values, macd_hist_values, i)
        grades.append(grade)

    return grades


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Uptrend grading based on RSI + MACD Histogram")

    # Check input files exist
    if not INPUT_RSI_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_RSI_FILE}")
        return 1
    if not INPUT_MACD_HIST_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_MACD_HIST_FILE}")
        return 1

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read RSI input CSV
        print(f"1. Reading RSI input file: {INPUT_RSI_FILE.name}")
        with open(INPUT_RSI_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rsi_rows = list(reader)

        print(f"2. Loaded {len(rsi_rows)} tickers with {len(header)-1} daynum columns")

        # Read MACD Histogram input CSV
        print(f"3. Reading MACD Histogram input file: {INPUT_MACD_HIST_FILE.name}")
        with open(INPUT_MACD_HIST_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip header (same as RSI header)
            macd_rows = list(reader)

        print(f"4. Loaded {len(macd_rows)} tickers from MACD histogram")

        # Create a dictionary for fast MACD histogram lookup
        macd_hist_dict: Dict[str, List[str]] = {}
        for row in macd_rows:
            ticker = row[0]
            macd_hist_dict[ticker] = row[1:]

        # Process each ticker
        output_rows = []
        tickers_processed = 0
        tickers_skipped = 0
        grade_counts = {grade_name: 0 for grade_name, _ in GRADE_RULES}
        grade_counts[""] = 0  # Empty/no grade

        print(f"5. Grading uptrend for {len(rsi_rows)} tickers...")
        for row in rsi_rows:
            ticker = row[0]
            rsi_strings = row[1:]

            # Get corresponding MACD histogram values
            if ticker not in macd_hist_dict:
                print(f"WARNING: Ticker {ticker} not found in MACD histogram data, skipping")
                tickers_skipped += 1
                # Output empty grades
                grades = [""] * len(rsi_strings)
            else:
                macd_hist_strings = macd_hist_dict[ticker]
                # Grade uptrend
                grades = process_ticker_row(ticker, rsi_strings, macd_hist_strings)

            # Count grades
            for grade in grades:
                if grade in grade_counts:
                    grade_counts[grade] += 1
                else:
                    grade_counts[grade] = 1

            # Build output row
            output_row = [ticker] + grades
            output_rows.append(output_row)

            # Count processing stats
            if any(grade != "" for grade in grades):
                tickers_processed += 1

        # Write output CSV
        print(f"6. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)  # Same header as input
            writer.writerows(output_rows)

        # Display grade statistics
        total_cells = sum(grade_counts.values())
        print(f"SUCCESS: {tickers_processed} tickers processed")
        print(f"  Grade distribution:")
        for grade_name, _ in GRADE_RULES:
            count = grade_counts.get(grade_name, 0)
            pct = (count / total_cells * 100) if total_cells > 0 else 0
            print(f"    {grade_name}: {count:,} ({pct:.1f}%)")
        empty_count = grade_counts.get("", 0)
        empty_pct = (empty_count / total_cells * 100) if total_cells > 0 else 0
        print(f"    Empty: {empty_count:,} ({empty_pct:.1f}%)")
        print(f"  Total cells: {total_cells:,}")

        return 0

    except Exception as e:
        print(f"ERROR: Error during uptrend grading: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
