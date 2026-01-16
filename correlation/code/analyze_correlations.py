import pandas as pd
import glob
import os
import argparse
import sys

# Optional plotting imports
try:
    import seaborn as sns
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

def analyze_correlations(input_dir, output_dir, exclude, plot=True):
    # Expand user paths
    input_dir = os.path.expanduser(input_dir)
    output_dir = os.path.expanduser(output_dir)
    print(f"Looking for data in: {input_dir}")
    print(f"Output directory: {output_dir}")
    if exclude:
        print(f"Excluding indicators: {exclude}")

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Find all longi_*.csv files
    pattern = os.path.join(input_dir, "longi_*.csv")
    files = glob.glob(pattern)

    if not files:
        print(f"No files found matching {pattern}")
        return

    print(f"Found {len(files)} files: {[os.path.basename(f) for f in files]}")

    all_data = []

    for file_path in files:
        filename = os.path.basename(file_path)
        # Extract indicator name: longi_XXX.csv -> XXX
        indicator_name = filename.replace("longi_", "").replace(".csv", "")
        
        if indicator_name in exclude:
            print(f"Skipping excluded indicator: {indicator_name}")
            continue
        
        try:
            # Read CSV with European format
            df = pd.read_csv(file_path, sep=';', decimal=',')
            
            # Rename first column to 'Yahoo'
            # We assume the first column is the ticker, regardless of its name
            first_col = df.columns[0]
            df.rename(columns={first_col: 'Yahoo'}, inplace=True)
            
            # Melt to long format
            # id_vars=['Yahoo'], var_name='Date', value_name=indicator_name
            df_long = df.melt(id_vars=['Yahoo'], var_name='Date', value_name=indicator_name)
            
            # Convert Date to numeric (just in case)
            df_long['Date'] = pd.to_numeric(df_long['Date'], errors='coerce')
            
            # Set multi-index for easy merging/joining later
            df_long.set_index(['Yahoo', 'Date'], inplace=True)
            
            all_data.append(df_long)
            print(f"Loaded {indicator_name} with {len(df_long)} records.")
            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    if not all_data:
        print("No data loaded successfully.")
        return

    # Concatenate all dataframes along columns (aligning on index)
    # Since we set index to Yahoo, Date, this effectively does an outer join on keys
    print("Merging data...")
    # We can stick them together. Since column names are unique (indicator names), this works.
    combined_df = pd.concat(all_data, axis=1)

    # Drop rows with NaN if we only want complete data for correlation, 
    # but .corr() handles NaNs by ignoring them pair-wise usually.
    # Let's keep as is to maximize data usage.
    
    print(f"Combined data shape: {combined_df.shape}")
    
    # 1. Collect and Save Time Spans
    spans = []
    for col in combined_df.columns:
        valid_dates = combined_df[col].dropna().index.get_level_values('Date')
        if not valid_dates.empty:
            spans.append({
                'Indicator': col,
                'Min_DayNum': valid_dates.min(),
                'Max_DayNum': valid_dates.max(),
                'Span': valid_dates.max() - valid_dates.min(),
                'Count': len(valid_dates)
            })
    
    span_df = pd.DataFrame(spans).set_index('Indicator').sort_index()
    span_file = os.path.join(output_dir, "indicator_spans.csv")
    span_df.to_csv(span_file, sep=';', decimal=',')
    print(f"\nTime span report saved to {span_file}")
    print(span_df)

    # 2. Refine NaN Handling
    # Convert all columns to numeric, coercing errors (strings like 'VeryGood' become NaN)
    numeric_df = combined_df.apply(pd.to_numeric, errors='coerce')
    
    # Report missingness
    print("\nMissing Data Report (per column):")
    for col in numeric_df.columns:
        null_count = numeric_df[col].isnull().sum()
        total = len(numeric_df)
        null_pct = (null_count / total) * 100
        print(f" - {col:20}: {null_pct:6.2f}% missing ({null_count}/{total})")

    # Drop columns ONLY if they are 100% NaN or have zero variance (cannot correlate)
    # We also keep columns that are mostly NaN if they have at least 2 non-NaN values
    cols_to_drop = []
    for col in numeric_df.columns:
        if numeric_df[col].isnull().all() or numeric_df[col].nunique() < 2:
            cols_to_drop.append(col)
    
    if cols_to_drop:
        print(f"\nDropping indicators with insufficient data/variance: {cols_to_drop}")
        numeric_df.drop(columns=cols_to_drop, inplace=True)

    if numeric_df.empty:
        print("Error: No numeric data remaining for correlation analysis after filtering.")
        return

    # 3. Calculate Correlation Matrix
    # Pairwise correlation (default) - uses all available pairs
    print("\nCalculating pairwise correlation matrix...")
    correlation_matrix = numeric_df.corr(method='pearson', min_periods=30)
    
    # Complete cases (row-wise drop) - only rows with NO NaNs
    # This addresses the user's point about "sacrificing rows" 
    print("Calculating complete-case correlation matrix (sacrificing rows)...")
    complete_case_df = numeric_df.dropna()
    print(f" - Complete cases (rows with zero NaNs): {len(complete_case_df)}")
    
    if not complete_case_df.empty:
        complete_corr = complete_case_df.corr().sort_index(axis=0).sort_index(axis=1)
        complete_corr_file = os.path.join(output_dir, "correlation_matrix_complete.csv")
        complete_corr.to_csv(complete_corr_file, sep=';', decimal=',')
        print(f" - Saved complete-case matrix to {complete_corr_file}")
    else:
        print(" - No rows found with complete data across all indicators.")

    # 4. Generate Heatmap (if requested and possible)
    if plot and HAS_PLOTTING:
        if not complete_case_df.empty:
            print("\nGenerating correlation heatmap...")
            generate_heatmap(complete_corr, output_dir)
        else:
            print("\nSkipping heatmap: No complete-case data available.")
    elif plot and not HAS_PLOTTING:
        print("\nSkipping heatmap: 'seaborn' or 'matplotlib' not installed.")

    # Sort the standard (pairwise) correlation matrix
    correlation_matrix = correlation_matrix.sort_index(axis=0).sort_index(axis=1)
    output_file = os.path.join(output_dir, "correlation_matrix.csv")
    correlation_matrix.to_csv(output_file, sep=';', decimal=',')
    print(f"\nPairwise correlation matrix saved to {output_file} (European format)")

def generate_heatmap(df, output_dir):
    # Sort indicators alphabetically
    df = df.sort_index(axis=0).sort_index(axis=1)

    # Create a custom colormap: Red (-1.0) -> White (0.0) -> Green (1.0)
    colors = ["red", "white", "green"]
    cmap = mcolors.LinearSegmentedColormap.from_list("RdWhGn", colors)

    # Set the figure size
    fig, ax = plt.subplots(figsize=(16, 14))

    # Plot the heatmap
    sns.heatmap(df, 
                annot=True, 
                fmt=".2f", 
                cmap=cmap, 
                center=0,
                vmin=-1, 
                vmax=1,
                cbar_kws={'label': 'Correlation Coefficient'},
                square=True,
                ax=ax)

    # Show ticks on all sides
    ax.tick_params(top=True, bottom=True, left=True, right=True, labeltop=True, labelbottom=True, labelleft=True, labelright=True)
    plt.xticks(rotation=45)
    plt.yticks(rotation=0)

    plt.title('Stock Indicator Correlation Heatmap (Alphabetical & Symmetric)', pad=40)
    plt.tight_layout()

    # Save the plot
    heatmap_file = os.path.join(output_dir, "correlation_heatmap.png")
    plt.savefig(heatmap_file, dpi=300)
    print(f"Heatmap saved as {heatmap_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze correlations between stock indicators.')
    parser.add_argument('--input_dir', type=str, default='~/potentials/correlation/input',
                        help='Directory containing longi_*.csv files')
    parser.add_argument('--output_dir', type=str, default='~/potentials/correlation/output',
                        help='Directory to save the correlation matrix')
    parser.add_argument('--exclude', type=str, nargs='*', default=[],
                        help='List of indicators to exclude (e.g., per1y uptrend)')
    parser.add_argument('--no_plot', action='store_false', dest='plot',
                        help='Disable heatmap generation')
    
    args = parser.parse_args()
    analyze_correlations(args.input_dir, args.output_dir, args.exclude, args.plot)
