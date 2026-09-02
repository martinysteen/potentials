"""
makeYfinanceSnapshot.py

Builds Yfinance.csv: a one-row-per-ticker "today's picture" snapshot of the
yFinance analyst target / recommendation fields, taken from the most recent
Daynum available for each ticker in StockData2_stacked.csv (robust to nightly
fetch gaps: a ticker missing from the very latest fetch still shows its last
good row, carrying that row's own Daynum).

The file lands in ../output_stacked/ so updgd_yf3.sh uploads it to Drive
(PotSystem/repositoryRTBI/Yfinance/), from where the PotDatML Google Sheet
imports it for onward importRange.

Because StockData2_stacked.csv only ever accumulates (a ticker dropped from the
universe still has its last-known row in there forever), the snapshot is filtered
down to tickers currently present in ../input/Stamdata.csv -- the system-wide root
ticker list every family's universe derives from. A ticker removed from Stamdata.csv
therefore drops out of Yfinance.csv on the next run, instead of showing stale data
indefinitely.
"""

import os

import pandas as pd

STACKED_FILE  = '../output_stacked/StockData2_stacked.csv'
SNAPSHOT_FILE = '../output_stacked/Yfinance.csv'
STAMDATA_FILE = '../input/Stamdata.csv'

CSV_PARAMS = dict(sep=';', decimal=',', encoding='utf-8')

# Source column -> output header. Extend here to route more fields the same way.
COLUMNS = {
    'Symbol':              'Ticker',
    'Daynum':              'Daynum',
    'Target_HighPrice':    'Target_High',
    'Target_LowPrice':     'Target_Low',
    'Target_MeanPrice':    'Target_Mean',
    'Target_MedianPrice':  'Target_Median',
    'Recommendation_Mean': 'Recomm_Mean',
    'Recommendation_Key':  'Recomm_Key',
    'NumberOfAnalysts':    'NumberOfAnalysts',
    'PreviousClose':       'PrevClose',
    'CurrentPrice':        'Close',
    'TrailingPEG':         'PEG',
    'RevenueGrowth':       'Gr_Sales',
    'EarningsGrowth':      'Gr_Earnings',
    'FullTimeEmpl':        'Empl',
}
# Output columns written as plain integers (no European decimal comma).
INT_COLUMNS = ['Daynum', 'NumberOfAnalysts']


def load_valid_tickers() -> set:
    """Root ticker universe: Stamdata.csv's first column, minus the ^-prefixed
    market indices yf3.py never fetches (same filter as its load_stock_codes()).
    """
    col0 = pd.read_csv(STAMDATA_FILE, sep=';', usecols=[0]).iloc[:, 0].astype(str)
    return set(col0[~col0.str.startswith('^')])


def main():
    df = pd.read_csv(STACKED_FILE, **CSV_PARAMS)

    # Most recent row per ticker. The stacked file is unique on (Symbol, Daynum),
    # so the highest Daynum per Symbol identifies exactly one row.
    idx = df.groupby('Symbol')['Daynum'].idxmax()
    snap = df.loc[idx, list(COLUMNS)].rename(columns=COLUMNS)

    valid = load_valid_tickers()
    before = len(snap)
    snap = snap[snap['Ticker'].isin(valid)]
    n_dropped = before - len(snap)

    for col in INT_COLUMNS:
        snap[col] = pd.to_numeric(snap[col], errors='coerce').astype('Int64')

    snap = snap.sort_values('Ticker').reset_index(drop=True)

    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
    snap.to_csv(SNAPSHOT_FILE, sep=';', decimal=',', index=False, encoding='utf-8')

    print(f'makeYfinanceSnapshot: {len(snap)} tickers -> {SNAPSHOT_FILE} '
          f'({n_dropped} dropped, no longer in Stamdata.csv)')


if __name__ == '__main__':
    main()
