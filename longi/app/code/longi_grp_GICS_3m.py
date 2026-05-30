"""
Calculate GICS sector-aggregated 3-month growth rates.

Reads:
- ../input/Stamdata.csv (ticker → GICS mapping)
- ../output/longi_per3m.csv (individual stock 3-month growth rates)

Writes:
- ../output_grp/longi_grp_GICS_3m.csv

Output structure:
- Rows: Unique GICS sector values
- Columns: All daynums from longi_per3m.csv
- Values: Sector-averaged growth rates using formula: average(1 + growth_rate) - 1
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path


def main() -> int:
    """
    Calculate GICS sector-aggregated 3-month growth rates.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        # Paths
        base_path = Path(__file__).parent.parent
        stamdata_path = base_path / 'input' / 'Stamdata.csv'
        per3m_path = base_path / 'output' / 'longi_per3m.csv'
        output_dir = base_path / 'output_grp'
        output_path = output_dir / 'longi_grp_GICS_3m.csv'

        # Create output_grp directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)

        print("GICS sector aggregation (3-month growth)")
        print(f"Reading Stamdata from: {stamdata_path}")
        print(f"Reading 3-month performance from: {per3m_path}")

        # Read Stamdata.csv to get ticker→GICS mapping
        stamdata = pd.read_csv(
            stamdata_path,
            sep=';',
            decimal=',',
            encoding='utf-8',
            dtype=str
        )

        # Create ticker→GICS mapping (skip header row)
        ticker_to_gics = {}
        for _, row in stamdata.iloc[1:].iterrows():
            ticker = row.iloc[0]
            gics = row.iloc[5]
            if pd.notna(ticker) and pd.notna(gics):
                ticker_to_gics[ticker] = gics

        print(f"Loaded {len(ticker_to_gics)} ticker→GICS mappings")

        unique_gics = sorted(set(ticker_to_gics.values()))
        print(f"Found {len(unique_gics)} unique GICS sectors: {unique_gics}")

        # Read longi_per3m.csv
        per3m = pd.read_csv(
            per3m_path,
            sep=';',
            decimal=',',
            encoding='utf-8'
        )

        header = per3m.columns.tolist()
        daynums = header[1:]

        print(f"Processing {len(per3m)-1} tickers across {len(daynums)} daynums")

        # Initialize result DataFrame
        result = pd.DataFrame(index=unique_gics, columns=header)
        result.iloc[:, 0] = unique_gics

        # For each daynum column, calculate sector-aggregated growth
        for daynum in daynums:
            sector_growth_rates = {gics: [] for gics in unique_gics}

            for idx in range(1, len(per3m)):
                ticker = per3m.iloc[idx, 0]
                growth_rate_value = per3m.iloc[idx][daynum]

                if ticker not in ticker_to_gics:
                    continue
                if pd.isna(growth_rate_value):
                    continue

                try:
                    growth_rate_pct = float(growth_rate_value)
                    growth_rate_decimal = growth_rate_pct / 100.0
                    gics = ticker_to_gics[ticker]
                    sector_growth_rates[gics].append(growth_rate_decimal)
                except (ValueError, TypeError):
                    continue

            for gics in unique_gics:
                rates = sector_growth_rates[gics]
                if len(rates) > 0:
                    avg_growth = np.mean([1 + r for r in rates]) - 1
                    result.loc[gics, daynum] = avg_growth * 100.0
                else:
                    result.loc[gics, daynum] = np.nan

        # Write output with European CSV format
        print(f"Writing output to: {output_path}")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(';'.join(str(col) for col in result.columns) + '\n')

            for idx in result.index:
                row_values = []
                for col in result.columns:
                    val = result.loc[idx, col]
                    if pd.isna(val):
                        row_values.append('')
                    elif isinstance(val, (int, float)):
                        formatted = f"{val:.2f}".replace('.', ',')
                        row_values.append(formatted)
                    else:
                        row_values.append(str(val))
                f.write(';'.join(row_values) + '\n')

        print(f"SUCCESS: Created longi_grp_GICS_3m.csv with {len(unique_gics)} sectors")
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
