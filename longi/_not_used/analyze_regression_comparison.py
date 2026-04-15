#!/usr/bin/env python3
"""
Regression Comparison: Native vs Decile, Single vs Interaction
Creates summary table comparing all 4 scenarios.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import statsmodels.api as sm
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

DECILES_FILE = OUTPUT_DIR / "aux_deciles.csv"


def load_decile_boundaries(filepath: Path) -> dict:
    df = pd.read_csv(filepath, sep=';', decimal=',')
    boundaries = {}
    for indicator in df['Indicator'].unique():
        ind_data = df[df['Indicator'] == indicator].sort_values('Decile')
        boundaries[indicator] = [
            (int(row['Decile']), float(row['LowerLimit']), float(row['UpperLimit']))
            for _, row in ind_data.iterrows()
        ]
    return boundaries


def value_to_decile(value: float, boundaries: list) -> int:
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
    return pd.read_csv(filepath, sep=';', decimal=',', index_col=0, low_memory=False)


def flatten_data(dfs: dict) -> pd.DataFrame:
    common_tickers = set(dfs[list(dfs.keys())[0]].index)
    common_daynums = set(dfs[list(dfs.keys())[0]].columns)
    for name, df in dfs.items():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)
    common_tickers = sorted(common_tickers)
    common_daynums = sorted(common_daynums, reverse=True)

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
    return pd.DataFrame(rows)


def convert_to_deciles(data: pd.DataFrame, x_cols: list, boundaries: dict) -> pd.DataFrame:
    data_deciles = data.copy()
    for col in x_cols:
        if col in boundaries:
            data_deciles[col] = data[col].apply(lambda v: value_to_decile(v, boundaries[col]))
    return data_deciles


def create_interactions(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data['spr100d_x_vola100d'] = data['spr100d'] * data['vola100d']
    data['spr100d_x_vola20d'] = data['spr100d'] * data['vola20d']
    data['spr250d_x_vola100d'] = data['spr250d'] * data['vola100d']
    data['spr250d_x_vola20d'] = data['spr250d'] * data['vola20d']
    data['spr100d_x_spr250d'] = data['spr100d'] * data['spr250d']
    data['vola20d_x_vola100d'] = data['vola20d'] * data['vola100d']
    return data


def run_regression(data: pd.DataFrame, x_cols: list, y_col: str) -> dict:
    X = data[x_cols].copy()
    y = data[y_col].copy()
    mask = ~(X.isna().any(axis=1) | y.isna() | np.isinf(X).any(axis=1) | np.isinf(y))
    X = X[mask]
    y = y[mask]
    X_const = sm.add_constant(X)
    model = sm.OLS(y, X_const).fit()

    return {
        "n_obs": len(y),
        "r_squared": model.rsquared,
        "coefficients": model.params.to_dict(),
        "pvalues": model.pvalues.to_dict(),
    }


def sig_marker(pval):
    if pval < 0.001:
        return "***"
    elif pval < 0.01:
        return "**"
    elif pval < 0.05:
        return "*"
    else:
        return ""


def main():
    print("Loading data...")
    boundaries = load_decile_boundaries(DECILES_FILE)
    x_dfs = {name: load_longi_csv(path) for name, path in X_FILES.items() if path.exists()}
    y_dfs = {name: load_longi_csv(path) for name, path in Y_FILES.items() if path.exists()}
    all_dfs = {**x_dfs, **y_dfs}
    data_native = flatten_data(all_dfs)
    print(f"Observations: {len(data_native)}")

    # Create all 4 data variants
    data_native_interact = create_interactions(data_native)
    data_decile = convert_to_deciles(data_native, X_INDICATORS, boundaries)
    data_decile_interact = create_interactions(data_decile)

    x_cols_base = X_INDICATORS
    x_cols_interact = X_INDICATORS + [
        'spr100d_x_vola100d', 'spr100d_x_vola20d',
        'spr250d_x_vola100d', 'spr250d_x_vola20d',
        'spr100d_x_spr250d', 'vola20d_x_vola100d'
    ]

    # Run all 8 regressions (4 scenarios x 2 Y variables)
    results = {}
    for y_col in Y_FILES.keys():
        results[(y_col, 'native', 'single')] = run_regression(data_native, x_cols_base, y_col)
        results[(y_col, 'native', 'interact')] = run_regression(data_native_interact, x_cols_interact, y_col)
        results[(y_col, 'decile', 'single')] = run_regression(data_decile, x_cols_base, y_col)
        results[(y_col, 'decile', 'interact')] = run_regression(data_decile_interact, x_cols_interact, y_col)

    # Print comparison tables
    print("\n" + "=" * 90)
    print("REGRESSION COMPARISON: NATIVE vs DECILE, SINGLE vs INTERACTION")
    print("=" * 90)

    # R-squared comparison
    print("\n--- R-SQUARED COMPARISON ---")
    print(f"{'Y Variable':<18} {'Native Single':>15} {'Native Interact':>17} {'Decile Single':>15} {'Decile Interact':>17}")
    print("-" * 90)
    for y_col in Y_FILES.keys():
        r2_ns = results[(y_col, 'native', 'single')]['r_squared']
        r2_ni = results[(y_col, 'native', 'interact')]['r_squared']
        r2_ds = results[(y_col, 'decile', 'single')]['r_squared']
        r2_di = results[(y_col, 'decile', 'interact')]['r_squared']
        print(f"{y_col:<18} {r2_ns:>14.4f} {r2_ni:>17.4f} {r2_ds:>15.4f} {r2_di:>17.4f}")

    # Main effects significance table
    for y_col in Y_FILES.keys():
        print(f"\n--- {y_col.upper()}: MAIN EFFECTS ---")
        print(f"{'Variable':<12} {'Native Single':>15} {'Native Interact':>17} {'Decile Single':>15} {'Decile Interact':>17}")
        print("-" * 90)

        for var in X_INDICATORS:
            row = f"{var:<12}"
            for scenario in [('native', 'single'), ('native', 'interact'), ('decile', 'single'), ('decile', 'interact')]:
                r = results[(y_col, scenario[0], scenario[1])]
                coef = r['coefficients'].get(var, 0)
                pval = r['pvalues'].get(var, 1)
                sig = sig_marker(pval)
                row += f" {coef:>11.4f}{sig:<4}"
            print(row)

    # Interaction effects significance table
    interaction_cols = [
        'spr100d_x_vola100d', 'spr100d_x_vola20d',
        'spr250d_x_vola100d', 'spr250d_x_vola20d',
        'spr100d_x_spr250d', 'vola20d_x_vola100d'
    ]

    for y_col in Y_FILES.keys():
        print(f"\n--- {y_col.upper()}: INTERACTION EFFECTS ---")
        print(f"{'Interaction':<22} {'Native Interact':>20} {'Decile Interact':>20}")
        print("-" * 65)

        for var in interaction_cols:
            row = f"{var:<22}"
            for scenario in [('native', 'interact'), ('decile', 'interact')]:
                r = results[(y_col, scenario[0], scenario[1])]
                coef = r['coefficients'].get(var, 0)
                pval = r['pvalues'].get(var, 1)
                sig = sig_marker(pval)
                row += f" {coef:>16.6f}{sig:<4}"
            print(row)

    # Summary interpretation
    print("\n" + "=" * 90)
    print("SIGNIFICANCE LEGEND: *** p<0.001, ** p<0.01, * p<0.05")
    print("=" * 90)

    print("\nKEY OBSERVATIONS:")
    print("-" * 50)

    # Find strongest predictors per scenario
    for y_col in Y_FILES.keys():
        print(f"\n{y_col}:")
        for data_type in ['native', 'decile']:
            r_single = results[(y_col, data_type, 'single')]
            r_interact = results[(y_col, data_type, 'interact')]
            r2_gain = (r_interact['r_squared'] - r_single['r_squared']) / r_single['r_squared'] * 100

            # Find most significant main effect
            best_var = max(X_INDICATORS, key=lambda v: abs(r_single['coefficients'].get(v, 0)))
            best_coef = r_single['coefficients'].get(best_var, 0)
            best_sig = sig_marker(r_single['pvalues'].get(best_var, 1))

            print(f"  {data_type.capitalize():7}: R2 single={r_single['r_squared']:.4f}, "
                  f"R2 interact={r_interact['r_squared']:.4f} ({r2_gain:+.1f}%), "
                  f"Top predictor: {best_var} ({best_coef:+.4f}{best_sig})")


if __name__ == "__main__":
    main()
