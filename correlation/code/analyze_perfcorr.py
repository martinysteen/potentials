import pandas as pd
import glob
import os
import sys

def load_european_csv(filepath):
    """
    Loads a CSV with ';' as separator and ',' as decimal.
    Expects first column to be Ticker, subsequent columns to be Daynums.
    """
    df = pd.read_csv(filepath, sep=';', decimal=',', index_col=0, low_memory=False)
    # The index is the Ticker. Columns are Daynums.
    # Melt to long format: Ticker, Daynum, Value
    df = df.reset_index()
    df.rename(columns={df.columns[0]: 'Yahoo'}, inplace=True)
    df_long = df.melt(id_vars=['Yahoo'], var_name='Daynum', value_name='Value')
    
    # Ensure Daynum is integer
    df_long['Daynum'] = pd.to_numeric(df_long['Daynum'], errors='coerce')
    
    # Custom mapping for categorical indicators (specifically 'uptrend')
    if 'uptrend' in filepath.lower():
        mapping = {
            'VeryGood': 5,
            'Good': 4,
            'Maybe': 2
        }
        # Map values, fill others with 0, then ensure numeric
        df_long['Value'] = df_long['Value'].map(mapping).fillna(0)
    else:
        df_long['Value'] = pd.to_numeric(df_long['Value'], errors='coerce')
    
    return df_long.dropna(subset=['Daynum'])

def calculate_future_gains(price_df, offset=21):
    """
    Calculates forward gain. For a day t, Gain = Price(t+offset)/Price(t) - 1.
    Note: In the input, daynums are descending. t+offset is a LARGER Daynum (more recent).
    """
    # Sort by Ticker and Daynum (ascending) for easy windowing
    df = price_df.sort_values(['Yahoo', 'Daynum']).copy()
    
    # Calculate gain: (Price at Daynum+offset) / (Price at Daynum) - 1
    # Since we sorted by Daynum ascending, we use shift(-offset) to get 'future' value
    df['Price_Future'] = df.groupby('Yahoo')['Value'].shift(-offset)
    df['Gain'] = (df['Price_Future'] / df['Value']) - 1
    
    return df[['Yahoo', 'Daynum', 'Gain']].dropna()

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_dir = os.path.join(base_dir, 'input')
    output_dir = os.path.join(base_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Load Price Data
    print("Loading price data from PotDat.csv...")
    potdat_path = os.path.join(input_dir, 'PotDat.csv')
    if not os.path.exists(potdat_path):
        print(f"Error: {potdat_path} not found.")
        return
        
    price_df = load_european_csv(potdat_path)
    
    # 2. Calculate 20-day gains (21 points)
    print("Calculating 20-day gains...")
    gain_df = calculate_future_gains(price_df, offset=21)
    
    # 3. Process indicators
    indicator_files = glob.glob(os.path.join(input_dir, 'longi_*.csv'))
    results = []
    
    print(f"Processing {len(indicator_files)} indicators...")
    for file in indicator_files:
        indicator_name = os.path.basename(file).replace('longi_', '').replace('.csv', '')
        print(f"  Analyzing {indicator_name}...")
        
        # Load indicator
        ind_df = load_european_csv(file)
        ind_df.rename(columns={'Value': 'IndValue'}, inplace=True)
        
        # Merge with gains on Ticker and Daynum
        merged = pd.merge(gain_df, ind_df, on=['Yahoo', 'Daynum'], how='inner')
        
        if not merged.empty:
            # Calculate correlation PER STOCK (Yahoo)
            # We filter out stocks with too few samples or zero variance to avoid NaN correlations
            stock_corrs = merged.groupby('Yahoo').apply(
                lambda x: x['IndValue'].corr(x['Gain']) if len(x) > 1 and x['IndValue'].std() > 0 and x['Gain'].std() > 0 else None,
                include_groups=False
            ).dropna()
            
            if not stock_corrs.empty:
                results.append({
                    'Indicator': indicator_name,
                    'Global_Corr': merged['IndValue'].corr(merged['Gain']),
                    'Min_Corr': stock_corrs.min(),
                    'Max_Corr': stock_corrs.max(),
                    'Mean_Stock_Corr': stock_corrs.mean(),
                    'Total_Samples': len(merged),
                    'Stock_Count': len(stock_corrs)
                })
            else:
                print(f"    Warning: No valid per-stock correlations for {indicator_name}")
        else:
            print(f"    Warning: No overlapping data for {indicator_name}")
            
    # 4. Save results
    if results:
        results_df = pd.DataFrame(results).sort_values('Indicator')
        output_path = os.path.join(output_dir, 'performance_correlation_20d_augmented.csv')
        results_df.to_csv(output_path, index=False, sep=';', decimal=',')
        print(f"\nResults saved to {output_path}")
        print(results_df.to_string(index=False))
    else:
        print("No results generated.")

if __name__ == "__main__":
    main()
