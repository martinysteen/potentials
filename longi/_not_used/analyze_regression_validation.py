#!/usr/bin/env python3
"""
Regression Validation: Compare predicted vs actual gains
For each of the 10 most recent daynums, show top 10 stocks by predicted gain
and compare to actual outcomes.
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

# Model variables (dropping spr250d as it adds nothing)
X_VARS = ["spr100d", "vola20d", "vola100d"]
X_FILES = {name: OUTPUT_DIR / f"longi_{name}.csv" for name in X_VARS}

# Target variable
Y_VAR = "future_gain50d"  # 50d has better R2
Y_FILE = OUTPUT_DIR / f"{Y_VAR}.csv"


def load_longi_csv(filepath: Path) -> pd.DataFrame:
    return pd.read_csv(filepath, sep=';', decimal=',', index_col=0, low_memory=False)


def main():
    print("Loading data...")
    x_dfs = {name: load_longi_csv(path) for name, path in X_FILES.items()}
    y_df = load_longi_csv(Y_FILE)

    # Get common tickers and daynums
    common_tickers = set(y_df.index)
    common_daynums = set(y_df.columns)
    for df in x_dfs.values():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    # Sort daynums (newest first - they are strings like "2009", "2008", etc.)
    all_daynums = sorted(common_daynums, key=lambda x: int(x), reverse=True)
    recent_daynums = all_daynums[:10]

    print(f"Tickers: {len(common_tickers)}, Total daynums: {len(all_daynums)}")
    print(f"Most recent 10 daynums: {recent_daynums}")

    # Build full dataset for model fitting (exclude recent 10 for cleaner validation)
    print("\nBuilding training dataset (excluding recent 10 daynums)...")
    train_daynums = all_daynums[10:]  # All except recent 10

    rows = []
    for ticker in common_tickers:
        for daynum in train_daynums:
            row = {"ticker": ticker, "daynum": daynum}
            valid = True
            for name, df in x_dfs.items():
                try:
                    val = df.loc[ticker, daynum]
                    if pd.isna(val) or val == '':
                        valid = False
                        break
                    row[name] = float(str(val).replace(',', '.')) if isinstance(val, str) else float(val)
                except:
                    valid = False
                    break
            if valid:
                try:
                    y_val = y_df.loc[ticker, daynum]
                    if pd.isna(y_val) or y_val == '':
                        valid = False
                    else:
                        row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
                except:
                    valid = False
            if valid:
                rows.append(row)

    train_data = pd.DataFrame(rows)
    print(f"Training observations: {len(train_data)}")

    # Fit model
    X_train = train_data[X_VARS]
    y_train = train_data[Y_VAR]
    mask = ~(X_train.isna().any(axis=1) | y_train.isna() | np.isinf(X_train).any(axis=1) | np.isinf(y_train))
    X_train = X_train[mask]
    y_train = y_train[mask]

    X_train_const = sm.add_constant(X_train)
    model = sm.OLS(y_train, X_train_const).fit()

    print(f"\nModel fitted: R2={model.rsquared:.4f}")
    print("Coefficients:")
    for var in ['const'] + X_VARS:
        print(f"  {var}: {model.params[var]:.4f}")

    # Validate on recent daynums
    print("\n" + "=" * 100)
    print("VALIDATION: TOP 10 STOCKS BY PREDICTED GAIN vs ACTUAL")
    print("=" * 100)

    all_predictions = []

    for daynum in recent_daynums:
        print(f"\n--- Daynum {daynum} ---")

        # Get all stocks for this daynum
        day_rows = []
        for ticker in common_tickers:
            row = {"ticker": ticker, "daynum": daynum}
            valid = True
            for name, df in x_dfs.items():
                try:
                    val = df.loc[ticker, daynum]
                    if pd.isna(val) or val == '':
                        valid = False
                        break
                    row[name] = float(str(val).replace(',', '.')) if isinstance(val, str) else float(val)
                except:
                    valid = False
                    break
            if valid:
                try:
                    y_val = y_df.loc[ticker, daynum]
                    if pd.isna(y_val) or y_val == '':
                        row[Y_VAR] = np.nan  # Missing actual - still include for prediction
                    else:
                        row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
                except:
                    row[Y_VAR] = np.nan
                day_rows.append(row)

        if not day_rows:
            print("  No valid data")
            continue

        day_df = pd.DataFrame(day_rows)

        # Predict
        X_day = day_df[X_VARS]
        X_day_const = sm.add_constant(X_day, has_constant='add')
        day_df['predicted'] = model.predict(X_day_const)

        # Sort by predicted gain (descending)
        day_df_sorted = day_df.sort_values('predicted', ascending=False)

        # Top 10
        top10 = day_df_sorted.head(10)

        print(f"{'Rank':<5} {'Ticker':<10} {'Predicted':>10} {'Actual':>10} {'Diff':>10} {'spr100d':>10} {'vola20d':>10} {'vola100d':>10}")
        print("-" * 95)

        for i, (_, row) in enumerate(top10.iterrows(), 1):
            pred = row['predicted']
            actual = row[Y_VAR]
            diff = actual - pred if not pd.isna(actual) else np.nan
            actual_str = f"{actual:.2f}" if not pd.isna(actual) else "N/A"
            diff_str = f"{diff:+.2f}" if not pd.isna(diff) else "N/A"

            print(f"{i:<5} {row['ticker']:<10} {pred:>10.2f} {actual_str:>10} {diff_str:>10} "
                  f"{row['spr100d']:>10.1f} {row['vola20d']:>10.2f} {row['vola100d']:>10.2f}")

            all_predictions.append({
                'daynum': daynum,
                'rank': i,
                'ticker': row['ticker'],
                'predicted': pred,
                'actual': actual,
            })

        # Summary stats for this daynum
        valid_top10 = top10[~top10[Y_VAR].isna()]
        if len(valid_top10) > 0:
            avg_pred = valid_top10['predicted'].mean()
            avg_actual = valid_top10[Y_VAR].mean()
            correlation = valid_top10['predicted'].corr(valid_top10[Y_VAR])
            print(f"\n  Top 10 avg predicted: {avg_pred:.2f}, avg actual: {avg_actual:.2f}, corr: {correlation:.3f}")

    # Overall summary
    print("\n" + "=" * 100)
    print("OVERALL SUMMARY")
    print("=" * 100)

    pred_df = pd.DataFrame(all_predictions)
    valid_pred = pred_df[~pred_df['actual'].isna()]

    if len(valid_pred) > 0:
        overall_corr = valid_pred['predicted'].corr(valid_pred['actual'])
        avg_pred = valid_pred['predicted'].mean()
        avg_actual = valid_pred['actual'].mean()
        hit_rate = (valid_pred['actual'] > 0).mean() * 100

        print(f"Total top-10 picks across 10 daynums: {len(valid_pred)}")
        print(f"Avg predicted gain: {avg_pred:.2f}%")
        print(f"Avg actual gain: {avg_actual:.2f}%")
        print(f"Correlation (pred vs actual): {overall_corr:.3f}")
        print(f"Hit rate (actual > 0): {hit_rate:.1f}%")

        # Compare to random baseline
        print("\nBenchmark comparison:")
        # Get avg gain across all stocks for these daynums
        all_gains = []
        for daynum in recent_daynums:
            for ticker in common_tickers:
                try:
                    val = y_df.loc[ticker, daynum]
                    if not pd.isna(val) and val != '':
                        all_gains.append(float(str(val).replace(',', '.')) if isinstance(val, str) else float(val))
                except:
                    pass

        if all_gains:
            market_avg = np.mean(all_gains)
            market_hit = (np.array(all_gains) > 0).mean() * 100
            print(f"  Market avg gain (all stocks): {market_avg:.2f}%")
            print(f"  Market hit rate: {market_hit:.1f}%")
            print(f"  Model outperformance: {avg_actual - market_avg:+.2f}%")


if __name__ == "__main__":
    main()
