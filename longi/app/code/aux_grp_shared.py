"""
Shared builder for the longi_grp_<Attribute>_<metric>.csv sector-aggregate tables.

A sector-aggregate table has exactly the same shape as the per-ticker table it is
built from — same daynum columns, same European CSV format, same 2-decimal
precision — but its ROWS ARE SECTOR NAMES (the distinct values of a Stamdata.csv
attribute such as GICS), not tickers. Each cell is the plain mean of that
sector's tickers' values for that daynum, NaN-skipping.

Because the row keys are sector names these files can never be joined to
ticker-keyed data: they are NOT per-ticker feature files. longi_across.py skips
them by name prefix, and they must stay out of aux_winloss_shared.FEATURE_FILES.

`group_col` is a parameter so a Sector2 (or Zone, Homeland, ...) family is a
drop-in: add thin per-metric scripts and register them, no edit here.
"""

from pathlib import Path
from typing import List
import pandas as pd

from aux_shared import format_european_decimal

INPUT_DIR = Path(__file__).parent.parent / "input"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
STAMDATA_FILE = INPUT_DIR / "Stamdata.csv"

DECIMALS = 2  # matches the precision of the longi_per*.csv sources


def load_ticker_to_group(group_col: str = "GICS") -> pd.Series:
    """
    Load the ticker -> group mapping from Stamdata.csv.

    Args:
        group_col: Stamdata column holding the group label (e.g. "GICS")

    Returns:
        Series indexed by ticker, values = group label. Tickers with a blank
        group are dropped; a duplicated ticker keeps its first occurrence.
    """
    stamdata = pd.read_csv(
        STAMDATA_FILE,
        sep=';',
        dtype=str,
        encoding='utf-8',
    )

    if group_col not in stamdata.columns:
        raise KeyError(f"Column '{group_col}' not found in {STAMDATA_FILE.name}")

    # First column header is a timestamp string, not a label - address it by position
    ticker_col = stamdata.columns[0]

    mapping = stamdata[[ticker_col, group_col]].copy()
    mapping.columns = ["ticker", "group"]
    mapping = mapping.dropna()
    mapping["ticker"] = mapping["ticker"].str.strip()
    mapping["group"] = mapping["group"].str.strip()
    mapping = mapping[(mapping["ticker"] != "") & (mapping["group"] != "")]
    mapping = mapping.drop_duplicates(subset="ticker", keep="first")

    return mapping.set_index("ticker")["group"]


def build_group_average(metric: str, group_col: str = "GICS") -> int:
    """
    Build one sector-aggregate table: longi_grp_<group_col>_<metric>.csv.

    Reads ../output/longi_<metric>.csv (rows=tickers) and writes the same table
    with rows collapsed to the mean per group_col value.

    Args:
        metric: Longi factor short name, e.g. "per1d" -> longi_per1d.csv
        group_col: Stamdata column to group by (e.g. "GICS")

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    source_path = OUTPUT_DIR / f"longi_{metric}.csv"
    output_path = OUTPUT_DIR / f"longi_grp_{group_col}_{metric}.csv"

    try:
        print(f"{group_col} sector aggregation of {source_path.name}")

        ticker_to_group = load_ticker_to_group(group_col)
        groups: List[str] = sorted(ticker_to_group.unique())
        print(f"Loaded {len(ticker_to_group)} ticker->{group_col} mappings, "
              f"{len(groups)} sectors: {groups}")

        # Rows=tickers, columns=daynum strings (newest left); European CSV
        data = pd.read_csv(
            source_path,
            sep=';',
            decimal=',',
            index_col=0,
            encoding='utf-8',
        )
        data.index = data.index.astype(str).str.strip()
        # Guard against a stray non-numeric cell turning a whole column to object
        data = data.apply(pd.to_numeric, errors='coerce')

        # Positional alignment: unmapped tickers get NaN and are dropped by groupby
        ticker_groups = ticker_to_group.reindex(data.index).values
        matched = int(pd.notna(ticker_groups).sum())
        print(f"Aggregating {matched}/{len(data)} tickers across {len(data.columns)} daynums")

        # mean() skips NaN, so a sector's average uses whichever tickers have data
        result = data.groupby(ticker_groups).mean()

        # Keep the full sector row set (and its order) stable across metrics and
        # over time - a sector with no data on any daynum stays as a blank row
        result = result.reindex(groups)

        print(f"Writing output to: {output_path}")
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            # Header mirrors longi_per*.csv: "-" then the daynum columns
            f.write(';'.join(['-'] + [str(col) for col in result.columns]) + '\n')

            for sector in result.index:
                cells = [sector]
                for value in result.loc[sector]:
                    if pd.isna(value):
                        cells.append('')
                    else:
                        cells.append(format_european_decimal(float(value), DECIMALS))
                f.write(';'.join(cells) + '\n')

        print(f"SUCCESS: Created {output_path.name} with {len(groups)} sectors")
        return 0

    except FileNotFoundError as e:
        print(f"ERROR: Required file not found: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: Failed to build {output_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return 1
