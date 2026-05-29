"""
Sector2 3-Month Sector Performance per Ticker Module

Expands sector-aggregated 3-month performance (from longi_grp_Sector2_3m.csv) back to
individual ticker level using the Sector2 mapping from Stamdata.csv.

For each ticker, looks up its Sector2 value, then copies that sector's full row of values.
Result is a standard longi_*.csv file (rows=tickers, columns=daynums).

Depends on: longi_grp_Sector2_3m.py (needs longi_grp_Sector2_3m.csv)
Reads Stamdata.csv and longi_grp_Sector2_3m.csv, outputs longi_Sector2_3m.csv.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import Dict, List

# Configuration
STAMDATA_FILE = Path(__file__).parent.parent / "input" / "Stamdata.csv"
POTDAT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
GRP_FILE = Path(__file__).parent.parent / "output_grp" / "longi_grp_Sector2_3m.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_Sector2_3m.csv"

SECTOR2_COL_INDEX = 19


def load_ticker_to_sector2() -> Dict[str, str]:
    """Load ticker → Sector2 mapping from Stamdata.csv (column index 19)."""
    mapping = {}
    with open(STAMDATA_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header
        for row in reader:
            if len(row) > SECTOR2_COL_INDEX:
                ticker = row[0].strip()
                sector2 = row[SECTOR2_COL_INDEX].strip()
                if ticker and sector2:
                    mapping[ticker] = sector2
    return mapping


def load_grp_data() -> tuple[List[str], Dict[str, List[str]]]:
    """
    Load longi_grp_Sector2_3m.csv.

    Returns:
        Tuple of (daynums_header, sector_data)
        - daynums_header: header row as list of strings (timestamp + daynums)
        - sector_data: dict mapping Sector2 name → list of values (one per daynum)
    """
    with open(GRP_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        sector_data = {}
        for row in reader:
            sector_name = row[0].strip()
            sector_data[sector_name] = row[1:]
    return header, sector_data


def load_ticker_list() -> List[str]:
    """Load ordered ticker list from PotDat.csv (first column)."""
    tickers = []
    with open(POTDAT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header
        for row in reader:
            tickers.append(row[0])
    return tickers


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print("Sector2 3-month sector performance per ticker")

    for f in [STAMDATA_FILE, POTDAT_FILE, GRP_FILE]:
        if not f.exists():
            print(f"ERROR: Input file not found: {f}")
            return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        print(f"1. Reading Sector2 mapping from {STAMDATA_FILE.name}")
        ticker_to_sector2 = load_ticker_to_sector2()
        print(f"   {len(ticker_to_sector2)} ticker→Sector2 mappings loaded")

        print(f"2. Reading sector data from {GRP_FILE.name}")
        header, sector_data = load_grp_data()
        num_daynums = len(header) - 1
        print(f"   {len(sector_data)} sectors, {num_daynums} daynums")

        print(f"3. Reading ticker list from {POTDAT_FILE.name}")
        tickers = load_ticker_list()
        print(f"   {len(tickers)} tickers")

        empty_values = [''] * num_daynums

        print(f"4. Expanding sector data to individual tickers...")
        output_rows = []
        matched = 0
        unmatched = 0

        for ticker in tickers:
            sector2 = ticker_to_sector2.get(ticker)
            if sector2 and sector2 in sector_data:
                output_rows.append([ticker] + sector_data[sector2])
                matched += 1
            else:
                output_rows.append([ticker] + empty_values)
                unmatched += 1

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
