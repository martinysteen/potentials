import pandas as pd
import glob
import os

# Configuration
INPUT_DIR = r'\\gandalf\sm-home\potentials\gainsuccess\input'
HURDLES = {
    'per6m': 54.59,
    'median_40d': 912.0,
    'median_50d': 905.5,
    'median_100d': 878.5
}
LATEST_DAY = 2059
RECOUP_WINDOW = 20
OPEN_START_DAY = LATEST_DAY - RECOUP_WINDOW + 1  # 2040

def load_european_csv(filename):
    """Loads a CSV with semicolon separator and comma as decimal."""
    try:
        # Load the first row with headers (which are mostly daynums)
        # Note: Indicator files have ticker as first column, then daynums.
        # But looking at the head, the first row is actually a timestamp;daynums.
        # Tickers are in column 0 of subsequent rows.
        df = pd.read_csv(filename, sep=';', decimal=',', index_col=0)
        return df
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return None

def find_open_cases():
    print(f"Analyzing open cases (Start Day >= {OPEN_START_DAY})...")
    
    # Load per6m
    df_per6m = load_european_csv(os.path.join(INPUT_DIR, 'longi_per6m.csv'))
    if df_per6m is None: return

    # Indicators of interest
    top3_median_files = ['longi_median_40d.csv', 'longi_median_50d.csv', 'longi_median_100d.csv']
    median_dfs = {}
    for f in top3_median_files:
        df = load_european_csv(os.path.join(INPUT_DIR, f))
        if df is not None:
            median_dfs[f.replace('longi_', '').replace('.csv', '')] = df

    # Load price data for gain calculation
    df_prices = load_european_csv(os.path.join(INPUT_DIR, 'PotDat.csv'))
    if df_prices is None: return

    results = []

    # Get tickers (intersection to be safe)
    tickers = df_per6m.index.intersection(df_prices.index)
    
    # Iterate through days in the open window
    open_days = [str(d) for d in range(OPEN_START_DAY, LATEST_DAY + 1)]
    # Filter for columns that actually exist in the dataframes
    available_days = [d for d in open_days if d in df_per6m.columns]
    
    latest_day_str = str(LATEST_DAY)

    for ticker in tickers:
        for daynum in available_days:
            per6m_val = df_per6m.loc[ticker, daynum]
            
            # Check per6m hurdle
            if pd.notnull(per6m_val) and per6m_val >= HURDLES['per6m']:
                # print(f"DEBUG: Ticker {ticker} at day {daynum} meets per6m hurdle ({per6m_val})")
                # Check if ANY of the top3 medians meet their hurdle
                matching_median = None
                for m_name, m_df in median_dfs.items():
                    if daynum in m_df.columns:
                        m_val = m_df.loc[ticker, daynum]
                        if ticker == 'WBD': # Debug specific high-per6m ticker
                            print(f"DEBUG: {ticker} at {daynum}: {m_name}={m_val} (Hurdle={HURDLES[m_name]})")
                        if pd.notnull(m_val) and m_val >= HURDLES[m_name]:
                            matching_median = m_name
                            break
                
                if matching_median:
                    # Found a case! Calculate gainPct_from_start_to_now
                    # start_price at daynum, now_price at LATEST_DAY
                    if daynum in df_prices.columns and latest_day_str in df_prices.columns:
                        start_price = df_prices.loc[ticker, daynum]
                        now_price = df_prices.loc[ticker, latest_day_str]
                        
                        if pd.notnull(start_price) and pd.notnull(now_price) and start_price > 0:
                            gain_pct = (now_price - start_price) / start_price * 100
                            results.append({
                                'per6m': per6m_val,
                                'median_NNd': matching_median,
                                'ticker': ticker,
                                'daynum_start': daynum,
                                'daynum_now': LATEST_DAY,
                                'gainPct_from_start_to_now': gain_pct
                            })

    # Create summary table
    if results:
        res_df = pd.DataFrame(results)
        # Reorder columns as requested
        res_df = res_df[['per6m', 'median_NNd', 'ticker', 'daynum_start', 'daynum_now', 'gainPct_from_start_to_now']]
        print("\nOpen Cases Matching Criteria:")
        print(res_df.to_markdown(index=False))
        # Save to output
        res_df.to_csv(r'\\gandalf\sm-home\potentials\gainsuccess\output\open_cases_report.csv', index=False, sep=';', decimal=',')
    else:
        print("\nNo open cases found matching the criteria.")

if __name__ == "__main__":
    find_open_cases()
