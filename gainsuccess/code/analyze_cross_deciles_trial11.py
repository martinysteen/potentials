import pandas as pd
import numpy as np
import os
import glob

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'input')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
WINDOW_SIZE = 132

def load_european_csv(filepath, is_indicator=False):
    """Loads a CSV with semicolon separator and comma decimal."""
    try:
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
        
        headers = first_line.split(';')
        headers[0] = 'Ticker'
        
        df = pd.read_csv(filepath, sep=';', decimal=',', names=headers, skiprows=1, index_col=0)
        
        # Convert daynums (columns) to integers
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
        mapping = {
            'VeryGood': 5,
            'Very Good': 5,
            'Good': 4,
            'Maybe': 2
        }
        df_str = df.astype(str).apply(lambda x: x.str.strip() if hasattr(x, 'str') else x)
        df_mapped = df_str.replace(mapping)
        df_num = df_mapped.apply(pd.to_numeric, errors='coerce').fillna(0)
        return df_num
    else:
        return df.apply(pd.to_numeric, errors='coerce')

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    indicator_files = sorted(glob.glob(os.path.join(INPUT_DIR, 'longi_*.csv')))
    print(f"Found {len(indicator_files)} indicator files.")
    
    # Storage for D1 member sets: {indicator_name: set((ticker, daynum))}
    indicator_d1_members = {}
    # Storage for limits: {indicator_name: (lower, upper)}
    indicator_limits = {}
    
    all_indicator_names = []

    for idx, fpath in enumerate(indicator_files):
        indicator_name = os.path.basename(fpath).replace('longi_', '').replace('.csv', '')
        all_indicator_names.append(indicator_name)
        print(f"[{idx+1}/{len(indicator_files)}] Processing: {indicator_name}...", flush=True)
        
        df_ind_raw = load_european_csv(fpath, is_indicator=True)
        if df_ind_raw is None: continue
            
        df_ind = apply_special_mapping(df_ind_raw, indicator_name)
        # Sort columns descending (newest to oldest)
        df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
        
        # Melt to long format: Ticker, Daynum, Value
        # But we only want the first 132 valid entries per Ticker
        # This is more efficient if handled row by row or via grouped head
        
        melted_parts = []
        for ticker, row in df_ind.iterrows():
            valid_row = row.dropna().head(WINDOW_SIZE)
            if len(valid_row) > 0:
                part = pd.DataFrame({
                    'Ticker': ticker,
                    'Daynum': valid_row.index,
                    'Value': valid_row.values
                })
                melted_parts.append(part)
        
        if not melted_parts:
            print(f"  No valid data for {indicator_name}")
            continue
            
        df_all = pd.concat(melted_parts)
        
        # Calculate Decile D1 (Top 10%)
        # D1 = highest values. method='first' to handle ties precisely 10%
        df_all['rank'] = df_all['Value'].rank(method='first', ascending=False)
        total_n = len(df_all)
        d1_threshold = total_n / 10.0
        
        df_d1 = df_all[df_all['rank'] <= d1_threshold]
        
        if df_d1.empty:
            print(f"  Empty D1 for {indicator_name}")
            continue
            
        # Limits
        lower_limit = df_d1['Value'].min()
        upper_limit = df_d1['Value'].max()
        indicator_limits[indicator_name] = (lower_limit, upper_limit)
        
        # Members
        members = set(zip(df_d1['Ticker'], df_d1['Daynum']))
        indicator_d1_members[indicator_name] = members
        print(f"  D1 size: {len(members)}, Limits: [{lower_limit}, {upper_limit}]")

    # Build the cross-occurrence table
    results = []
    
    # Ensure we use indicator names that actually reached the d1 phase
    processed_names = [name for name in all_indicator_names if name in indicator_d1_members]
    
    for name_row in processed_names:
        row_limits = indicator_limits[name_row]
        row_members = indicator_d1_members[name_row]
        
        row_data = {
            'Indicator': name_row,
            'upperLimit': row_limits[1],
            'lowerLimit': row_limits[0]
        }
        
        for name_col in processed_names:
            col_members = indicator_d1_members[name_col]
            # Count intersection
            overlap_count = len(row_members.intersection(col_members))
            row_data[name_col] = overlap_count
            
        results.append(row_data)

    df_cross = pd.DataFrame(results)
    
    # Save Output
    output_file = os.path.join(OUTPUT_DIR, 'trial11_cross_deciles.csv')
    # European format: semicolon separator, comma decimal
    df_cross.to_csv(output_file, sep=';', decimal=',', index=False)
    print(f"\nTrial 11 results saved to {output_file}")

if __name__ == "__main__":
    main()
