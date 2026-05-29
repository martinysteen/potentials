import pandas as pd
import numpy as np
import os
import glob

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
POTDAT_FILE = os.path.join(INPUT_DIR, 'PotDat.csv')
WINDOW_SIZE = 132
GAIN_THRESHOLD = 0.10
GAIN_JUMP = 21

def load_european_csv(filepath, is_indicator=False):
    """Loads a CSV with semicolon separator and comma decimal."""
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

def apply_special_mapping(df, indicator_name):
    """Applies specific numeric conversion and mapping for indicators."""
    if indicator_name == 'uptrend':
        mapping = { 'VeryGood': 5, 'Very Good': 5, 'Good': 4, 'Maybe': 2 }
        df_str = df.astype(str).apply(lambda x: x.str.strip() if hasattr(x, 'str') else x)
        df_mapped = df_str.replace(mapping)
        return df_mapped.apply(pd.to_numeric, errors='coerce').fillna(0)
    else:
        return df.apply(pd.to_numeric, errors='coerce')

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print("Loading price data (PotDat.csv)...")
    df_prices = load_european_csv(POTDAT_FILE)
    if df_prices is None: return
    df_prices = df_prices.reindex(sorted(df_prices.columns, reverse=True), axis=1)
    
    print(f"Calculating forward max gains ({GAIN_JUMP}-day window)...")
    df_future_max_T = df_prices.T.shift(1).rolling(window=GAIN_JUMP, min_periods=1).max()
    df_gain = (df_future_max_T.T - df_prices) / df_prices
    
    indicator_files = sorted(glob.glob(os.path.join(INPUT_DIR, 'longi_*.csv')))
    
    # Storage for DataFrames
    # keyed by indicator_name, contains columns: [Ticker, Daynum, Value, is_d1, is_d10]
    indicator_cached_data = {}
    
    print(f"Processing indicators to find deciles...")
    for idx, fpath in enumerate(indicator_files):
        ind_name = os.path.basename(fpath).replace('longi_', '').replace('.csv', '')
        print(f"  {ind_name}...", end='', flush=True)
        
        df_ind_raw = load_european_csv(fpath, is_indicator=True)
        if df_ind_raw is None: continue
        df_ind = apply_special_mapping(df_ind_raw, ind_name)
        df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
        
        # Extract last 132 samples per ticker
        melted = []
        for ticker, row in df_ind.iterrows():
            valid_row = row.dropna().head(WINDOW_SIZE)
            if len(valid_row) > 0:
                melted.append(pd.DataFrame({
                    'Ticker': ticker,
                    'Daynum': valid_row.index,
                    'Value': valid_row.values
                }))
        
        if not melted:
            print(" no data")
            continue
            
        df_all = pd.concat(melted)
        total_n = len(df_all)
        
        # Rank-based D1 and D10
        # D1 = Top 10% highest
        df_all['rank_desc'] = df_all['Value'].rank(method='first', ascending=False)
        df_all['is_d1'] = df_all['rank_desc'] <= (total_n / 10.0)
        
        # D10 = Bottom 10% lowest
        df_all['rank_asc'] = df_all['Value'].rank(method='first', ascending=True)
        df_all['is_d10'] = df_all['rank_asc'] <= (total_n / 10.0)
        
        # We need a unique key for merging
        df_all['Key'] = df_all['Ticker'].astype(str) + "_" + df_all['Daynum'].astype(str)
        
        indicator_cached_data[ind_name] = df_all[['Key', 'is_d1', 'is_d10']]
        print(" ok")

    # Step 2: Prepare Anchor Pool (per6m in D1)
    anchor = 'per6m'
    if anchor not in indicator_cached_data:
        print(f"Error: {anchor} data not found.")
        return
    
    # We need the Gains for the anchor members
    # Re-extract melted per6m but keep Ticker/Daynum for merging gains
    print(f"\nBuilding Anchor Pool ({anchor}-D1)...")
    # Actually, simpler to just melt the gains once and merge.
    
    melted_gains = []
    # Use per6m tickers to limit gain melting size if needed, but here we can just do all
    for ticker, row in df_gain.iterrows():
        # We only care about ticker/day pairs present in our indicator pools
        melted_gains.append(pd.DataFrame({
            'Ticker': ticker,
            'Daynum': row.index,
            'Gain': row.values
        }))
    
    df_gains_long = pd.concat(melted_gains)
    df_gains_long['Key'] = df_gains_long['Ticker'].astype(str) + "_" + df_gains_long['Daynum'].astype(str)
    df_gains_long = df_gains_long[['Key', 'Gain']].dropna()

    # Get anchor members (per6m D1)
    df_anchor_members = indicator_cached_data[anchor][indicator_cached_data[anchor]['is_d1']]
    df_anchor_pool = pd.merge(df_anchor_members, df_gains_long, on='Key', how='inner')
    
    base_count = len(df_anchor_pool)
    base_success_count = (df_anchor_pool['Gain'] > GAIN_THRESHOLD).sum()
    base_success_rate = base_success_count / base_count if base_count > 0 else 0
    
    print(f"Anchor Base Success Rate: {base_success_rate:.4f} (N={base_count})")

    # Step 3: Test Lift
    lift_results = []
    
    for ind_name in indicator_cached_data:
        if ind_name == anchor: continue
        
        df_ind_info = indicator_cached_data[ind_name]
        
        for condition in ['is_d1', 'is_d10']:
            # Members of other indicator meeting condition
            other_members = df_ind_info[df_ind_info[condition]][['Key']]
            
            # Intersection with anchor pool
            combined = pd.merge(df_anchor_pool, other_members, on='Key', how='inner')
            
            comb_count = len(combined)
            if comb_count > 0:
                comb_success = (combined['Gain'] > GAIN_THRESHOLD).sum()
                comb_success_rate = comb_success / comb_count
                lift = comb_success_rate - base_success_rate
            else:
                comb_success_rate = 0
                lift = 0
            
            lift_results.append({
                'CombinedIndicator': ind_name,
                'Condition': 'Top10%' if condition == 'is_d1' else 'Bottom10%',
                'Count': comb_count,
                'SuccessRate': comb_success_rate,
                'Lift': lift
            })

    # Save and Print Results
    df_lift = pd.DataFrame(lift_results).sort_values(by='SuccessRate', ascending=False)
    output_file = os.path.join(OUTPUT_DIR, 'trial12_combined_lift.csv')
    df_lift.to_csv(output_file, sep=';', decimal=',', index=False)
    
    print("\nTop 10 Combinations by Success Rate:")
    print(df_lift.head(10)[['CombinedIndicator', 'Condition', 'Count', 'SuccessRate', 'Lift']])

if __name__ == "__main__":
    main()
