#!/usr/bin/env python3
"""
Regression Analysis using Deciles: Which factors predict future gains?
Converts spr100d, spr250d, vola20d, vola100d to deciles (1-10) using aux_deciles.csv
before analyzing against future_gain20d and future_gain50d.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# Paths
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "output"

# Independent variables (X)
X_INDICATORS = ["spr100d", "spr250d", "vola20d", "vola100d"]
X_FILES = {name: OUTPUT_DIR / f"longi_{name}.csv" for name in X_INDICATORS}

# Dependent variables (Y)
Y_FILES = {
    "future_gain20d": OUTPUT_DIR / "future_gain20d.csv",
    "future_gain50d": OUTPUT_DIR / "future_gain50d.csv",
}

# Decile boundaries
DECILES_FILE = OUTPUT_DIR / "aux_deciles.csv"


def load_decile_boundaries(filepath: Path) -> dict[str, list[tuple[int, float, float]]]:
    """Load decile boundaries from aux_deciles.csv."""
    df = pd.read_csv(filepath, sep=';', decimal=',')

    boundaries = {}
    for indicator in df['Indicator'].unique():
        ind_data = df[df['Indicator'] == indicator].sort_values('Decile')
        boundaries[indicator] = [
            (int(row['Decile']), float(row['LowerLimit']), float(row['UpperLimit']))
            for _, row in ind_data.iterrows()
        ]
    return boundaries


def value_to_decile(value: float, boundaries: list[tuple[int, float, float]]) -> int:
    """Convert a value to its decile (1-10) based on boundaries."""
    if pd.isna(value):
        return np.nan

    for decile, lower, upper in boundaries:
        if decile == 1 and value <= upper:
            return 1
        elif decile == 10 and value >= lower:
            return 10
        elif lower <= value < upper:
            return decile

    # Edge case: if value exactly equals the upper boundary of decile 10
    return 10


def load_longi_csv(filepath: Path) -> pd.DataFrame:
    """Load a longi-style CSV file (European format, ticker as first column)."""
    df = pd.read_csv(filepath, sep=';', decimal=',', index_col=0, low_memory=False)
    return df


def flatten_data(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Flatten multiple dataframes into a single long-format dataframe.
    Each row = (ticker, daynum) observation with all indicators as columns.
    """
    # Get common tickers and daynums across all dataframes
    common_tickers = set(dfs[list(dfs.keys())[0]].index)
    common_daynums = set(dfs[list(dfs.keys())[0]].columns)

    for name, df in dfs.items():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    common_tickers = sorted(common_tickers)
    common_daynums = sorted(common_daynums, reverse=True)  # newest first

    print(f"Common tickers: {len(common_tickers)}")
    print(f"Common daynums: {len(common_daynums)}")

    # Build flattened data
    rows = []
    for ticker in common_tickers:
        for daynum in common_daynums:
            row = {"ticker": ticker, "daynum": daynum}
            valid = True
            for name, df in dfs.items():
                try:
                    val = df.loc[ticker, daynum]
                    if pd.isna(val) or val == '':
                        valid = False
                        break
                    row[name] = float(str(val).replace(',', '.')) if isinstance(val, str) else float(val)
                except (KeyError, ValueError):
                    valid = False
                    break
            if valid:
                rows.append(row)

    result = pd.DataFrame(rows)
    print(f"Valid observations: {len(result)}")
    return result


def convert_to_deciles(data: pd.DataFrame, x_cols: list[str],
                       boundaries: dict[str, list[tuple[int, float, float]]]) -> pd.DataFrame:
    """Convert X columns from raw values to deciles."""
    data_deciles = data.copy()

    for col in x_cols:
        if col in boundaries:
            col_boundaries = boundaries[col]
            data_deciles[col] = data[col].apply(lambda v: value_to_decile(v, col_boundaries))
            print(f"  {col}: converted to deciles (range: {data_deciles[col].min():.0f}-{data_deciles[col].max():.0f})")
        else:
            print(f"  WARNING: No decile boundaries found for {col}")

    return data_deciles


def run_regression(data: pd.DataFrame, x_cols: list[str], y_col: str) -> dict:
    """
    Run OLS regression and return results.
    """
    # Prepare data
    X = data[x_cols].copy()
    y = data[y_col].copy()

    # Remove any remaining NaN/inf
    mask = ~(X.isna().any(axis=1) | y.isna() | np.isinf(X).any(axis=1) | np.isinf(y))
    X = X[mask]
    y = y[mask]

    print(f"\n{'='*60}")
    print(f"Regression: {y_col}")
    print(f"{'='*60}")
    print(f"Observations: {len(y)}")

    # Add constant for intercept
    X_const = sm.add_constant(X)

    # Fit OLS model
    model = sm.OLS(y, X_const).fit()

    # Print summary
    print(f"\nR-squared: {model.rsquared:.4f}")
    print(f"Adjusted R-squared: {model.rsquared_adj:.4f}")
    print(f"F-statistic: {model.fvalue:.2f} (p-value: {model.f_pvalue:.2e})")

    print("\nCoefficients:")
    print("-" * 50)
    print(f"{'Variable':<15} {'Coef':>10} {'Std Err':>10} {'t-stat':>10} {'P>|t|':>10}")
    print("-" * 50)

    for var in model.params.index:
        coef = model.params[var]
        stderr = model.bse[var]
        tstat = model.tvalues[var]
        pval = model.pvalues[var]
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"{var:<15} {coef:>10.4f} {stderr:>10.4f} {tstat:>10.2f} {pval:>10.4f} {sig}")

    # Standardized coefficients (beta weights) for comparison
    print("\nStandardized Coefficients (Beta weights):")
    print("-" * 40)
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns, index=X.index)
    y_scaled = (y - y.mean()) / y.std()
    X_scaled_const = sm.add_constant(X_scaled)
    model_std = sm.OLS(y_scaled, X_scaled_const).fit()

    for var in x_cols:
        beta = model_std.params[var]
        print(f"{var:<15} {beta:>10.4f}")

    return {
        "y_col": y_col,
        "n_obs": len(y),
        "r_squared": model.rsquared,
        "adj_r_squared": model.rsquared_adj,
        "f_stat": model.fvalue,
        "f_pvalue": model.f_pvalue,
        "coefficients": model.params.to_dict(),
        "pvalues": model.pvalues.to_dict(),
        "std_coefficients": {var: model_std.params[var] for var in x_cols},
    }


def compare_results(results: list[dict]):
    """Compare regression results across different dependent variables."""
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY (DECILE-BASED)")
    print("=" * 70)

    x_cols = [k for k in results[0]["std_coefficients"].keys()]

    print(f"\n{'Metric':<20}", end="")
    for r in results:
        print(f"{r['y_col']:>20}", end="")
    print()
    print("-" * (20 + 20 * len(results)))

    print(f"{'R-squared':<20}", end="")
    for r in results:
        print(f"{r['r_squared']:>20.4f}", end="")
    print()

    print(f"{'Adj. R-squared':<20}", end="")
    for r in results:
        print(f"{r['adj_r_squared']:>20.4f}", end="")
    print()

    print(f"{'F-statistic':<20}", end="")
    for r in results:
        print(f"{r['f_stat']:>20.2f}", end="")
    print()

    print(f"\n{'Standardized Coefficients (importance):'}")
    print("-" * (20 + 20 * len(results)))

    for var in x_cols:
        print(f"{var:<20}", end="")
        for r in results:
            val = r['std_coefficients'][var]
            print(f"{val:>20.4f}", end="")
        print()

    # Rank predictors by absolute beta weight
    print(f"\n{'Predictor Ranking by |Beta|:'}")
    print("-" * 50)

    for r in results:
        print(f"\n{r['y_col']}:")
        sorted_vars = sorted(x_cols, key=lambda x: abs(r['std_coefficients'][x]), reverse=True)
        for i, var in enumerate(sorted_vars, 1):
            beta = r['std_coefficients'][var]
            sig = r['pvalues'].get(var, 1)
            sig_marker = "***" if sig < 0.001 else "**" if sig < 0.01 else "*" if sig < 0.05 else ""
            print(f"  {i}. {var:<15} Beta={beta:>8.4f} {sig_marker}")

    # Interpretation for deciles
    print("\n" + "-" * 50)
    print("Coefficient Interpretation (per decile increase):")
    for r in results:
        print(f"\n{r['y_col']}:")
        for var in x_cols:
            coef = r['coefficients'][var]
            print(f"  {var}: +1 decile → {coef:+.3f}% change in future gain")


def main():
    print("="*70)
    print("REGRESSION ANALYSIS WITH DECILE-TRANSFORMED X-VALUES")
    print("="*70)

    print("\nLoading decile boundaries...")
    boundaries = load_decile_boundaries(DECILES_FILE)
    print(f"  Loaded boundaries for {len(boundaries)} indicators")

    print("\nLoading data files...")

    # Load X variables
    x_dfs = {}
    for name, path in X_FILES.items():
        if path.exists():
            x_dfs[name] = load_longi_csv(path)
            print(f"  Loaded {name}: {x_dfs[name].shape}")
        else:
            print(f"  WARNING: {path} not found")
            return

    # Load Y variables
    y_dfs = {}
    for name, path in Y_FILES.items():
        if path.exists():
            y_dfs[name] = load_longi_csv(path)
            print(f"  Loaded {name}: {y_dfs[name].shape}")
        else:
            print(f"  WARNING: {path} not found")
            return

    # Combine all dataframes for flattening
    all_dfs = {**x_dfs, **y_dfs}

    # Flatten to long format
    print("\nFlattening data...")
    data = flatten_data(all_dfs)

    if len(data) == 0:
        print("ERROR: No valid observations found")
        return

    # Convert X variables to deciles
    print("\nConverting X variables to deciles...")
    x_cols = list(x_dfs.keys())
    data_deciles = convert_to_deciles(data, x_cols, boundaries)

    # Summary statistics for decile-transformed data
    print("\nDescriptive Statistics (Decile-transformed X):")
    print(data_deciles[x_cols + list(y_dfs.keys())].describe().round(4))

    # Verify decile distribution
    print("\nDecile Distribution Check:")
    for col in x_cols:
        print(f"  {col}: {data_deciles[col].value_counts().sort_index().to_dict()}")

    # Run regressions with decile data
    results = []

    for y_col in y_dfs.keys():
        result = run_regression(data_deciles, x_cols, y_col)
        results.append(result)

    # Compare results
    compare_results(results)

    print("\n" + "=" * 70)
    print("INTERPRETATION GUIDE (DECILE MODEL)")
    print("=" * 70)
    print("""
- X-variables are now integers 1-10 (deciles)
- Decile 1 = lowest 10% of values, Decile 10 = highest 10%
- Coefficients show the effect of moving up one decile
- Standardized coefficients (Beta) show relative importance

Key advantages of decile approach:
1. Robust to outliers
2. Easier interpretation (e.g., "moving from decile 5 to 6")
3. Captures non-linear relationships better than raw values
4. All predictors on same scale (1-10)
""")


if __name__ == "__main__":
    main()
