"""
CoreIndex RSI per Ticker Module

For each ticker, looks up its CoreIndex (market index) from Stamdata.csv,
then copies that index's full RSI row from longi_rsi.csv.
Result is a standard longi_*.csv file (rows=tickers, columns=daynums).

Depends on: longi_rsi.py (needs longi_rsi.csv)
Outputs: longi_coreindexRSI.csv
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import Dict, List

# Configuration
STAMDATA_FILE = Path(__file__).parent.parent / "input" / "Stamdata.csv"
POTDAT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
RSI_FILE = Path(__file__).parent.parent / "output" / "longi_rsi.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_coreindexRSI.csv"


def load_ticker_to_index() -> Dict[str, str]:
    """Load ticker → CoreIndex mapping from Stamdata.csv (column index 23)."""
    mapping = {}
    with open(STAMDATA_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header
        for row in reader:
            if len(row) > 23:
                ticker = row[0].strip()
                index_ticker = row[23].strip()
                if ticker and index_ticker:
                    mapping[ticker] = index_ticker
    return mapping


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print("CoreIndex RSI per ticker")

    # Check input files
    for f in [STAMDATA_FILE, POTDAT_FILE, RSI_FILE]:
        if not f.exists():
            print(f"ERROR: Input file not found: {f}")
            return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Load CoreIndex mapping
        print(f"1. Reading CoreIndex mapping from {STAMDATA_FILE.name}")
        ticker_to_index = load_ticker_to_index()
        print(f"   {len(ticker_to_index)} ticker→CoreIndex mappings loaded")

        # 2. Load ticker list from PotDat (for row order)
        print(f"2. Reading ticker list from {POTDAT_FILE.name}")
        with open(POTDAT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip header
            tickers = [row[0] for row in reader]
        print(f"   {len(tickers)} tickers")

        # 3. Load RSI data: header + index ticker rows
        print(f"3. Reading RSI data from {RSI_FILE.name}")
        with open(RSI_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rsi_rows = list(reader)

        num_daynums = len(header) - 1
        print(f"   {len(rsi_rows)} tickers, {num_daynums} daynums")

        # Build lookup for index tickers (those starting with ^)
        index_rsi = {}
        for row in rsi_rows:
            t = row[0].strip()
            if t.startswith('^'):
                index_rsi[t] = row[1:]

        print(f"   {len(index_rsi)} index tickers found in RSI file")

        # Empty row for tickers with no match
        empty_values = [''] * num_daynums

        # 4. Build output: for each ticker, copy its index's RSI row
        print(f"4. Expanding index RSI to individual tickers...")
        output_rows = []
        matched = 0
        unmatched = 0

        for ticker in tickers:
            idx_ticker = ticker_to_index.get(ticker)
            if idx_ticker and idx_ticker in index_rsi:
                output_rows.append([ticker] + index_rsi[idx_ticker])
                matched += 1
            else:
                output_rows.append([ticker] + empty_values)
                unmatched += 1

        # 5. Write output
        print(f"5. Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(output_rows)

        print(f"SUCCESS: {matched} tickers matched, {unmatched} unmatched (empty)")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
