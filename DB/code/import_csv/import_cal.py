# =============================================================================
# import_cal.py — Import Cal.csv into cal table
# =============================================================================
# Cal.csv format: Daynum;Date  (European: comma decimal, semicolon sep)
# daynum is stored as INTEGER, date as DATE
# =============================================================================
import pandas as pd
from pot_import_utils import get_conn, log, upsert

CSV = "/home/sm/potentials/DB/RTBI_corr/Cal.csv"

def run():
    log("import_cal START")

    df = pd.read_csv(CSV, sep=';', decimal=',')
    df.columns = ['daynum', 'date']

    # daynum arrives as float (e.g. 2152.0) due to European decimal — cast to int
    df['daynum'] = df['daynum'].astype(float).astype(int)
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d').dt.date

    rows = df.to_dict('records')

    conn = get_conn()
    n = upsert(conn, 'cal', rows,
               conflict_cols=['daynum'],
               update_cols=['date'])
    conn.close()

    log(f"import_cal DONE — {n} rows upserted")

if __name__ == '__main__':
    run()
