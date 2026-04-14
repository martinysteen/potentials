# =============================================================================
# pot_import_utils.py — Shared utilities for PotSystem CSV → PostgreSQL import
# =============================================================================
import os
import re
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

# --- Database connection ------------------------------------------------------
DB_PARAMS = {
    "host":     "localhost",
    "dbname":   "potsystem",
    "user":     "sm",
}

def get_conn():
    return psycopg2.connect(**DB_PARAMS)

# --- European CSV parsing -----------------------------------------------------
def read_eu_csv(path, **kwargs):
    """
    Read a European-format CSV (semicolon separator, comma decimal).
    Automatically strips the timestamp from col[0] header and renames it
    to 'ticker' — the standard pattern across all PotSystem wide files.
    """
    df = pd.read_csv(path, sep=';', decimal=',', low_memory=False, **kwargs)

    # Rename col[0] if its header looks like a timestamp (contains digits and
    # punctuation but is not a plain column name like 'Symbol' or 'Daynum')
    first_col = df.columns[0]
    if _is_timestamp_header(str(first_col)):
        df = df.rename(columns={first_col: 'ticker'})

    return df

def _is_timestamp_header(s):
    """
    Returns True if the string looks like a timestamp header used by PotSystem.
    Examples: 'Mon Apr 13 2026 12:51:15 GMT+0200 (Central European Summer Time)'
              '13-04-26  00:42'
              'Sat Apr 11 2026 00:05:38 GMT+0200 (Central European Summer Time)'
    Returns False for plain names like 'Symbol', 'Daynum', 'Indicator'
    """
    ts_patterns = [
        r'\d{2}-\d{2}-\d{2}',           # 13-04-26
        r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)',# weekday prefix
        r'GMT[+-]\d{4}',                 # GMT offset
    ]
    return any(re.search(p, s) for p in ts_patterns)

# --- European number parsing --------------------------------------------------
def parse_eu_float(series):
    """
    Convert a pandas Series of European-format number strings to float.
    Handles: '1.234,56' → 1234.56, '1234,56' → 1234.56, '' → NaN
    """
    if series.dtype in ['float64', 'int64']:
        return series
    return (series.astype(str)
                  .str.replace('.', '', regex=False)
                  .str.replace(',', '.', regex=False)
                  .pipe(pd.to_numeric, errors='coerce'))

# --- Bulk upsert helper -------------------------------------------------------
def upsert(conn, table, rows, conflict_cols, update_cols=None):
    """
    Bulk insert rows into table with ON CONFLICT DO UPDATE.
    rows: list of dicts
    conflict_cols: list of column names forming the unique key
    update_cols: columns to update on conflict (None = all non-key cols)
    """
    if not rows:
        print(f"  No rows to upsert into {table}")
        return 0

    cols = list(rows[0].keys())
    if update_cols is None:
        update_cols = [c for c in cols if c not in conflict_cols]

    conflict_str = ', '.join(conflict_cols)
    set_str = ', '.join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    sql = f"""
        INSERT INTO {table} ({', '.join(cols)})
        VALUES %s
        ON CONFLICT ({conflict_str})
        DO UPDATE SET {set_str}
    """
    values = [[r[c] for c in cols] for r in rows]

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=1000)
    conn.commit()
    return len(rows)

# --- Logging helper ----------------------------------------------------------
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

