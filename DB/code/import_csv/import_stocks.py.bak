# =============================================================================
# import_stocks.py — Import Stamdata.csv into stocks table
# =============================================================================
# Stamdata.csv col[0] header = timestamp → renamed to 'ticker'
# col[1] header = 'Google' (Google Finance ID) → stored as 'google_id'
# Boolean columns: SM_ejet, FK_analyse, FKplus, Protected
# Date column: Oprettet
# =============================================================================
import pandas as pd
import numpy as np
from pot_import_utils import get_conn, read_eu_csv, log, upsert

CSV = "/home/sm/potentials/DB_old_corr/repositoryRTBI/Stamdata.csv"

# Map CSV column names to DB column names
COL_MAP = {
    'ticker':           'ticker',
    'Google':           'google_id',
    'Name':             'name',
    'Sector':           'sector',
    'Homeland':         'homeland',
    'GICS':             'gics',
    'Link_Summary':     'link_summary',
    'Link_Yahoo':       'link_yahoo',
    'Company_website':  'company_website',
    'StamNote':         'stam_note',
    'SM_ejet':          'sm_ejet',
    'FK_analyse':       'fk_analyse',
    'FKplus':           'fkplus',
    'FKyr':             'fkyr',
    'Oprettet':         'oprettet',
    'Valuta':           'valuta',
    'NperADR':          'nper_adr',
    'Sgrp1':            'sgrp1',
    'Protected':        'protected',
    'Sector2':          'sector2',
    'Check':            'check_flag',
    'Exchange':         'exchange',
    'Zone':             'zone',
    'CoreIndex':        'core_index',
    'Yahoo2':           'yahoo2',
}

BOOL_COLS = ['sm_ejet', 'fk_analyse', 'protected']
DATE_COLS = ['oprettet']

def parse_bool(val):
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ('true', '1', 'yes'):
        return True
    if s in ('false', '0', 'no', ''):
        return False
    return None

def run():
    log("import_stocks START")

    df = read_eu_csv(CSV)
    df = df.rename(columns=COL_MAP)

    # Keep only mapped columns (ignore any extras)
    df = df[[c for c in COL_MAP.values() if c in df.columns]]

    # Boolean columns
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].apply(parse_bool)

    # Date columns
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).str.strip(),
                                    format='%Y%m%d', errors='coerce')
            df[col] = df[col].apply(lambda x: x.date() if pd.notna(x) else None)
    
    def safe_int(x):
        try:
            if x is None or x != x: return None
            return int(float(x))
        except: return None

    def safe_float(x):
        try:
            if x is None or x != x: return None
            return float(x)
        except: return None

    def safe_str_int(x):
        try:
            if x is None or x != x: return None
            return str(int(float(x)))
        except: return None

    df['fkyr']       = df['fkyr'].apply(safe_int)
    df['check_flag'] = df['check_flag'].apply(safe_str_int)
    df['fkplus']     = df['fkplus'].apply(safe_float)
    df['nper_adr']   = df['nper_adr'].apply(safe_float)

    # Convert to object dtype BEFORE to_dict to prevent None→nan reinstatement
    df = df.astype(object).where(pd.notna(df), None)
    rows = df.to_dict('records')

    conn = get_conn()
    n = upsert(conn, 'stocks', rows,
               conflict_cols=['ticker'],
               update_cols=[c for c in COL_MAP.values() if c != 'ticker'])
    conn.close()

    log(f"import_stocks DONE — {n} rows upserted")

if __name__ == '__main__':
    run()
