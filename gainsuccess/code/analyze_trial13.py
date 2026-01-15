import pandas as pd
import numpy as np
import os
import glob

# Constants
BASE_DIR = r'\\gandalf\sm-home\potentials\gainsuccess'
INPUT_DIR = os.path.join(BASE_DIR, 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
POTDAT_FILE = os.path.join(INPUT_DIR, 'PotDat.csv')
WINDOW_SIZE = 132
GAIN_THRESHOLD = 0.10

def load_european_csv(filepath):
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

def compute_gains(df_prices, window_size):
    """Calculates forward max gains for a given window size."""
    # GAIN_JUMP = window_size + 1 (to include 'next' N days)
    df_future_max_T = df_prices.T.shift(1).rolling(window=window_size+1, min_periods=1).max()
    df_gain = (df_future_max_T.T - df_prices) / df_prices
    return df_gain

def run_analysis(df_prices, indicators_of_interest, anchor_perc, secondary_perc, gain_window):
    print(f"\n--- Running Analysis: Anchor Top {anchor_perc*100:.0f}%, Secondary Top {secondary_perc*100:.0f}%, Window {gain_window} days ---")
    
    df_gain = compute_gains(df_prices, gain_window)
    
    melted_gains = []
    for ticker, row in df_gain.iterrows():
        melted_gains.append(pd.DataFrame({
            'Ticker': ticker,
            'Daynum': row.index,
            'Gain': row.values
        }))
    df_gains_long = pd.concat(melted_gains)
    df_gains_long['Key'] = df_gains_long['Ticker'].astype(str) + "_" + df_gains_long['Daynum'].astype(str)
    df_gains_long = df_gains_long[['Key', 'Gain']].dropna()

    indicator_cached_data = {}
    all_indicators = ['per6m'] + indicators_of_interest
    cutoffs = {}
    
    for ind_name in all_indicators:
        fpath = os.path.join(INPUT_DIR, f'longi_{ind_name}.csv')
        df_ind_raw = load_european_csv(fpath)
        if df_ind_raw is None: continue
        df_ind = apply_special_mapping(df_ind_raw, ind_name)
        df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
        
        melted = []
        for ticker, row in df_ind.iterrows():
            valid_row = row.dropna().head(WINDOW_SIZE)
            if len(valid_row) > 0:
                melted.append(pd.DataFrame({
                    'Ticker': ticker,
                    'Daynum': valid_row.index,
                    'Value': valid_row.values
                }))
        
        if not melted: continue
        df_all = pd.concat(melted)
        total_n = len(df_all)
        
        # Determine specific threshold for this indicator
        perc = anchor_perc if ind_name == 'per6m' else secondary_perc
        
        df_all['rank_desc'] = df_all['Value'].rank(method='first', ascending=False)
        df_all['is_top'] = df_all['rank_desc'] <= (total_n * perc)
        df_all['Key'] = df_all['Ticker'].astype(str) + "_" + df_all['Daynum'].astype(str)
        indicator_cached_data[ind_name] = df_all[['Key', 'is_top']]
        
        # Store cutoff for reporting
        vals = df_all['Value'].values
        if len(vals) > 0:
            cutoffs[ind_name] = np.percentile(vals, (1 - perc) * 100)

    anchor = 'per6m'
    df_anchor_members = indicator_cached_data[anchor][indicator_cached_data[anchor]['is_top']]
    df_anchor_pool = pd.merge(df_anchor_members, df_gains_long, on='Key', how='inner')
    
    base_count = len(df_anchor_pool)
    base_success_count = (df_anchor_pool['Gain'] > GAIN_THRESHOLD).sum()
    base_success_rate = base_success_count / base_count if base_count > 0 else 0
    
    results = []
    # Add anchor itself
    results.append({
        'CombinedIndicator': 'per6m (Base)',
        'Condition': f'Top{anchor_perc*100:.0f}%',
        'Cutoff': cutoffs.get('per6m', 0),
        'Count': base_count,
        'SuccessRate': base_success_rate,
        'Lift': 0.0
    })

    for ind_name in indicators_of_interest:
        if ind_name not in indicator_cached_data: continue
        
        other_members = indicator_cached_data[ind_name][indicator_cached_data[ind_name]['is_top']][['Key']]
        combined = pd.merge(df_anchor_pool, other_members, on='Key', how='inner')
        
        comb_count = len(combined)
        if comb_count > 0:
            comb_success = (combined['Gain'] > GAIN_THRESHOLD).sum()
            comb_success_rate = comb_success / comb_count
            lift = comb_success_rate - base_success_rate
        else:
            comb_success_rate = 0
            lift = 0
            
        results.append({
            'CombinedIndicator': ind_name,
            'Condition': f'Top{secondary_perc*100:.0f}%',
            'Cutoff': cutoffs.get(ind_name, 0),
            'Count': comb_count,
            'SuccessRate': comb_success_rate,
            'Lift': lift
        })

    return pd.DataFrame(results)

def main():
    print("Loading price data...")
    df_prices = load_european_csv(POTDAT_FILE)
    if df_prices is None: return
    df_prices = df_prices.reindex(sorted(df_prices.columns, reverse=True), axis=1)
    
    indicators = ['median_40d', 'median_50d', 'median_100d']
    
    # Trial 13 - Modification 1: Top 20%, 20-day window (GAIN_JUMP=21)
    res_mod1 = run_analysis(df_prices, indicators, 0.20, 0.20, 20)
    print("\nModification 1: Top 20% Thresholds (20-day window)")
    print(res_mod1)
    res_mod1.to_csv(os.path.join(OUTPUT_DIR, 'trial13_mod1_top20.csv'), sep=';', decimal=',', index=False)
    
    # Trial 13 - Modification 2: Top 10%, 40-day window (GAIN_JUMP=41)
    res_mod2 = run_analysis(df_prices, indicators, 0.10, 0.10, 40)
    print("\nModification 2: Top 10% Thresholds (40-day window)")
    print(res_mod2)
    res_mod2.to_csv(os.path.join(OUTPUT_DIR, 'trial13_mod2_40days.csv'), sep=';', decimal=',', index=False)

    # Trial 13 - Modification 3: per6m Top 10%, medians Top 20%, 20-day window
    res_mod3 = run_analysis(df_prices, indicators, 0.10, 0.20, 20)
    print("\nModification 3: Anchor Top 10% / Medians Top 20% (20-day window)")
    print(res_mod3)
    res_mod3.to_csv(os.path.join(OUTPUT_DIR, 'trial13_mod3_mixed.csv'), sep=';', decimal=',', index=False)

if __name__ == "__main__":
    main()
