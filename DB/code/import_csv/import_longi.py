# =============================================================================
# import_longi.py — Import all longi_*.csv into longi table
# =============================================================================
# Each file is WIDE format: col[0]=ticker, col[1..n]=daynum headers
# All files are unpivoted and stacked into one long/narrow table:
#   ticker | daynum | indicator | value
#
# indicator = filename stem with 'longi_' prefix stripped
#   e.g. longi_ma10.csv      → indicator = 'ma10'
#        longi_futgain20d.csv → indicator = 'futgain20d'
# =============================================================================
import os
import glob
import pandas as pd
from pot_import_utils import get_conn, read_eu_csv, log, upsert

LONGI_DIR = "/home/sm/potentials/DB/RTBI_corr/Longi"

def process_file(path):
    """Unpivot one longi file, return long-format dataframe."""
    stem = os.path.splitext(os.path.basename(path))[0]
    indicator = stem.replace('longi_', '')

    df = read_eu_csv(path)
    daynum_cols = [c for c in df.columns if c != 'ticker']

    df_long = df.melt(
        id_vars='ticker',
        value_vars=daynum_cols,
        var_name='daynum',
        value_name='value'
    )

    df_long['daynum']    = df_long['daynum'].astype(int)
    df_long['indicator'] = indicator
    df_long = df_long.dropna(subset=['value'])

    return df_long[['ticker', 'daynum', 'indicator', 'value']]

def run():
    log("import_longi START")

    files = sorted(glob.glob(os.path.join(LONGI_DIR, 'longi_*.csv')))
    log(f"  Found {len(files)} longi_*.csv files")

    conn = get_conn()
    total = 0

    for path in files:
        fname = os.path.basename(path)
        log(f"  Processing {fname}...")

        df = process_file(path)
        rows = df.to_dict('records')

        n = upsert(conn, 'longi', rows,
                   conflict_cols=['ticker', 'daynum', 'indicator'],
                   update_cols=['value'])
        total += n
        log(f"    → {n:,} rows upserted (indicator: {df['indicator'].iloc[0]})")

    conn.close()
    log(f"import_longi DONE — {total:,} total rows upserted")

if __name__ == '__main__':
    run()
