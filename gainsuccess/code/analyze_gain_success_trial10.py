import pandas as pd
import numpy as np
import os
import glob
import sys

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
        
        # Match Trial 9 loading logic more closely
        df = pd.read_csv(filepath, sep=';', decimal=',', names=headers, skiprows=1, index_col=0)
        
        # Convert daynums (columns) to integers
        new_cols = []
        for col in df.columns:
            try:
                # Handle cases where col might be a string like "2059.0" or " 2059 "
                clean_col = str(col).strip().replace('"', '').replace("'", "")
                new_cols.append(int(float(clean_col)))
            except:
                new_cols.append(col)
        df.columns = new_cols
        
        # For indicators, we might have strings even if we specify decimal=',' if the data has Mixed values
        # (especially for uptrend)
        if is_indicator:
            # We'll handle conversion in apply_special_mapping
            pass
        else:
            # For prices, ensure numeric
            df = df.apply(pd.to_numeric, errors='coerce')
            
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def apply_special_mapping(df, indicator_name):
    """Applies specific numeric conversion and mapping for indicators."""
    if indicator_name == 'uptrend':
        mapping = {
            'VeryGood': 5,
            'Very Good': 5,
            'Good': 4,
            'Maybe': 2
        }
        # If it was already numeric (somehow), convert to string for mapping
        df_str = df.astype(str).apply(lambda x: x.str.strip() if hasattr(x, 'str') else x)
        df_mapped = df_str.replace(mapping)
        # Convert to numeric, handle remaining strings (like 'nan' or empty)
        df_num = df_mapped.apply(pd.to_numeric, errors='coerce')
        # Fill missing with 0 as per user direction
        df_num = df_num.fillna(0)
        return df_num
    else:
        return df.apply(pd.to_numeric, errors='coerce')

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print("Loading price data (PotDat.csv)...")
    df_prices = load_european_csv(POTDAT_FILE)
    if df_prices is None or df_prices.empty:
        print("Failed to load prices or empty.")
        return
    
    # Sort columns descending (newest to oldest)
    df_prices = df_prices.reindex(sorted(df_prices.columns, reverse=True), axis=1)
    
    print(f"Prices shape: {df_prices.shape}, Columns (first 5): {list(df_prices.columns[:5])}")
    
    print(f"Calculating forward max gains ({GAIN_JUMP}-day window)...")
    # For descending columns, shift(1) is the immediate future.
    df_future_max_T = df_prices.T.shift(1).rolling(window=GAIN_JUMP, min_periods=1).max()
    df_max_future = df_future_max_T.T
    df_gain = (df_max_future - df_prices) / df_prices
    
    print(f"Gains shape: {df_gain.shape}")

    indicator_files = glob.glob(os.path.join(INPUT_DIR, 'longi_*.csv'))
    print(f"Found {len(indicator_files)} indicator files.")
    
    comparison_results = []
    indicator_summaries = {}
    
    for idx, fpath in enumerate(sorted(indicator_files)):
        indicator_name = os.path.basename(fpath).replace('longi_', '').replace('.csv', '')
        print(f"[{idx+1}/{len(indicator_files)}] Processing: {indicator_name}...", flush=True)
        
        df_ind_raw = load_european_csv(fpath, is_indicator=True)
        if df_ind_raw is None: continue
            
        df_ind = apply_special_mapping(df_ind_raw, indicator_name)
        df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
        
        common_tickers = df_ind.index.intersection(df_gain.index)
        if len(common_tickers) == 0:
            print(f"  No common tickers between indicator and gains.")
            continue
            
        all_pairs = []
        for ticker in common_tickers:
            ind_series = df_ind.loc[ticker]
            gain_series = df_gain.loc[ticker]
            
            # Align by index (daynums)
            combined = pd.DataFrame({'ind': ind_series, 'gain': gain_series}).dropna()
            if len(combined) > 0:
                all_pairs.append(combined.head(WINDOW_SIZE))
        
        if not all_pairs:
            print(f"  No valid (ind, gain) pairs for {indicator_name}")
            continue
            
        df_all = pd.concat(all_pairs)
        if len(df_all) < 10:
            print(f"  Too few samples ({len(df_all)})")
            continue
            
        df_all['is_success'] = df_all['gain'] > GAIN_THRESHOLD
        
        try:
            # Rank-based deciles to handle ties. 
            # We use ascending=False so that D1 = Highest Values.
            df_all['decile'] = pd.qcut(df_all['ind'].rank(method='first', ascending=False), 10, labels=[f"D{i+1}" for i in range(10)])
            
            # Aggregate
            agg_dict = {
                'ind': ['count', 'mean'],
                'is_success': 'sum'
            }
            summary = df_all.groupby('decile', observed=False).agg(agg_dict)
            summary.columns = ['count', 'avg_ind_value', 'success_count']
            summary['success_rate'] = summary['success_count'] / summary['count']
            
            # Ensure 10 deciles
            for i in range(1, 11):
                d_lab = f"D{i}"
                if d_lab not in summary.index:
                    summary.loc[d_lab] = [0, 0.0, 0, 0.0]
            summary = summary.sort_index()
            
            indicator_summaries[indicator_name] = summary
            
            comparison_results.append({
                'Indicator': indicator_name,
                'D1successRate': summary.loc['D1', 'success_rate'],
                'D10successRate': summary.loc['D10', 'success_rate'],
                'PeakRate': summary['success_rate'].max()
            })
        except Exception as e:
            print(f"  Error processing {indicator_name}: {e}")
            continue

    if not comparison_results:
        print("No results to save.")
        return

    # Save Comparison Table
    df_comp = pd.DataFrame(comparison_results)
    df_comp_final = df_comp[['Indicator', 'D1successRate', 'D10successRate']]
    comp_file = os.path.join(OUTPUT_DIR, 'trial10_comparison.csv')
    df_comp_final.to_csv(comp_file, sep=';', decimal=',', index=False)
    print(f"\nSaved comparison table: {comp_file}")
    
    # Identify top 3 indicators
    top_3_df = df_comp.sort_values(by='PeakRate', ascending=False).head(3)
    print("\nTop 3 Indicators by Peak Success Rate:")
    print(top_3_df[['Indicator', 'PeakRate']])
    
    for _, row in top_3_df.iterrows():
        ind = row['Indicator']
        summary = indicator_summaries[ind]
        full_file = os.path.join(OUTPUT_DIR, f'trial10_full_decile_{ind}.csv')
        summary.to_csv(full_file, sep=';', decimal=',')
        print(f"Saved full decile for {ind}: {full_file}")

if __name__ == "__main__":
    main()
