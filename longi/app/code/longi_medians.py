"""
Calculate rolling medians over multiple time windows from rank data.
Reads longi_rank.csv and calculates 10d, 20d, 50d, and 100d medians.

Time scale: Left=newest (index 0), Right=oldest (index n-1)

Depends on: longi_rank.py (needs longi_rank.csv in output/)
Outputs: longi_median_10d.csv, longi_median_20d.csv, longi_median_50d.csv, longi_median_100d.csv
"""
import pandas as pd
import numpy as np
from typing import Dict
import sys
import os


def load_rank_data(output_path: str) -> pd.DataFrame:
    """
    Loads longi_rank.csv with European CSV format.

    Args:
        output_path: Path to output directory (where longi_rank.csv is)

    Returns:
        DataFrame with rank data (tickers as rows, daynums as columns)
    """
    file_path = os.path.join(output_path, 'longi_rank.csv')

    # European CSV: semicolon separator, comma decimal
    df = pd.read_csv(file_path, sep=';', decimal=',', index_col=0)

    return df


def calculate_rolling_median(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    Calculates rolling median for specified window size.

    Time scale: Left=newest, Right=oldest
    For day at index i, median uses [i:i+window]

    Args:
        df: Input DataFrame (tickers x daynums)
        window: Rolling window size (10, 20, 30, 40, 50, or 100)

    Returns:
        DataFrame with rolling medians (same structure as input)
        Last (window-1) columns are NaN (insufficient history)
    """
    result = pd.DataFrame(index=df.index, columns=df.columns, dtype=float)

    num_cols = len(df.columns)

    # Calculate median for each position where we have enough history
    for i in range(num_cols - window + 1):
        # Get window: [i:i+window] (current day + next (window-1) days backward)
        window_data = df.iloc[:, i:i+window]

        # Calculate median across the window (axis=1 means row-wise)
        medians = window_data.median(axis=1)

        # Store in result at position i
        result.iloc[:, i] = medians

    # Remaining columns (last window-1) stay NaN - not enough history

    return result


def main() -> int:
    """
    Main execution - calculates all four rolling medians.

    Returns:
        Exit code (0=success, 1=failure)
    """
    try:
        output_path = '../output'

        print("Loading longi_rank.csv...")
        df_rank = load_rank_data(output_path)

        print(f"Loaded {len(df_rank)} tickers x {len(df_rank.columns)} daynums")

        windows = [10, 20, 30, 40, 50, 100]

        for window in windows:
            print(f"Calculating {window}d rolling median...")
            df_median = calculate_rolling_median(df_rank, window)

            # Count non-NaN values
            valid_count = df_median.notna().sum().sum()
            total_count = len(df_rank) * len(df_rank.columns)
            print(f"  -> {valid_count:,} / {total_count:,} values calculated")

            # Save to output
            filename = f'longi_median_{window}d.csv'
            filepath = os.path.join(output_path, filename)

            # European CSV format
            df_median.to_csv(filepath, sep=';', decimal=',')

            file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
            print(f"  -> Saved {filename} ({file_size:.1f} MB)")

        print("\nMedian calculation complete")
        return 0

    except Exception as e:
        print(f"*** ERROR: {e} ***")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
