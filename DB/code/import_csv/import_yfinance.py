# =============================================================================
# import_yfinance.py — Import Stockdata2_stacked.csv into yfinance table
# =============================================================================
# Already in long format. One row per ticker per fetch.
# col[0] = Symbol (ticker), col[1] = FetchedDate (timestamp string)
# Currency column added to schema.
# =============================================================================
import pandas as pd
from pot_import_utils import get_conn, log, upsert

CSV = "/home/sm/potentials/DB/RTBI_corr/Yfinance/StockData2_stacked.csv"

# Map CSV column names → DB column names
COL_MAP = {
    'Symbol':               'ticker',
    'FetchedDate':          'fetched_date',
    'PreviousClose':        'previous_close',
    'CurrentPrice':         'current_price',
    'DividendRate':         'dividend_rate',
    'DividendYield_Pct':    'dividend_yield_pct',
    'ExDivDate':            'ex_div_date',
    'PE_TTM':               'pe_ttm',
    'PE_Fwd':               'pe_fwd',
    'PS_TTM':               'ps_ttm',
    'ProfitMargin':         'profit_margin',
    'FloatShares':          'float_shares',
    'BookValue':            'book_value',
    'PB':                   'pb',
    'EPS_TTM':              'eps_ttm',
    'EPS_Fwd':              'eps_fwd',
    'DividendLast':         'dividend_last',
    'Date_DividendLast':    'date_dividend_last',
    'Target_HighPrice':     'target_high_price',
    'Target_LowPrice':      'target_low_price',
    'Target_MeanPrice':     'target_mean_price',
    'Target_MedianPrice':   'target_median_price',
    'Recommendation_Mean':  'recommendation_mean',
    'Recommendation_Key':   'recommendation_key',
    'NumberOfAnalysts':     'number_of_analysts',
    'Revenue_Total':        'revenue_total',
    'RevenuePerShare':      'revenue_per_share',
    'FreeCashFlow':         'free_cash_flow',
    'EarningsGrowth':       'earnings_growth',
    'RevenueGrowth':        'revenue_growth',
    'GrossMargin':          'gross_margin',
    'EbitdaMargin':         'ebitda_margin',
    'OperatingMargin':      'operating_margin',
    'TrailingPEG':          'trailing_peg',
    'FullTimeEmpl':         'full_time_employees',
}

DATE_COLS = ['ex_div_date', 'date_dividend_last']

def run():
    log("import_yfinance START")

    df = pd.read_csv(CSV, sep=';', decimal=',', low_memory=False)
    df = df.rename(columns=COL_MAP)
    df = df[[c for c in COL_MAP.values() if c in df.columns]]

    # Two-pass parse — handle both date formats in the file
    # New format: YYYY-MM-DD HH:MM (from newer fetches)
    # Old format: DD-MM-YYYY HH:MM (from older fetches)
    parsed_new = pd.to_datetime(df['fetched_date'], format='%Y-%m-%d %H:%M', errors='coerce', utc=True)
    parsed_old = pd.to_datetime(df['fetched_date'], format='%d-%m-%Y %H:%M', errors='coerce', utc=True)
    df['fetched_date'] = parsed_new.fillna(parsed_old)

    # Drop any remaining rows where neither format worked
    before = len(df)
    df = df.dropna(subset=['fetched_date'])
    dropped = before - len(df)
    if dropped > 0:
        log(f"  WARNING: dropped {dropped} rows with unparseable fetched_date")

    # Parse date columns
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
            df[col] = df[col].apply(lambda x: x.date() if pd.notna(x) else None)

    def safe_int(x):
        try:
            if x is None or x != x: return None
            return int(float(x))
        except: return None

    def safe_float(x):
        try:
            if x is None or x != x: return None
            f = float(x)
            # if the float is infinite or -infinite, return None to avoid DB issues
            if f == float('inf') or f == float('-inf'): return None
            return f
        except: return None

    # Integer columns
    df['number_of_analysts']   = df['number_of_analysts'].apply(safe_int)
    df['full_time_employees']  = df['full_time_employees'].apply(safe_int)

    # Float columns — ensure clean floats for all numeric columns
    for col in ['previous_close','current_price','dividend_rate','dividend_yield_pct',
                'pe_ttm','pe_fwd','ps_ttm','profit_margin','book_value','pb',
                'eps_ttm','eps_fwd','dividend_last','target_high_price','target_low_price',
                'target_mean_price','target_median_price','recommendation_mean',
                'revenue_total','revenue_per_share','free_cash_flow','earnings_growth',
                'revenue_growth','gross_margin','ebitda_margin','operating_margin',
                'trailing_peg','float_shares']:
        df[col] = df[col].apply(safe_float)

    # Prevent None→nan reinstatement
    df = df.astype(object).where(pd.notna(df), None)

    # Deduplicate — keep last occurrence of each ticker+fetched_date combination
    before = len(df)
    df = df.drop_duplicates(subset=['ticker', 'fetched_date'], keep='last')
    dupes = before - len(df)
    if dupes > 0:
        log(f"  WARNING: dropped {dupes} duplicate ticker+fetched_date rows")
        
    rows = df.to_dict('records')

    conn = get_conn()
    n = upsert(conn, 'yfinance', rows,
               conflict_cols=['ticker', 'fetched_date'],
               update_cols=[c for c in COL_MAP.values()
                            if c not in ('ticker', 'fetched_date')])
    conn.close()

    log(f"import_yfinance DONE — {n} rows upserted")

if __name__ == '__main__':
    run()
