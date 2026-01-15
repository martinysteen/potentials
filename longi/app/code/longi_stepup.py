"""
Calculate step-up counts from rolling medians.
A step-up occurs when shorter-period median > longer-period median.

Step-up configurations:
  - longi_stepup40.csv: Comparisons 10d < 20d, 20d < 30d, 30d < 40d (max score: 3)
  - longi_stepup100.csv: Comparisons 10d < 20d, 20d < 50d, 50d < 100d (max score: 3)

Depends on: longi_medians.py (needs longi_median_*.csv in output/)
Outputs: longi_stepup40.csv, longi_stepup100.csv

NOTE: All numeric output uses European format (`;` delimiter, `,` decimal separator).
IMPORTANT: Never use American thousand separators (e.g., 1,234) in any output.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import sys
import os


def load_median_csvs(output_path: str, required_windows: List[int]) -> Dict[int, pd.DataFrame]:
    """
    Loads median CSV files from output directory.

    Args:
        output_path: Path to output directory containing longi_median_*.csv files
        required_windows: List of window sizes to load (e.g., [10, 20, 30, 40] or [10, 20, 50, 100])

    Returns:
        Dictionary {10: df, 20: df, 30: df, 40: df, 50: df, 100: df} (only loaded windows included)
    """
    medians = {}

    for window in required_windows:
        filename = f'longi_median_{window}d.csv'
        filepath = os.path.join(output_path, filename)

        # European CSV format
        df = pd.read_csv(filepath, sep=';', decimal=',', index_col=0)
        medians[window] = df

        print(f"  Loaded {filename}: {len(df)} tickers x {len(df.columns)} daynums")

    return medians


def calculate_stepup_counts(medians: Dict[int, pd.DataFrame], comparisons: List[Tuple[int, int]]) -> pd.DataFrame:
    """
    Calculates step-up counts from median DataFrames using specified comparisons.

    Args:
        medians: Dictionary {window: df} with all median DataFrames
        comparisons: List of (shorter_window, longer_window) tuples
                    e.g., [(10, 20), (20, 30), (30, 40)] for stepup40
                    e.g., [(10, 20), (20, 50), (50, 100)] for stepup100

    Returns:
        DataFrame with step-up counts, same structure as input
        NaN where any median is missing
    """
    # Initialize result with zeros
    result = medians[comparisons[0][0]].copy() * 0

    # Add +1 for each step-up comparison
    for shorter, longer in comparisons:
        stepup = (medians[shorter] < medians[longer]).astype(int)
        result = result + stepup

    # Set to NaN where any median used in comparisons is missing
    # Create mask by checking all windows involved in comparisons
    windows_used = set(sum(comparisons, ()))
    for window in windows_used:
        result = result.where(~medians[window].isna(), np.nan)

    # Convert to nullable integer type (Int64 supports both integers and NaN)
    result = result.astype('Int64')

    return result


def save_and_report(df: pd.DataFrame, output_path: str, filename: str, comparisons: List[Tuple[int, int]]) -> None:
    """
    Saves step-up DataFrame to CSV and prints statistics.

    Args:
        df: DataFrame with step-up counts
        output_path: Path to output directory
        filename: Output filename (e.g., 'longi_stepup40.csv')
        comparisons: List of comparisons for reporting
    """
    filepath = os.path.join(output_path, filename)

    # Ensure nullable integer dtype and write integers.
    # Use pandas nullable Int64 dtype so missing values are preserved as <NA>.
    # When writing, use na_rep='' so missing values become empty cells in the CSV.
    df_output = df.astype('Int64')

    # European CSV format; na_rep='' ensures empty cells for missing values
    df_output.to_csv(filepath, sep=';', decimal=',', na_rep='')

    file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
    print(f"  -> Saved {filename} ({file_size:.1f} MB)")

    # Print statistics
    flat_data = df.values.flatten()
    flat_data = pd.Series(flat_data).dropna()

    max_score = len(comparisons)
    print(f"\n  Step-up count distribution (max score: {max_score}):")
    for count in range(max_score + 1):
        pct = (flat_data == count).sum() / len(flat_data) * 100 if len(flat_data) > 0 else 0
        # NOTE: No thousand separators - European format only
        print(f"    Count {count}: {(flat_data == count).sum()} ({pct:.1f}%)")
    if len(flat_data) > 0:
        print(f"    Mean: {flat_data.mean():.2f}")


def main() -> int:
    """
    Main execution - calculates step-up counts from median files.
    Generates both longi_stepup40.csv and longi_stepup100.csv

    Returns:
        Exit code (0=success, 1=failure)
    """
    try:
        output_path = '../output'

        # Define step-up configurations
        configs = [
            {
                'name': 'stepup40',
                'windows': [10, 20, 30, 40],
                'comparisons': [(10, 20), (20, 30), (30, 40)],
                'filename': 'longi_stepup40.csv'
            },
            {
                'name': 'stepup100',
                'windows': [10, 20, 50, 100],
                'comparisons': [(10, 20), (20, 50), (50, 100)],
                'filename': 'longi_stepup100.csv'
            }
        ]

        print("Loading median CSV files...")
        # Load all required windows
        all_windows = set()
        for config in configs:
            all_windows.update(config['windows'])
        medians = load_median_csvs(output_path, sorted(list(all_windows)))

        # Calculate and save each step-up configuration
        for config in configs:
            print(f"\nCalculating {config['name']}...")
            
            df_stepup = calculate_stepup_counts(medians, config['comparisons'])
            
            valid_count = df_stepup.notna().sum().sum()
            total_count = len(df_stepup) * len(df_stepup.columns)
            print(f"  -> {valid_count:,} / {total_count:,} values calculated")
            
            save_and_report(df_stepup, output_path, config['filename'], config['comparisons'])

        print("\nStep-up calculation complete")
        return 0

    except Exception as e:
        print(f"*** ERROR: {e} ***")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
