import pandas as pd
import numpy as np
import os
import glob

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, 'input')
WINDOW_SIZE = 132

def load_european_csv(filepath, is_indicator=False):
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
    except:
        return None

def apply_special_mapping(df, indicator_name):
    if indicator_name == 'uptrend':
        mapping = { 'VeryGood': 5, 'Very Good': 5, 'Good': 4, 'Maybe': 2 }
        df_str = df.astype(str).apply(lambda x: x.str.strip() if hasattr(x, 'str') else x)
        df_mapped = df_str.replace(mapping)
        return df_mapped.apply(pd.to_numeric, errors='coerce').fillna(0)
    else:
        return df.apply(pd.to_numeric, errors='coerce')

def main():
    indicator_files = sorted(glob.glob(os.path.join(INPUT_DIR, 'longi_*.csv')))
    
    thresholds = []
    
    for fpath in indicator_files:
        ind_name = os.path.basename(fpath).replace('longi_', '').replace('.csv', '')
        df_ind_raw = load_european_csv(fpath, is_indicator=True)
        if df_ind_raw is None: continue
        df_ind = apply_special_mapping(df_ind_raw, ind_name)
        df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
        
        melted = []
        for ticker, row in df_ind.iterrows():
            valid_row = row.dropna().head(WINDOW_SIZE)
            if len(valid_row) > 0:
                melted.extend(valid_row.values)
        
        if not melted: continue
        
        data = sorted(melted, reverse=True) # D1 at head
        n = len(data)
        d1_idx = int(n / 10.0)
        
        threshold_d1 = data[d1_idx - 1] # Min of D1 (Over this)
        threshold_d10 = data[-d1_idx]    # Max of D10 (Under this)
        
        thresholds.append({
            'Indicator': ind_name,
            'd1_hurdle': threshold_d1,
            'd10_hurdle': threshold_d10
        })

    df_res = pd.DataFrame(thresholds)
    print(df_res.to_string(index=False))

if __name__ == "__main__":
    main()
