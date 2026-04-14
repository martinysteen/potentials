# =============================================================================
# import_longi_grp.py — Import output_grp/*.csv into longi_grp table
# =============================================================================
# Files: longi_grp_GICS_1yr.csv, longi_grp_GICS_3m.csv,
#        longi_grp_Sector2_1yr.csv, longi_grp_Sector2_3m.csv
#
# Same wide format as longi files but col[0] = group_label (sector/GICS)
# indicator = filename stem with 'longi_grp_' prefix stripped
#   e.g. longi_grp_GICS_1yr.csv → indicator = 'GICS_1yr'
# =============================================================================
import os
import glob
import pandas as pd
from pot_import_utils import get_conn, read_eu_csv, log, upsert

GRP_DIR = "/home/sm/potentials/DB_old_corr/repositoryRTBI/Longi/output_grp"

def process_file(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    indicator = stem.replace('longi_grp_', '')

    df = read_eu_csv(path)

    # col[0] is group_label (renamed from timestamp header by read_eu_csv)
    # rename 'ticker' back to 'group_label' — it's not a ticker here
    df = df.rename(columns={'ticker': 'group_label'})

    daynum_cols = [c for c in df.columns if c != 'group_label']

    df_long = df.melt(
        id_vars='group_label',
        value_vars=daynum_cols,
        var_name='daynum',
        value_name='value'
    )

    df_long['daynum']    = df_long['daynum'].astype(int)
    df_long['indicator'] = indicator
    df_long = df_long.dropna(subset=['value'])

    return df_long[['group_label', 'daynum', 'indicator', 'value']]

def run():
    log("import_longi_grp START")

    files = sorted(glob.glob(os.path.join(GRP_DIR, 'longi_grp_*.csv')))
    log(f"  Found {len(files)} longi_grp_*.csv files")

    conn = get_conn()
    total = 0

    for path in files:
        fname = os.path.basename(path)
        log(f"  Processing {fname}...")

        df = process_file(path)
        rows = df.to_dict('records')

        n = upsert(conn, 'longi_grp', rows,
                   conflict_cols=['group_label', 'daynum', 'indicator'],
                   update_cols=['value'])
        total += n
        log(f"    → {n:,} rows upserted (indicator: {df['indicator'].iloc[0]})")

    conn.close()
    log(f"import_longi_grp DONE — {total:,} total rows upserted")

if __name__ == '__main__':
    run()
