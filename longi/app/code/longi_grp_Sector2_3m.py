"""
Calculate Sector2-aggregated 3-month growth rates.

Reads:
- ../input/Stamdata.csv (ticker → Sector2 mapping)
- ../output/longi_per3m.csv (individual stock 3-month growth rates)

Writes:
- ../output/longi_grp_Sector2_3m.csv

Output structure:
- Rows: Unique Sector2 values
- Columns: All daynums from longi_per3m.csv
- Values: Sector-averaged growth rates using formula: average(1 + growth_rate) - 1
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path


def main() -> int:
    """
    Calculate Sector2-aggregated 3-month growth rates.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        # Paths
        base_path = Path(__file__).parent.parent
        stamdata_path = base_path / 'input' / 'Stamdata.csv'
        per3m_path = base_path / 'output' / 'longi_per3m.csv'
        output_dir = base_path / 'output'
        output_path = output_dir / 'longi_grp_Sector2_3m.csv'

        print("Sector2 aggregation (3-month growth)")
        print(f"Reading Stamdata from: {stamdata_path}")
        print(f"Reading 3-month performance from: {per3m_path}")

        stamdata = pd.read_csv(
            stamdata_path,
            sep=';',
            decimal=',',
            encoding='utf-8',
            dtype=str
        )

        ticker_to_sector2 = {}
        for _, row in stamdata.iloc[1:].iterrows():
            ticker = row.iloc[0]
            sector2 = row.iloc[19]
            if pd.notna(ticker) and pd.notna(sector2) and sector2.strip() != '':
                ticker_to_sector2[ticker] = sector2

        print(f"Loaded {len(ticker_to_sector2)} ticker→Sector2 mappings")

        unique_sector2 = sorted(set(ticker_to_sector2.values()))
        print(f"Found {len(unique_sector2)} unique Sector2 values")

        per3m = pd.read_csv(
            per3m_path,
            sep=';',
            decimal=',',
            encoding='utf-8'
        )

        header = per3m.columns.tolist()
        daynums = header[1:]

        print(f"Processing {len(per3m)-1} tickers across {len(daynums)} daynums")

        result = pd.DataFrame(index=unique_sector2, columns=header)
        result.iloc[:, 0] = unique_sector2

        for daynum in daynums:
            sector_growth_rates = {sector2: [] for sector2 in unique_sector2}

            for idx in range(1, len(per3m)):
                ticker = per3m.iloc[idx, 0]
                growth_rate_value = per3m.iloc[idx][daynum]

                if ticker not in ticker_to_sector2:
                    continue
                if pd.isna(growth_rate_value):
                    continue

                try:
                    growth_rate_pct = float(growth_rate_value)
                    growth_rate_decimal = growth_rate_pct / 100.0
                    sector2 = ticker_to_sector2[ticker]
                    sector_growth_rates[sector2].append(growth_rate_decimal)
                except (ValueError, TypeError):
                    continue

            for sector2 in unique_sector2:
                rates = sector_growth_rates[sector2]
                if len(rates) > 0:
                    avg_growth = np.mean([1 + r for r in rates]) - 1
                    result.loc[sector2, daynum] = avg_growth * 100.0
                else:
                    result.loc[sector2, daynum] = np.nan

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

        print(f"SUCCESS: Created longi_grp_Sector2_3m.csv with {len(unique_sector2)} sectors")
        print("Done")
        return 0

    except FileNotFoundError as e:
        print(f"ERROR: Required file not found: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: Failed to calculate Sector2 aggregated growth: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
