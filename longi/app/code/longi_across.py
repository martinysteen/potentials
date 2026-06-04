"""
Cross-Sectional Data Extraction Module - Extract Data for Specific Daynum

This module creates a cross-sectional view of all derived tables for a specific daynum.

Output structure:
- Rows: Stock tickers
- Columns: ticker_<daynum> (first column with daynum), then metrics extracted
  from longi_*.csv files, plus sector aggregates
  - e.g., ticker_2009, rsi, macd_line, macd_signal, macd_histogram,
    per1d, per1w, per1m, per3m, per6m, per1y, rank, median_10d, median_20d,
    median_50d, median_100d, stepup, GICS_1yr, Sector2_1yr
  - GICS_1yr: Sector-aggregated 1-year performance for stock's GICS sector
  - Sector2_1yr: Sector-aggregated 1-year performance for stock's Sector2

Usage:
  Programmatic: from longi_across import make_across; make_across(daynum, target_folder)
  CLI: python3 longi_across.py [daynum] [--target-folder=/path]

Output: across_<daynum>.csv (written to app/output by default)
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Dict, Tuple

# Configuration
INPUT_DIR = Path(__file__).parent.parent / "input"
SOURCE_DIR = Path(__file__).parent.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"
STAMDATA_FILE = INPUT_DIR / "Stamdata.csv"


def parse_european_decimal(value: str) -> Optional[str]:
    """
    Parse European decimal format value, preserving as-is for output.

    Args:
        value: String value (may be empty, European decimal, or plain text)

    Returns:
        Original value stripped, or None if empty
    """
    value = value.strip()
    if not value:
        return None
    return value


def load_stamdata_mappings(quiet: bool = False) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load ticker→GICS and ticker→Sector2 mappings from Stamdata.csv.

    Args:
        quiet: If True, suppress verbose output (used for batch updates)

    Returns:
        Tuple of (ticker_to_gics, ticker_to_sector2) dictionaries
    """
    ticker_to_gics = {}
    ticker_to_sector2 = {}

    try:
        with open(STAMDATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip header row

            for row in reader:
                if len(row) < 20:  # Need at least 20 columns for Sector2
                    continue

                ticker = row[0].strip()
                gics = row[5].strip() if len(row) > 5 else ""  # GICS at index 5
                sector2 = row[19].strip() if len(row) > 19 else ""  # Sector2 at index 19

                if ticker:
                    if gics:
                        ticker_to_gics[ticker] = gics
                    if sector2:
                        ticker_to_sector2[ticker] = sector2

        if not quiet:
            print(f"  Loaded Stamdata mappings: {len(ticker_to_gics)} GICS, {len(ticker_to_sector2)} Sector2")

    except Exception as e:
        print(f"  WARNING: Failed to load Stamdata.csv: {e}")

    return ticker_to_gics, ticker_to_sector2


def get_max_daynum_from_potdat() -> Optional[int]:
    """
    Extract the maximum (leftmost/newest) daynum from PotDat.csv header.

    Returns:
        Maximum daynum value, or None if error
    """
    try:
        with open(POTDAT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)

            # Skip first column (timestamp/label), extract numeric daynums
            daynums = []
            for col in header[1:]:
                try:
                    daynum = int(col.strip())
                    daynums.append(daynum)
                except ValueError:
                    continue  # Skip non-numeric columns

            if not daynums:
                return None

            return max(daynums)

    except Exception as e:
        print(f"ERROR: Failed to read {POTDAT_FILE.name}: {e}")
        return None


def get_available_output_files() -> List[Tuple[str, str]]:
    """
    Scan output directory for longi_*.csv files and extract metric names.

    Returns:
        List of tuples: (metric_name, filepath)
        Example: [("rsi", "longi_rsi.csv"), ("macd_line", "longi_macd_line.csv")]
    """
    source_files = []

    # Find all longi_*.csv files
    for filepath in sorted(SOURCE_DIR.glob("longi_*.csv")):
        filename = filepath.name

        if filename.startswith("across_"):
            continue
        if filename.startswith("longi_grp_"):
            continue

        # Extract metric name: remove "longi_" prefix and ".csv" suffix
        if filename.startswith("longi_") and filename.endswith(".csv"):
            metric_name = filename[6:-4]  # Remove "longi_" and ".csv"
            source_files.append((metric_name, str(filepath)))

    return source_files


def load_column_for_daynum(filepath: str, daynum: int) -> Tuple[List[str], List[Optional[str]]]:
    """
    Load a specific daynum column from a CSV file.

    Args:
        filepath: Path to CSV file
        daynum: Daynum to extract

    Returns:
        Tuple of (tickers, values) where values[i] corresponds to tickers[i]
        Returns ([], []) if daynum not found
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            header = next(reader)

            # Find column index for this daynum
            daynum_str = str(daynum)
            col_idx = None
            for idx, col in enumerate(header[1:], start=1):  # Skip first column (ticker)
                if col.strip() == daynum_str:
                    col_idx = idx
                    break

            if col_idx is None:
                # Daynum not found in this file
                return [], []

            # Extract tickers and values for this column
            tickers = []
            values = []

            for row in reader:
                ticker = row[0]
                tickers.append(ticker)

                # Get value for this daynum column
                if col_idx < len(row):
                    value = parse_european_decimal(row[col_idx])
                else:
                    value = None

                values.append(value)

            return tickers, values

    except Exception as e:
        print(f"WARNING: Failed to read {filepath}: {e}")
        return [], []


def load_sector_aggregated_data(daynum: int, quiet: bool = False) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load sector-aggregated performance data for a specific daynum.

    Args:
        daynum: Daynum to extract
        quiet: If True, suppress verbose output (used for batch updates)

    Returns:
        Tuple of (gics_to_perf, sector2_to_perf) dictionaries
        Maps sector name → performance value for this daynum
    """
    gics_to_perf = {}
    sector2_to_perf = {}

    # Load GICS aggregated data
    gics_file = SOURCE_DIR / "longi_grp_GICS_1yr.csv"
    if gics_file.exists():
        try:
            with open(gics_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                header = next(reader)

                # Find column index for this daynum
                daynum_str = str(daynum)
                col_idx = None
                for idx, col in enumerate(header[1:], start=1):
                    if col.strip() == daynum_str:
                        col_idx = idx
                        break

                if col_idx is not None:
                    for row in reader:
                        sector_name = row[0].strip()
                        if col_idx < len(row):
                            perf_value = parse_european_decimal(row[col_idx])
                            if perf_value:
                                gics_to_perf[sector_name] = perf_value

            if not quiet:
                print(f"  Loaded GICS aggregated data: {len(gics_to_perf)} sectors")

        except Exception as e:
            print(f"  WARNING: Failed to load GICS aggregated data: {e}")

    # Load Sector2 aggregated data
    sector2_file = SOURCE_DIR / "longi_grp_Sector2_1yr.csv"
    if sector2_file.exists():
        try:
            with open(sector2_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                header = next(reader)

                # Find column index for this daynum
                daynum_str = str(daynum)
                col_idx = None
                for idx, col in enumerate(header[1:], start=1):
                    if col.strip() == daynum_str:
                        col_idx = idx
                        break

                if col_idx is not None:
                    for row in reader:
                        sector_name = row[0].strip()
                        if col_idx < len(row):
                            perf_value = parse_european_decimal(row[col_idx])
                            if perf_value:
                                sector2_to_perf[sector_name] = perf_value

            if not quiet:
                print(f"  Loaded Sector2 aggregated data: {len(sector2_to_perf)} sectors")

        except Exception as e:
            print(f"  WARNING: Failed to load Sector2 aggregated data: {e}")

    return gics_to_perf, sector2_to_perf


def extract_cross_sectional_data(daynum: int, quiet: bool = False) -> Tuple[List[str], Dict[str, List[Optional[str]]]]:
    """
    Extract cross-sectional data for all metrics at a specific daynum.

    Args:
        daynum: Daynum to extract
        quiet: If True, suppress verbose output (used for batch updates)

    Returns:
        Tuple of (tickers, metric_data)
        - tickers: List of ticker symbols (consistent across all metrics)
        - metric_data: Dict mapping metric_name -> list of values (one per ticker)
    """
    # Get all available output files
    source_files = get_available_output_files()

    if not source_files:
        print("ERROR: No longi_*.csv output files found")
        return [], {}

    if not quiet:
        print(f"\nFound {len(source_files)} derived tables:")
        for metric_name, _ in source_files:
            print(f"  - {metric_name}")

    # Load data from each file
    tickers = None  # Will be set from first file
    metric_data = {}

    for metric_name, filepath in source_files:
        file_tickers, values = load_column_for_daynum(filepath, daynum)

        if not file_tickers:
            print(f"  WARNING: Daynum {daynum} not found in {Path(filepath).name}")
            continue

        # Set tickers from first successful file
        if tickers is None:
            tickers = file_tickers
        else:
            # Verify ticker consistency
            if file_tickers != tickers:
                print(f"  WARNING: Ticker mismatch in {Path(filepath).name} (skipping)")
                continue

        metric_data[metric_name] = values

    if tickers is None:
        tickers = []

    # Add sector-aggregated performance columns (GICS_1yr and Sector2_1yr)
    if not quiet:
        print(f"\nAdding sector-aggregated performance columns...")
    ticker_to_gics, ticker_to_sector2 = load_stamdata_mappings(quiet=quiet)
    gics_to_perf, sector2_to_perf = load_sector_aggregated_data(daynum, quiet=quiet)

    # Create GICS_1yr column: for each ticker, lookup its GICS sector's performance
    gics_1yr_values = []
    for ticker in tickers:
        gics = ticker_to_gics.get(ticker)
        if gics and gics in gics_to_perf:
            gics_1yr_values.append(gics_to_perf[gics])
        else:
            gics_1yr_values.append(None)

    metric_data["GICS_1yr"] = gics_1yr_values

    # Create Sector2_1yr column: for each ticker, lookup its Sector2's performance
    sector2_1yr_values = []
    for ticker in tickers:
        sector2 = ticker_to_sector2.get(ticker)
        if sector2 and sector2 in sector2_to_perf:
            sector2_1yr_values.append(sector2_to_perf[sector2])
        else:
            sector2_1yr_values.append(None)

    metric_data["Sector2_1yr"] = sector2_1yr_values

    return tickers, metric_data


def write_cross_sectional_csv(daynum: int, tickers: List[str],
                                metric_data: Dict[str, List[Optional[str]]],
                                target_folder: Optional[Path] = None) -> Path:
    """
    Write cross-sectional data to CSV file.

    Column ordering:
    - Regular columns: alphabetically sorted, placed first (left)
    - Group columns (from longi_grp_*): alphabetically sorted, placed last (right)

    Args:
        daynum: Daynum being extracted
        tickers: List of ticker symbols
        metric_data: Dict mapping metric_name -> list of values
        target_folder: Output folder (default: app/output)

    Returns:
        Path to output file
    """
    if target_folder is None:
        target_folder = Path(__file__).parent.parent / "output"

    output_file = target_folder / f"across_{daynum}.csv"

    # Separate regular columns from group columns (GICS_*, Sector2_*, etc.)
    # Group columns are those ending with _1yr, _3m, _6m patterns (from longi_grp_* files)
    regular_cols = []
    group_cols = []

    for col_name in metric_data.keys():
        # Check if this is a group column (contains underscore followed by time period)
        # Pattern: GICS_1yr, Sector2_1yr, etc.
        if '_1yr' in col_name or '_3m' in col_name or '_6m' in col_name or '_1m' in col_name:
            group_cols.append(col_name)
        else:
            regular_cols.append(col_name)

    # Sort each group alphabetically, then combine: regular first, group last
    metric_names = sorted(regular_cols) + sorted(group_cols)

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')

        # Write header: ticker_<daynum> + metric names
        header = [f"ticker_{daynum}"] + metric_names
        writer.writerow(header)

        # Write data rows
        for ticker_idx, ticker in enumerate(tickers):
            row = [ticker]

            for metric_name in metric_names:
                value = metric_data[metric_name][ticker_idx]
                row.append(value if value is not None else "")

            writer.writerow(row)

    return output_file


def make_across(daynum: int, target_folder: Optional[str] = None) -> int:
    """
    Create a cross-sectional snapshot for a specific daynum.

    Deletes any existing across_*.csv files in target_folder before creating new one.

    Args:
        daynum: The daynum to extract
        target_folder: Output folder path (default: app/output); can be string or Path

    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Normalize target_folder
    if target_folder is None:
        target_path = Path(__file__).parent.parent / "output"
    else:
        target_path = Path(target_folder)

    try:
        # Delete existing across_*.csv files in target folder
        if target_path.exists():
            existing_files = list(target_path.glob("across_*.csv"))
            if existing_files:
                print(f"\nCleaning up {len(existing_files)} existing across file(s) from {target_path.name}/")
                for f in existing_files:
                    f.unlink()
                    print(f"  ✗ Deleted: {f.name}")

        # Extract cross-sectional data
        print(f"\nExtracting data for daynum {daynum}...")
        tickers, metric_data = extract_cross_sectional_data(daynum)

        if not tickers:
            print(f"ERROR: No data extracted for daynum {daynum}")
            return 1

        num_tickers = len(tickers)
        num_metrics = len(metric_data)

        print(f"\nExtracted data:")
        print(f"  - Tickers: {num_tickers}")
        print(f"  - Metrics: {num_metrics}")

        # Count data coverage
        total_cells = num_tickers * num_metrics
        filled_cells = sum(
            1 for metric_values in metric_data.values()
            for value in metric_values
            if value is not None
        )

        print(f"  - Data coverage: {filled_cells}/{total_cells} cells ({100*filled_cells/total_cells:.1f}%)")

        # Write output file
        print(f"\nWriting cross-sectional data for daynum {daynum} to {target_path.name}/...")
        output_file = write_cross_sectional_csv(daynum, tickers, metric_data, target_path)

        print(f"\nSUCCESS: Cross-sectional data created")
        print(f"  Daynum: {daynum}")
        print(f"  Output: {output_file.name}")
        print(f"  Tickers: {num_tickers}")
        print(f"  Metrics: {num_metrics}")

        return 0

    except Exception as e:
        print(f"ERROR: Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return 1


def get_existing_daynums_to_update(current_daynum: int) -> List[int]:
    """
    Scan for existing across_*.csv files to update (legacy - kept for backwards compatibility).

    Returns daynums that need updating (excluding the current daynum being created).

    Args:
        current_daynum: The daynum currently being created (exclude from update list)

    Returns:
        List of daynums to update
    """
    return []  # No longer auto-updating files


def update_existing_cross_sectional_files(current_daynum: int) -> None:
    """Legacy function - kept for backwards compatibility, does nothing now."""
    pass


def main() -> int:
    """
    Main execution function for CLI usage.

    Accepts optional command-line arguments:
    - daynum (optional): Specific daynum to extract
    - --target-folder (optional): Output folder (default: app/output)

    If no daynum provided, uses maximum daynum from PotDat.csv.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    print(f"longi_across.py: Cross-sectional data extraction")

    # Parse command-line arguments
    daynum = None
    target_folder = None

    for arg in sys.argv[1:]:
        if arg.startswith("--target-folder="):
            target_folder = arg.split("=", 1)[1]
        else:
            try:
                daynum = int(arg)
            except ValueError:
                print(f"ERROR: Invalid argument: {arg}")
                return 1

    # If no daynum specified, get max from PotDat.csv
    if daynum is None:
        print(f"\nNo daynum specified, reading max daynum from {POTDAT_FILE.name}...")
        daynum = get_max_daynum_from_potdat()

        if daynum is None:
            print(f"ERROR: Failed to determine daynum from {POTDAT_FILE.name}")
            return 1

        print(f"  ✓ Using maximum daynum: {daynum}")

    return make_across(daynum, target_folder)


if __name__ == "__main__":
    sys.exit(main())
