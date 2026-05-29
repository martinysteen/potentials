"""
Trump Tariff Index Module

Calculates a price index relative to daynum 1863 (2 April 2025, the day Trump
announced retaliatory customs). Index = price / price_at_origin.

Origin daynum 1863 = 1.0. Daynums older than origin are left empty.
Reads PotDat.csv -> outputs longi_trump.csv.
"""

import csv
import sys
from pathlib import Path
from typing import Optional

INPUT_FILE = Path(__file__).parent.parent / "input" / "PotDat.csv"
OUTPUT_FILE = Path(__file__).parent.parent / "output" / "longi_trump.csv"

ORIGIN_DAYNUM = "1863"


def parse_european_decimal(value: str) -> Optional[float]:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def format_european_decimal(value: Optional[float], decimals: int = 4) -> str:
    if value is None:
        return ""
    return f"{value:.{decimals}f}".replace('.', ',')


def main() -> int:
    print(f"Trump Tariff Index (origin daynum {ORIGIN_DAYNUM})")

    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)
            rows = list(reader)

        print(f"Loaded {len(rows)} tickers with {len(header)-1} daynum columns")

        if ORIGIN_DAYNUM not in header:
            print(f"ERROR: Origin daynum {ORIGIN_DAYNUM} not found in header")
            return 1

        origin_col = header.index(ORIGIN_DAYNUM)
        print(f"Origin column index: {origin_col} (daynum {ORIGIN_DAYNUM})")

        # Identify which columns are at or newer than origin (daynum >= ORIGIN_DAYNUM)
        origin_int = int(ORIGIN_DAYNUM)
        active_cols = {i for i, h in enumerate(header) if i > 0 and int(h) >= origin_int}

        output_rows = []
        tickers_with_data = 0
        tickers_no_origin = 0

        for row in rows:
            ticker = row[0]
            origin_price = parse_european_decimal(row[origin_col])

            if origin_price is None or origin_price == 0:
                # No price at origin: entire row empty
                output_rows.append([ticker] + [""] * (len(header) - 1))
                tickers_no_origin += 1
                continue

            result = []
            for i in range(1, len(header)):
                if i in active_cols:
                    price = parse_european_decimal(row[i])
                    index_val = (price / origin_price) if price is not None else None
                    result.append(format_european_decimal(index_val))
                else:
                    result.append("")

            output_rows.append([ticker] + result)
            tickers_with_data += 1

        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)
            writer.writerows(output_rows)

        print(f"Tickers with index: {tickers_with_data}, no origin price: {tickers_no_origin}")
        print(f"SUCCESS: Written to {OUTPUT_FILE.name}")
        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
