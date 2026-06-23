"""
stackYfinanceData.py

Stacks all daily StockData2*.csv files from ../output/ into a single
long-form CSV at ../output_stacked/StockData2_stacked.csv.

Deduplication: rows whose FetchedDate is already present in the stacked
file are skipped, so re-running is always safe.
"""

import glob
import os
import pandas as pd

OUTPUT_DIR   = '../output/'
STACKED_FILE = '../output_stacked/StockData2_stacked.csv'

CSV_PARAMS = dict(sep=';', decimal=',', encoding='utf-8')


def load_stacked() -> tuple[pd.DataFrame | None, set]:
    """Return (existing_df_or_None, set_of_known_FetchedDates)."""
    if not os.path.exists(STACKED_FILE):
        return None, set()
    df = pd.read_csv(STACKED_FILE, **CSV_PARAMS)
    known = set(df['FetchedDate'].unique())
    return df, known


def main():
    existing_df, known_dates = load_stacked()

    source_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'StockData2*.csv')))
    if not source_files:
        print('stackYfinanceData: no source files found in', OUTPUT_DIR)
        return

    new_frames = []
    for path in source_files:
        try:
            df = pd.read_csv(path, **CSV_PARAMS)
        except Exception as e:
            print(f'stackYfinanceData: could not read {path}: {e}')
            continue

        new_rows = df[~df['FetchedDate'].isin(known_dates)]
        if new_rows.empty:
            continue

        new_dates = set(new_rows['FetchedDate'].unique())
        known_dates.update(new_dates)
        new_frames.append(new_rows)

    if not new_frames:
        total = len(existing_df) if existing_df is not None else 0
        print(f'stackYfinanceData: 0 new rows added — stacked file has {total} rows')
        return

    combined_new = pd.concat(new_frames, ignore_index=True)

    if existing_df is not None:
        result = pd.concat([existing_df, combined_new], ignore_index=True)
    else:
        result = combined_new

    os.makedirs(os.path.dirname(STACKED_FILE), exist_ok=True)
    result.to_csv(STACKED_FILE, sep=';', decimal=',', index=False, encoding='utf-8')

    print(f'stackYfinanceData: {len(combined_new)} new rows added — '
          f'stacked file now has {len(result)} rows')


if __name__ == '__main__':
    main()
