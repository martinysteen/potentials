"""
Calculate GICS sector-aggregated 1-year growth rates.

Reads:
- ../input/Stamdata.csv (ticker → GICS mapping)
- ../output/longi_per1y.csv (individual stock 1-year growth rates)

Writes:
- ../output_grp/longi_grp_GICS_1yr.csv

Output structure:
- Rows: Unique GICS sector values
- Columns: All daynums from longi_per1y.csv
- Values: Sector-averaged growth rates using formula: average(1 + growth_rate) - 1
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path


def main() -> int:
    """
    Calculate GICS sector-aggregated 1-year growth rates.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        # Paths
        base_path = Path(__file__).parent.parent
        stamdata_path = base_path / 'input' / 'Stamdata.csv'
        per1y_path = base_path / 'output' / 'longi_per1y.csv'
        output_dir = base_path / 'output_grp'
        output_path = output_dir / 'longi_grp_GICS_1yr.csv'

        # Create output_grp directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)

        print("GICS sector aggregation (1-year growth)")
        print(f"Reading Stamdata from: {stamdata_path}")
        print(f"Reading 1-year performance from: {per1y_path}")

        # Read Stamdata.csv to get ticker→GICS mapping
        # European CSV format: sep=';', decimal=','
        stamdata = pd.read_csv(
            stamdata_path,
            sep=';',
            decimal=',',
            encoding='utf-8',
            dtype=str  # Read as strings to preserve all values
        )

        # Create ticker→GICS mapping (skip header row)
        ticker_to_gics = {}
        for _, row in stamdata.iloc[1:].iterrows():  # Skip header row
            ticker = row.iloc[0]  # First column is ticker
            gics = row.iloc[5]    # GICS column (index 5, 6th column)
            if pd.notna(ticker) and pd.notna(gics):
                ticker_to_gics[ticker] = gics

        print(f"Loaded {len(ticker_to_gics)} ticker→GICS mappings")

        # Get unique GICS sectors
        unique_gics = sorted(set(ticker_to_gics.values()))
        print(f"Found {len(unique_gics)} unique GICS sectors: {unique_gics}")

        # Read longi_per1y.csv
        per1y = pd.read_csv(
            per1y_path,
            sep=';',
            decimal=',',
            encoding='utf-8'
        )

        # First row is timestamp, skip it for processing
        # Second row onwards: first column = ticker, rest = growth rates per daynum
        header = per1y.columns.tolist()
        daynums = header[1:]  # Skip first column (timestamp/ticker column)

        print(f"Processing {len(per1y)-1} tickers across {len(daynums)} daynums")

        # Initialize result DataFrame
        result = pd.DataFrame(index=unique_gics, columns=header)
        result.iloc[:, 0] = unique_gics  # First column = GICS sector names

        # For each daynum column, calculate sector-aggregated growth
        for daynum in daynums:
            # Group stocks by GICS sector
            sector_growth_rates = {gics: [] for gics in unique_gics}

            # Iterate through stocks (skip header row in per1y)
            for idx in range(1, len(per1y)):
                ticker = per1y.iloc[idx, 0]  # First column = ticker
                growth_rate_value = per1y.iloc[idx][daynum]  # Growth rate for this daynum

                # Skip if ticker not in mapping or growth rate is missing
                if ticker not in ticker_to_gics:
                    continue
                if pd.isna(growth_rate_value):
                    continue

                try:
                    # pandas already converted from European format, value is a float in percentage
                    # The value 13.87 means 13.87% growth
                    # Convert from percentage to decimal (e.g., 13.87% -> 0.1387)
                    growth_rate_pct = float(growth_rate_value)
                    growth_rate_decimal = growth_rate_pct / 100.0
                    gics = ticker_to_gics[ticker]
                    sector_growth_rates[gics].append(growth_rate_decimal)
                except (ValueError, TypeError):
                    # Skip invalid values
                    continue

            # Calculate sector-aggregated growth: average(1 + growth_rate) - 1
            for gics in unique_gics:
                rates = sector_growth_rates[gics]
                if len(rates) > 0:
                    # Formula: average(1 + r) - 1
                    avg_growth = np.mean([1 + r for r in rates]) - 1
                    # Convert back to percentage
                    result.loc[gics, daynum] = avg_growth * 100.0
                else:
                    # No data for this sector at this daynum
                    result.loc[gics, daynum] = np.nan

        # Write output with European CSV format
        # Convert float columns to use comma as decimal separator
        print(f"Writing output to: {output_path}")

        # Write with European format
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write(';'.join(str(col) for col in result.columns) + '\n')

            # Write data rows
            for idx in result.index:
                row_values = []
                for col in result.columns:
                    val = result.loc[idx, col]
                    if pd.isna(val):
                        row_values.append('')
                    elif isinstance(val, (int, float)):
                        # Format number with comma as decimal separator
                        # Use same precision as input (2 decimal places for percentages)
                        formatted = f"{val:.2f}".replace('.', ',')
                        row_values.append(formatted)
                    else:
                        row_values.append(str(val))
                f.write(';'.join(row_values) + '\n')

        print(f"SUCCESS: Created longi_grp_GICS_1yr.csv with {len(unique_gics)} sectors")
        print("Done")
        return 0

    except FileNotFoundError as e:
        print(f"ERROR: Required file not found: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: Failed to calculate GICS aggregated growth: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
