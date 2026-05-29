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
PERCENTILE = 0.90
GAIN_JUMP = 21

def load_european_csv(filepath):
    """Loads a CSV with semicolon separator and comma decimal."""
    # Read the first line to get headers, handling the metadata string in the first cell
    with open(filepath, 'r') as f:
        first_line = f.readline().strip()
    
    headers = first_line.split(';')
    # The first cell is often a timestamp/metadata, we'll name it 'Ticker'
    headers[0] = 'Ticker'
    
    df = pd.read_csv(filepath, sep=';', decimal=',', names=headers, skiprows=1, index_col=0)
    # Ensure daynums (columns) are integers where possible
    new_cols = []
    for col in df.columns:
        try:
            new_cols.append(int(col))
        except:
            new_cols.append(col)
    df.columns = new_cols
    return df

def main():
    print("Loading price data...")
    df_prices = load_european_csv(POTDAT_FILE)
    
    # Sort columns descending (newest to oldest) just in case
    df_prices = df_prices.reindex(sorted(df_prices.columns, reverse=True), axis=1)
    
    print(f"Calculating forward max gains ({GAIN_JUMP}-day window)...")
    df_max_future = df_prices.shift(1, axis=1).rolling(window=GAIN_JUMP, axis=1, min_periods=1).max()
    df_gain = (df_max_future - df_prices) / df_prices
    
    # Locate indicator files
    indicator_files = glob.glob(os.path.join(INPUT_DIR, 'longi_*.csv'))
    
    # Trial 9: Focus on median_40d and decile analysis
    all_pairs = []
    
    target_indicator = 'median_40d'
    target_file = os.path.join(INPUT_DIR, f'longi_{target_indicator}.csv')
    
    if not os.path.exists(target_file):
        print(f"Error: {target_file} not found.")
        return

    print(f"Processing indicator: {target_indicator} for Trial 9...")
    df_ind = load_european_csv(target_file)
    df_ind = df_ind.apply(pd.to_numeric, errors='coerce')
    df_ind = df_ind.reindex(sorted(df_ind.columns, reverse=True), axis=1)
    
    common_tickers = df_ind.index.intersection(df_gain.index)
    
    for ticker in common_tickers:
        ind_series = df_ind.loc[ticker]
        gain_series = df_gain.loc[ticker]
        
        combined = pd.DataFrame({'ind': ind_series, 'gain': gain_series})
        valid_cases = combined.dropna()
        
        if len(valid_cases) == 0:
            continue
            
        recent_cases = valid_cases.head(WINDOW_SIZE)
        all_pairs.append(recent_cases)
        
    if not all_pairs:
        print("No valid data points found.")
        return
        
    df_all = pd.concat(all_pairs)
    
    # Perform Decile Analysis
    print("Performing Decile Analysis...")
    # Add a small amount of noise to handle ties if necessary, or use 'rank' method in qcut
    df_all['decile'] = pd.qcut(df_all['ind'], 10, labels=[f"D{i+1}" for i in range(10)], duplicates='drop')
    
    # Calculate success (Gain > GAIN_THRESHOLD)
    df_all['is_success'] = df_all['gain'] > GAIN_THRESHOLD
    
    # Aggregate results
    summary = df_all.groupby('decile', observed=False).agg(
        count=('ind', 'count'),
        success_count=('is_success', 'sum'),
        avg_ind_value=('ind', 'mean'),
        min_ind_value=('ind', 'min'),
        max_ind_value=('ind', 'max')
    )
    
    summary['success_rate'] = summary['success_count'] / summary['count']
    
    print("\n--- Trial 9: median_40d Decile Analysis Summary ---")
    print(f"Total Samples: {len(df_all)}")
    print(f"Success Threshold: >{GAIN_THRESHOLD:.0%}")
    print(summary)
    
    # Save decile results
    output_file = os.path.join(OUTPUT_DIR, 'gain_decile_analysis.csv')
    summary.to_csv(output_file, sep=';', decimal=',')
    print(f"\nDecile analysis saved to {output_file}")

    # Plotting
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 6))
    summary['success_rate'].plot(kind='bar', color='skyblue', edgecolor='black')
    plt.title(f'Success Rate by median_40d Decile (Threshold > {GAIN_THRESHOLD:.0%})')
    plt.xlabel('Decile (D1=Lowest, D10=Highest)')
    plt.ylabel('Success Rate')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    plot_path = os.path.join(OUTPUT_DIR, 'median_40d_decile_analysis.png')
    plt.savefig(plot_path)
    print(f"Plot saved to {plot_path}")

if __name__ == "__main__":
    main()

