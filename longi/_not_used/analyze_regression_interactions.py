#!/usr/bin/env python3
"""
Regression Analysis with Interactions: Testing spread x volatility effects
Uses deciles (1-10) and adds interaction terms.
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
    return 10


def load_longi_csv(filepath: Path) -> pd.DataFrame:
    """Load a longi-style CSV file."""
    return pd.read_csv(filepath, sep=';', decimal=',', index_col=0, low_memory=False)


def flatten_data(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Flatten multiple dataframes into long format."""
    common_tickers = set(dfs[list(dfs.keys())[0]].index)
    common_daynums = set(dfs[list(dfs.keys())[0]].columns)

    for name, df in dfs.items():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    common_tickers = sorted(common_tickers)
    common_daynums = sorted(common_daynums, reverse=True)

    print(f"Common tickers: {len(common_tickers)}, daynums: {len(common_daynums)}")

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
            data_deciles[col] = data[col].apply(lambda v: value_to_decile(v, boundaries[col]))
    return data_deciles


def create_interaction_terms(data: pd.DataFrame) -> pd.DataFrame:
    """Create interaction terms between spread and volatility measures."""
    data = data.copy()

    # Main interactions: spread x volatility
    data['spr100d_x_vola100d'] = data['spr100d'] * data['vola100d']
    data['spr100d_x_vola20d'] = data['spr100d'] * data['vola20d']
    data['spr250d_x_vola100d'] = data['spr250d'] * data['vola100d']
    data['spr250d_x_vola20d'] = data['spr250d'] * data['vola20d']

    # Within-category interactions
    data['spr100d_x_spr250d'] = data['spr100d'] * data['spr250d']
    data['vola20d_x_vola100d'] = data['vola20d'] * data['vola100d']

    return data


def run_regression(data: pd.DataFrame, x_cols: list[str], y_col: str, model_name: str) -> dict:
    """Run OLS regression and return results."""
    X = data[x_cols].copy()
    y = data[y_col].copy()

    mask = ~(X.isna().any(axis=1) | y.isna() | np.isinf(X).any(axis=1) | np.isinf(y))
    X = X[mask]
    y = y[mask]

    print(f"\n{'='*65}")
    print(f"{model_name}: {y_col}")
    print(f"{'='*65}")
    print(f"Observations: {len(y)}, Predictors: {len(x_cols)}")

    X_const = sm.add_constant(X)
    model = sm.OLS(y, X_const).fit()

    print(f"\nR-squared: {model.rsquared:.4f}")
    print(f"Adjusted R-squared: {model.rsquared_adj:.4f}")
    print(f"F-statistic: {model.fvalue:.2f}")

    print("\nCoefficients:")
    print("-" * 65)
    print(f"{'Variable':<25} {'Coef':>10} {'t-stat':>10} {'P>|t|':>10} {'Sig':<5}")
    print("-" * 65)

    for var in model.params.index:
        coef = model.params[var]
        tstat = model.tvalues[var]
        pval = model.pvalues[var]
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
        print(f"{var:<25} {coef:>10.4f} {tstat:>10.2f} {pval:>10.4f} {sig:<5}")

    # Standardized coefficients
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns, index=X.index)
    y_scaled = (y - y.mean()) / y.std()
    X_scaled_const = sm.add_constant(X_scaled)
    model_std = sm.OLS(y_scaled, X_scaled_const).fit()

    return {
        "model_name": model_name,
        "y_col": y_col,
        "n_obs": len(y),
        "n_predictors": len(x_cols),
        "r_squared": model.rsquared,
        "adj_r_squared": model.rsquared_adj,
        "coefficients": model.params.to_dict(),
        "pvalues": model.pvalues.to_dict(),
        "std_coefficients": {var: model_std.params[var] for var in x_cols},
    }


def compare_models(results_base: list[dict], results_interact: list[dict]):
    """Compare base model vs interaction model."""
    print("\n" + "=" * 70)
    print("MODEL COMPARISON: Base vs Interactions")
    print("=" * 70)

    for base, interact in zip(results_base, results_interact):
        y_col = base['y_col']
        r2_base = base['r_squared']
        r2_int = interact['r_squared']
        r2_gain = (r2_int - r2_base) / r2_base * 100

        print(f"\n{y_col}:")
        print(f"  Base model R2:        {r2_base:.4f} ({base['n_predictors']} predictors)")
        print(f"  Interaction model R2: {r2_int:.4f} ({interact['n_predictors']} predictors)")
        print(f"  R2 improvement:       {r2_gain:+.1f}%")


def print_interaction_summary(results: list[dict]):
    """Summarize which interactions matter."""
    print("\n" + "=" * 70)
    print("INTERACTION EFFECTS SUMMARY")
    print("=" * 70)

    interactions = [
        'spr100d_x_vola100d', 'spr100d_x_vola20d',
        'spr250d_x_vola100d', 'spr250d_x_vola20d',
        'spr100d_x_spr250d', 'vola20d_x_vola100d'
    ]

    print(f"\n{'Interaction':<25} {'20d Coef':>12} {'20d Sig':>8} {'50d Coef':>12} {'50d Sig':>8}")
    print("-" * 70)

    for inter in interactions:
        row = f"{inter:<25}"
        for r in results:
            coef = r['coefficients'].get(inter, 0)
            pval = r['pvalues'].get(inter, 1)
            sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
            row += f" {coef:>12.4f} {sig:>8}"
        print(row)

    print("\n" + "-" * 70)
    print("Interpretation of significant interactions:")
    print("-" * 70)

    for r in results:
        print(f"\n{r['y_col']}:")
        sig_interactions = []
        for inter in interactions:
            pval = r['pvalues'].get(inter, 1)
            coef = r['coefficients'].get(inter, 0)
            if pval < 0.05:
                direction = "positive" if coef > 0 else "negative"
                sig_interactions.append((inter, coef, direction))

        if sig_interactions:
            for inter, coef, direction in sorted(sig_interactions, key=lambda x: abs(x[1]), reverse=True):
                parts = inter.split('_x_')
                print(f"  {parts[0]} x {parts[1]}: {direction} ({coef:+.4f})")
                if direction == "positive":
                    print(f"    -> High {parts[0]} + High {parts[1]} = EXTRA boost to gains")
                else:
                    print(f"    -> High {parts[0]} + High {parts[1]} = REDUCES gain effect")
        else:
            print("  No significant interactions")


def main():
    print("=" * 70)
    print("REGRESSION WITH INTERACTION TERMS")
    print("=" * 70)

    # Load data
    print("\nLoading data...")
    boundaries = load_decile_boundaries(DECILES_FILE)

    x_dfs = {name: load_longi_csv(path) for name, path in X_FILES.items() if path.exists()}
    y_dfs = {name: load_longi_csv(path) for name, path in Y_FILES.items() if path.exists()}

    all_dfs = {**x_dfs, **y_dfs}
    data = flatten_data(all_dfs)

    if len(data) == 0:
        print("ERROR: No valid observations")
        return

    # Convert to deciles
    print("\nConverting to deciles...")
    x_cols_base = list(x_dfs.keys())
    data = convert_to_deciles(data, x_cols_base, boundaries)

    # Create interaction terms
    print("Creating interaction terms...")
    data = create_interaction_terms(data)

    interaction_cols = [
        'spr100d_x_vola100d', 'spr100d_x_vola20d',
        'spr250d_x_vola100d', 'spr250d_x_vola20d',
        'spr100d_x_spr250d', 'vola20d_x_vola100d'
    ]
    x_cols_full = x_cols_base + interaction_cols

    # Run base models (no interactions)
    print("\n" + "=" * 70)
    print("BASE MODELS (Main effects only)")
    print("=" * 70)

    results_base = []
    for y_col in y_dfs.keys():
        result = run_regression(data, x_cols_base, y_col, "Base Model")
        results_base.append(result)

    # Run interaction models
    print("\n" + "=" * 70)
    print("INTERACTION MODELS (Main effects + Interactions)")
    print("=" * 70)

    results_interact = []
    for y_col in y_dfs.keys():
        result = run_regression(data, x_cols_full, y_col, "Interaction Model")
        results_interact.append(result)

    # Compare models
    compare_models(results_base, results_interact)

    # Summarize interactions
    print_interaction_summary(results_interact)

    # Final interpretation
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    print("""
Interaction interpretation guide:
- Positive interaction: the two factors AMPLIFY each other's effect
  Example: spr100d_x_vola100d > 0 means high spread + high volatility
           together predict HIGHER gains than sum of individual effects

- Negative interaction: the two factors DAMPEN each other's effect
  Example: spr100d_x_vola100d < 0 means high spread + high volatility
           together predict LOWER gains than sum of individual effects

Practical implication:
- If spr100d_x_vola100d is positive: look for stocks that are BOTH
  far from highs AND volatile (contrarian + momentum combination)
- If negative: the combination is less valuable than either alone
""")


if __name__ == "__main__":
    main()
