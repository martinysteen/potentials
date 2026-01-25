"""
Ranking Module - Final Rank Based on Average Rank Across All Performance Periods

Step 1: Rank performance values for each time period (1d, 1w, 1m, 3m, 6m, 1y)
  - For each column (daynum), rank all tickers by performance value
  - Rank 1 = highest performance (best)
  - Handle ties: assign same rank to equal values, skip next rank(s)
  - Example: if two values tie at rank 4, both get rank 4, next rank is 6
  - Preserve empty values (no ranking for missing data)

Step 2: Calculate average rank across all 6 periods
  - For each ticker and daynum, average the ranks from all 6 periods
  - Exclude empty values from average calculation
  - Result: average rank values (floats)

Step 3: Rank the average ranks
  - For each column, rank non-index tickers by their average rank
  - Lowest average rank = best performance = final rank 1
  - Index tickers (starting with ^) are excluded from final ranking
  - Output: longi_rank.csv with final integer ranks

Output goes to stdout - start_longi.sh handles logging redirection.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

# Configuration
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "longi_rank.csv"

# Performance files to process
PERFORMANCE_FILES = [
    "longi_per1d.csv",
    "longi_per1w.csv",
    "longi_per1m.csv",
    "longi_per3m.csv",
    "longi_per6m.csv",
    "longi_per1y.csv",
]


def parse_european_decimal(value: str) -> Optional[float]:
    """
    Parse European decimal format (comma as decimal separator).

    Args:
        value: String value to parse (e.g., "123,45")

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


def format_european_decimal(value: Optional[float], decimals: int = 2) -> str:
    """
    Format float to European decimal format (comma as decimal separator).

    Args:
        value: Float value to format
        decimals: Number of decimal places

    Returns:
        Formatted string or empty string if value is None
    """
    if value is None:
        return ""
    # Format with specified decimals and replace dot with comma
    return f"{value:.{decimals}f}".replace('.', ',')


def format_integer(value: Optional[int]) -> str:
    """
    Format integer value.

    Args:
        value: Integer value to format

    Returns:
        Formatted string or empty string if value is None
    """
    if value is None:
        return ""
    return str(value)


def rank_column_values(values: List[Optional[float]]) -> List[Optional[int]]:
    """
    Rank values in a single column (highest value gets rank 1).

    Uses standard/competition ranking: ties get same rank, next rank is skipped.
    Example: 1, 2, 2, 4 (not 1, 2, 2, 3)

    Args:
        values: List of performance values (None for empty cells)

    Returns:
        List of ranks (None for empty cells, same rank for ties)
    """
    # Extract non-None values with their indices
    value_index_pairs = [(val, idx) for idx, val in enumerate(values) if val is not None]

    if not value_index_pairs:
        return [None] * len(values)

    # Sort by value descending (highest first)
    sorted_pairs = sorted(value_index_pairs, key=lambda x: x[0], reverse=True)

    # Assign ranks (standard/competition ranking)
    ranks = [None] * len(values)
    current_rank = 1

    for i, (val, idx) in enumerate(sorted_pairs):
        if i > 0 and val < sorted_pairs[i-1][0]:
            # Value is different from previous, set rank to position + 1
            current_rank = i + 1

        ranks[idx] = current_rank

    return ranks


def load_performance_file(filepath: Path) -> Tuple[List[str], List[str], List[List[Optional[float]]]]:
    """
    Load a performance CSV file.

    Args:
        filepath: Path to CSV file

    Returns:
        Tuple of (header, tickers, data_matrix)
        - header: Column headers (daynum values)
        - tickers: List of ticker symbols
        - data_matrix: 2D list [ticker_idx][column_idx] of performance values
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)

        tickers = []
        data_matrix = []

        for row in reader:
            ticker = row[0]
            tickers.append(ticker)

            # Parse values
            values = [parse_european_decimal(val) for val in row[1:]]
            data_matrix.append(values)

    return header, tickers, data_matrix


def rank_performance_file(filepath: Path) -> List[List[Optional[int]]]:
    """
    Rank all columns in a performance file.

    Args:
        filepath: Path to performance CSV file

    Returns:
        2D list [ticker_idx][column_idx] of rank values
    """
    header, tickers, data_matrix = load_performance_file(filepath)

    num_tickers = len(tickers)
    num_columns = len(data_matrix[0]) if data_matrix else 0

    # Initialize rank matrix
    rank_matrix = [[None] * num_columns for _ in range(num_tickers)]

    # Rank each column independently
    for col_idx in range(num_columns):
        # Extract column values across all tickers
        column_values = [data_matrix[ticker_idx][col_idx] for ticker_idx in range(num_tickers)]

        # Rank the column
        column_ranks = rank_column_values(column_values)

        # Store ranks back in matrix
        for ticker_idx in range(num_tickers):
            rank_matrix[ticker_idx][col_idx] = column_ranks[ticker_idx]

    return rank_matrix


def calculate_average_ranks(rank_matrices: List[List[List[Optional[int]]]],
                           num_tickers: int,
                           num_columns: int) -> List[List[Optional[float]]]:
    """
    Calculate average rank across all performance periods.

    Args:
        rank_matrices: List of rank matrices (one per performance file)
        num_tickers: Number of tickers
        num_columns: Number of columns (daynums)

    Returns:
        2D list [ticker_idx][column_idx] of average ranks (floats)
    """
    avg_rank_matrix = [[None] * num_columns for _ in range(num_tickers)]

    for ticker_idx in range(num_tickers):
        for col_idx in range(num_columns):
            # Collect ranks from all periods for this ticker/column
            ranks = []
            for rank_matrix in rank_matrices:
                rank = rank_matrix[ticker_idx][col_idx]
                if rank is not None:
                    ranks.append(rank)

            # Calculate average (excluding None values)
            if ranks:
                avg_rank = sum(ranks) / len(ranks)
                avg_rank_matrix[ticker_idx][col_idx] = avg_rank
            # else: leave as None

    return avg_rank_matrix


def rank_average_ranks(avg_rank_matrix: List[List[Optional[float]]],
                       tickers: List[str],
                       num_tickers: int,
                       num_columns: int) -> List[List[Optional[int]]]:
    """
    Rank the average ranks for each column (lowest average rank = best = rank 1).
    Index tickers (starting with ^) are excluded from ranking.

    Args:
        avg_rank_matrix: 2D matrix of average ranks
        tickers: List of ticker symbols
        num_tickers: Number of tickers
        num_columns: Number of columns (daynums)

    Returns:
        2D list [ticker_idx][column_idx] of final ranks (integers)
    """
    final_rank_matrix = [[None] * num_columns for _ in range(num_tickers)]

    # Identify non-index tickers
    non_index_indices = [i for i, ticker in enumerate(tickers) if not ticker.startswith('^')]

    # Rank each column independently
    for col_idx in range(num_columns):
        # Extract average ranks for non-index tickers only
        avg_ranks_for_column = []
        for ticker_idx in non_index_indices:
            avg_rank = avg_rank_matrix[ticker_idx][col_idx]
            if avg_rank is not None:
                avg_ranks_for_column.append((avg_rank, ticker_idx))

        if not avg_ranks_for_column:
            continue  # No valid data for this column

        # Sort by average rank ascending (lowest average rank = best performance)
        avg_ranks_for_column.sort(key=lambda x: x[0])

        # Assign final ranks using standard/competition ranking
        current_rank = 1
        for i, (avg_rank, ticker_idx) in enumerate(avg_ranks_for_column):
            if i > 0 and avg_rank > avg_ranks_for_column[i-1][0]:
                # Different value from previous, set rank to position + 1
                current_rank = i + 1

            final_rank_matrix[ticker_idx][col_idx] = current_rank

        # Index tickers remain None (not ranked)

    return final_rank_matrix


def main() -> int:
    """
    Main execution function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"Ranking across all performance periods")

    # Check input files exist
    for filename in PERFORMANCE_FILES:
        filepath = OUTPUT_DIR / filename
        if not filepath.exists():
            print(f"ERROR: Input file not found: {filename}")
            return 1

    try:
        # Step 1: Rank each performance file
        print(f"\nStep 1: Ranking performance values for {len(PERFORMANCE_FILES)} periods...")

        rank_matrices = []
        tickers = None
        header = None

        for filename in PERFORMANCE_FILES:
            filepath = OUTPUT_DIR / filename
            print(f"  - Processing {filename}...")

            # Load and rank this performance file
            file_header, file_tickers, data_matrix = load_performance_file(filepath)
            rank_matrix = rank_performance_file(filepath)
            rank_matrices.append(rank_matrix)

            # Store header and tickers from first file
            if header is None:
                header = file_header
                tickers = file_tickers

            # Verify consistency
            if file_tickers != tickers:
                print(f"WARNING: Ticker mismatch in {filename}")

        num_tickers = len(tickers)
        num_columns = len(rank_matrices[0][0]) if rank_matrices and rank_matrices[0] else 0

        print(f"  ✓ Ranked {num_tickers} tickers across {num_columns} columns for each period")

        # Step 2: Calculate average ranks
        print(f"\nStep 2: Calculating average rank across all {len(PERFORMANCE_FILES)} periods...")
        avg_rank_matrix = calculate_average_ranks(rank_matrices, num_tickers, num_columns)

        # Count statistics
        total_cells = 0
        filled_cells = 0
        for ticker_idx in range(num_tickers):
            for col_idx in range(num_columns):
                total_cells += 1
                if avg_rank_matrix[ticker_idx][col_idx] is not None:
                    filled_cells += 1

        print(f"  ✓ Average ranks calculated: {filled_cells}/{total_cells} cells ({100*filled_cells/total_cells:.1f}%)")

        # Step 3: Rank the average ranks (exclude index tickers starting with ^)
        print(f"\nStep 3: Ranking average ranks (excluding index tickers)...")
        num_index_tickers = sum(1 for t in tickers if t.startswith('^'))
        num_non_index = num_tickers - num_index_tickers
        print(f"  - {num_index_tickers} index tickers excluded (starting with ^)")
        print(f"  - {num_non_index} non-index tickers will be ranked")

        final_rank_matrix = rank_average_ranks(avg_rank_matrix, tickers, num_tickers, num_columns)

        # Count final rank statistics
        final_filled_cells = 0
        for ticker_idx in range(num_tickers):
            for col_idx in range(num_columns):
                if final_rank_matrix[ticker_idx][col_idx] is not None:
                    final_filled_cells += 1

        print(f"  ✓ Final ranks assigned: {final_filled_cells}/{total_cells} cells ({100*final_filled_cells/total_cells:.1f}%)")

        # Write output file
        print(f"\nStep 4: Writing output file: {OUTPUT_FILE.name}")
        with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(header)  # Same header as input

            for ticker_idx in range(num_tickers):
                ticker = tickers[ticker_idx]
                rank_strings = [format_integer(val) for val in final_rank_matrix[ticker_idx]]
                output_row = [ticker] + rank_strings
                writer.writerow(output_row)

        print(f"\nSUCCESS: Average ranking completed")
        print(f"  Output: {OUTPUT_FILE.name}")
        print(f"  Tickers: {num_tickers}")
        print(f"  Columns: {num_columns}")

        return 0

    except Exception as e:
        print(f"ERROR: Error during ranking: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
