import pandas as pd
import numpy as np
import os

# Constants
BASE_DIR = r'\\gandalf\sm-home\potentials\gainsuccess'
INPUT_DIR = os.path.join(BASE_DIR, 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
POTDAT_FILE = os.path.join(INPUT_DIR, 'PotDat.csv')
WINDOW_SIZE = 132
GAIN_JUMP = 21

def load_european_csv(filepath):
    try:
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
        headers = first_line.split(';')
        headers[0] = 'Ticker'
        df = pd.read_csv(filepath, sep=';', decimal=',', names=headers, skiprows=1, index_col=0)
        new_cols = []
        for col in df.columns:
            try:
                clean_col = str(col).strip().replace('"', '').replace("'", "")
                new_cols.append(int(float(clean_col)))
            except:
                new_cols.append(col)
        df.columns = new_cols
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def main():
    print("Loading data...")
    df_prices = load_european_csv(POTDAT_FILE)
    df_per6m = load_european_csv(os.path.join(INPUT_DIR, 'longi_per6m.csv'))
    df_m40 = load_european_csv(os.path.join(INPUT_DIR, 'longi_median_40d.csv'))
    
    if df_prices is None or df_per6m is None or df_m40 is None:
        print("Error: Required data files not found.")
        return

    # Align columns (daynums)
    df_prices = df_prices.reindex(sorted(df_prices.columns, reverse=True), axis=1)
    df_per6m = df_per6m.reindex(sorted(df_per6m.columns, reverse=True), axis=1)
    df_m40 = df_m40.reindex(sorted(df_m40.columns, reverse=True), axis=1)

    # Calculate gains
    print("Calculating forward max gains...")
    df_future_max_T = df_prices.T.shift(1).rolling(window=GAIN_JUMP, min_periods=1).max()
    df_gain = (df_future_max_T.T - df_prices) / df_prices

    # Helper to get decile membership (Ticker, Day, Value)
    def get_indicator_data(df, window):
        melted = []
        for ticker, row in df.iterrows():
            valid_row = row.dropna().head(window)
            if len(valid_row) > 0:
                melted.append(pd.DataFrame({
                    'Ticker': ticker,
                    'Daynum': valid_row.index,
                    'Value': valid_row.values
                }))
        return pd.concat(melted) if melted else pd.DataFrame()

    print("Identifying Super-Sample members (per6m D1, median_40d D1+D2)...")
    df_p6m_all = get_indicator_data(df_per6m, WINDOW_SIZE)
    df_m40_all = get_indicator_data(df_m40, WINDOW_SIZE)

    # Find thresholds
    p6m_threshold = np.percentile(df_p6m_all['Value'].values, 90)
    m40_threshold = np.percentile(df_m40_all['Value'].values, 80)

    # Filter members
    df_p6m_members = df_p6m_all[df_p6m_all['Value'] >= p6m_threshold].copy()
    df_m40_members = df_m40_all[df_m40_all['Value'] >= m40_threshold].copy()

    # Join
    df_p6m_members['Key'] = df_p6m_members['Ticker'].astype(str) + "_" + df_p6m_members['Daynum'].astype(str)
    df_m40_members['Key'] = df_m40_members['Ticker'].astype(str) + "_" + df_m40_members['Daynum'].astype(str)

    combined = pd.merge(df_p6m_members[['Key', 'Ticker', 'Daynum']], df_m40_members[['Key']], on='Key', how='inner')

    # Add Gains
    results = []
    for _, row in combined.iterrows():
        ticker = row['Ticker']
        daynum = row['Daynum']
        if ticker in df_gain.index and daynum in df_gain.columns:
            gain = df_gain.loc[ticker, daynum]
            results.append({
                'ticker': ticker,
                'start_daynum': daynum,
                'gain_obtained': gain
            })

    df_final = pd.DataFrame(results).sort_values(by=['start_daynum', 'ticker'])
    
    output_file = os.path.join(OUTPUT_DIR, 'trial14_supersample_members.csv')
    df_final.to_csv(output_file, sep=';', decimal=',', index=False)
    
    print(f"\nSuper-Sample Members (N={len(df_final)}):")
    # For markdown output, print first 50
    print(df_final.to_string(index=False))

if __name__ == "__main__":
    main()
