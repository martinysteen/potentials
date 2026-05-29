# =============================================================================
# import_prices.py — Import PotDat.csv into prices table
# =============================================================================
# PotDat.csv is WIDE format:
#   col[0] header = timestamp → ticker
#   col[1..n] headers = daynums (integers)
# Unpivot (melt) to long format: ticker | daynum | close
# =============================================================================
import pandas as pd
from pot_import_utils import get_conn, read_eu_csv, log, upsert

CSV = "/home/sm/potentials/DB_old_corr/repositoryRTBI/PotDat.csv"

def run():
    log("import_prices START")
    log("Reading PotDat.csv (wide format, may take a moment)...")

    df = read_eu_csv(CSV)

    # All columns except 'ticker' are daynums
    daynum_cols = [c for c in df.columns if c != 'ticker']

    log(f"  {len(df)} tickers × {len(daynum_cols)} daynums = "
        f"{len(df) * len(daynum_cols):,} cells to unpivot")

    # Unpivot wide → long
    df_long = df.melt(
        id_vars='ticker',
        value_vars=daynum_cols,
        var_name='daynum',
        value_name='close'
    )

    # daynum column headers are strings after melt — cast to int
    df_long['daynum'] = df_long['daynum'].astype(int)

    # Drop rows where close is NaN (sparse cells — not all tickers trade all days)
    df_long = df_long.dropna(subset=['close'])

    log(f"  After dropping NaN: {len(df_long):,} rows")

    rows = df_long.to_dict('records')

    conn = get_conn()
    n = upsert(conn, 'prices', rows,
               conflict_cols=['ticker', 'daynum'],
               update_cols=['close'])
    conn.close()

    log(f"import_prices DONE — {n} rows upserted")

if __name__ == '__main__':
    run()
