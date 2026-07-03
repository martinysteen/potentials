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
"""

import os

import pandas as pd

STACKED_FILE  = '../output_stacked/StockData2_stacked.csv'
SNAPSHOT_FILE = '../output_stacked/Yfinance.csv'

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
}
# Output columns written as plain integers (no European decimal comma).
INT_COLUMNS = ['Daynum', 'NumberOfAnalysts']


def main():
    df = pd.read_csv(STACKED_FILE, **CSV_PARAMS)

    # Most recent row per ticker. The stacked file is unique on (Symbol, Daynum),
    # so the highest Daynum per Symbol identifies exactly one row.
    idx = df.groupby('Symbol')['Daynum'].idxmax()
    snap = df.loc[idx, list(COLUMNS)].rename(columns=COLUMNS)

    for col in INT_COLUMNS:
        snap[col] = pd.to_numeric(snap[col], errors='coerce').astype('Int64')

    snap = snap.sort_values('Ticker').reset_index(drop=True)

    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
    snap.to_csv(SNAPSHOT_FILE, sep=';', decimal=',', index=False, encoding='utf-8')

    print(f'makeYfinanceSnapshot: {len(snap)} tickers -> {SNAPSHOT_FILE}')


if __name__ == '__main__':
    main()
