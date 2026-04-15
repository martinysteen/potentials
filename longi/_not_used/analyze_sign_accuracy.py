#!/usr/bin/env python3
"""
Sign Accuracy Test: For each day, predict ALL filtered stocks and count correct signs.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import statsmodels.api as sm
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = Path(__file__).parent.parent / 'output'

# Filter configuration - try different combinations:
# Option 1: All three variables (aggressive, ~40-50% excluded with decile)
# FILTER_VARS = ['spr100d', 'vola20d', 'vola100d']
# Option 2: Just spr100d (gentler, main "falling knife" indicator)
FILTER_VARS = ['spr100d']
# Option 3: No filtering
# FILTER_VARS = []

X_VARS = {
    'ma20': 'longi_ma20.csv',
    'ma50': 'longi_ma50.csv',
    'macd_signal': 'longi_macd_signal.csv',
    'median_20d': 'longi_median_20d.csv',
    'median_50d': 'longi_median_50d.csv',
    'PdivMA20': 'longi_PdivMA20.csv',
    'PdivMA50': 'longi_PdivMA50.csv',
    'per1w': 'longi_per1w.csv',
    'per1m': 'longi_per1m.csv',
    'per3m': 'longi_per3m.csv',
    'rsi': 'longi_rsi.csv',
    'sh3m': 'longi_sh3m.csv',
    'spr100d': 'longi_spr100d.csv',
    'vola20d': 'longi_vola20d.csv',
    'vola100d': 'longi_vola100d.csv',
}

Y_VAR = 'future_gain50d'  # 50d has much better predictive power than 20d
print(f'Y_VAR: {Y_VAR}')
print(f'FILTER_VARS: {FILTER_VARS}')
VARIANCE_THRESHOLD = 0.90
TEST_DAYS = 5  # Number of test days

# Filtering method: 'decile' or 'sigma' (only matters if FILTER_VARS is not empty)
FILTER_METHOD = 'decile'  # 'decile' gave 70% on 50d; 'sigma' gave 66%
print(f'FILTER_METHOD: {FILTER_METHOD}')
SIGMA_THRESHOLD = 3
if FILTER_METHOD == 'sigma':
    print(f'SIGMA_THRESHOLD: {SIGMA_THRESHOLD}')

def load_csv(f):
    return pd.read_csv(OUTPUT_DIR / f, sep=';', decimal=',', index_col=0, low_memory=False)


def load_decile_boundaries():
    df = pd.read_csv(OUTPUT_DIR / 'aux_deciles.csv', sep=';', decimal=',')
    boundaries = {}
    for indicator in df['Indicator'].unique():
        ind_data = df[df['Indicator'] == indicator].sort_values('Decile')
        d10 = ind_data[ind_data['Decile'] == 10]
        if len(d10) > 0:
            boundaries[indicator] = float(d10['LowerLimit'].values[0])
    return boundaries


def main():
    print('=' * 70)
    print('SIGN ACCURACY TEST')
    print('=' * 70)

    # Load decile boundaries or prepare for sigma
    decile_bounds = {}
    filter_stats = {}  # Will be populated during training for sigma method

    if not FILTER_VARS:
        print('No filtering applied (FILTER_VARS is empty)')
    elif FILTER_METHOD == 'decile':
        decile_bounds = load_decile_boundaries()
        print(f'Filtering out decile 10 for: {FILTER_VARS}')
        for var in FILTER_VARS:
            if var in decile_bounds:
                print(f'  {var} >= {decile_bounds[var]:.2f}')
    else:
        print(f'Using {SIGMA_THRESHOLD}-sigma rule for: {FILTER_VARS}')

    # Load data
    print('\nLoading data...')
    x_dfs = {name: load_csv(filename) for name, filename in X_VARS.items()}
    y_df = load_csv(f'{Y_VAR}.csv')

    # Common tickers/daynums
    common_tickers = set(y_df.index)
    common_daynums = set(y_df.columns)
    for df in x_dfs.values():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    all_daynums = sorted(common_daynums, key=lambda x: int(x), reverse=True)

    # Data summary
    print(f'\nData loaded:')
    print(f'  Common tickers: {len(common_tickers)}')
    print(f'  Common daynums: {len(all_daynums)} (range: {all_daynums[-1]} to {all_daynums[0]})')

    # Find daynums with Y data and count stocks per daynum
    valid_daynums = []
    daynum_stock_counts = {}
    for dn in all_daynums:
        col = y_df[dn]
        non_empty = col.dropna()
        non_empty = non_empty[non_empty != '']
        count = len(non_empty)
        if count > 500:
            valid_daynums.append(dn)
            daynum_stock_counts[dn] = count

    print(f'  Daynums with Y data (>500 stocks): {len(valid_daynums)}')
    if valid_daynums:
        counts = list(daynum_stock_counts.values())
        print(f'  Stocks per daynum: min={min(counts)}, max={max(counts)}, avg={np.mean(counts):.0f}')

    # Sample test daynums: newest, middle, oldest (spread across time)
    # Or use every 20th daynum for broader coverage
    SAMPLE_MODE = 'every_n'  # 'spread' for 3 points, 'every_n' for every Nth
    print(f'\nSAMPLE_MODE: {SAMPLE_MODE}')
    EVERY_N = 20

    if SAMPLE_MODE == 'spread' and len(valid_daynums) >= 3:
        # Sample 3 points: newest, middle, oldest
        idx_newest = 0
        idx_middle = len(valid_daynums) // 2
        idx_oldest = len(valid_daynums) - 1
        test_daynums = [valid_daynums[idx_newest], valid_daynums[idx_middle], valid_daynums[idx_oldest]]
        train_daynums = [dn for dn in valid_daynums if dn not in test_daynums]
        print(f'\nTest sampling: 3 spread points (newest, middle, oldest)')
    elif SAMPLE_MODE == 'every_n':
        # Every Nth daynum
        test_daynums = valid_daynums[::EVERY_N]
        train_daynums = [dn for dn in valid_daynums if dn not in test_daynums]
        print(f'\nTest sampling: every {EVERY_N}th daynum')
    else:
        # Fallback: consecutive
        test_daynums = valid_daynums[:TEST_DAYS]
        train_daynums = valid_daynums[TEST_DAYS:]
        print(f'\nTest sampling: {TEST_DAYS} most recent consecutive')

    print(f'Test daynums ({len(test_daynums)}): {test_daynums}')
    print(f'Train daynums: {len(train_daynums)}')

    # Build training data (first without filtering to compute sigma if needed)
    print('\nBuilding training data...')
    rows = []
    x_names = list(x_dfs.keys())

    for ticker in common_tickers:
        for daynum in train_daynums:
            row = {'ticker': ticker, 'daynum': daynum}
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

            if not valid:
                continue

            try:
                y_val = y_df.loc[ticker, daynum]
                if pd.isna(y_val) or y_val == '':
                    continue
                row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
            except:
                continue

            rows.append(row)

    train_data_raw = pd.DataFrame(rows)
    print(f'Raw training observations: {len(train_data_raw):,}')

    # Compute sigma bounds if using sigma method
    if FILTER_METHOD == 'sigma' and FILTER_VARS:
        for var in FILTER_VARS:
            mean = train_data_raw[var].mean()
            std = train_data_raw[var].std()
            filter_stats[var] = {
                'mean': mean,
                'std': std,
                'upper': mean + SIGMA_THRESHOLD * std,
                'lower': mean - SIGMA_THRESHOLD * std
            }
            print(f'  {var}: mean={mean:.2f}, std={std:.2f}, bounds=[{filter_stats[var]["lower"]:.2f}, {filter_stats[var]["upper"]:.2f}]')

    # Apply filtering (skip if no filter vars)
    if FILTER_VARS:
        mask = pd.Series(True, index=train_data_raw.index)
        for var in FILTER_VARS:
            if FILTER_METHOD == 'decile':
                if var in decile_bounds:
                    mask = mask & (train_data_raw[var] < decile_bounds[var])
            else:
                mask = mask & (train_data_raw[var] >= filter_stats[var]['lower']) & (train_data_raw[var] <= filter_stats[var]['upper'])
        train_data = train_data_raw[mask].copy()
        excluded_pct = (1 - len(train_data) / len(train_data_raw)) * 100
        print(f'After filtering: {len(train_data):,} ({excluded_pct:.1f}% excluded)')
    else:
        train_data = train_data_raw.copy()
        print(f'No filtering: {len(train_data):,} observations')

    # Prepare and fit model
    X_train = train_data[x_names]
    y_train = train_data[Y_VAR]
    mask = ~(X_train.isna().any(axis=1) | y_train.isna() | np.isinf(X_train).any(axis=1) | np.isinf(y_train))
    X_train, y_train = X_train[mask], y_train[mask]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    pca = PCA()
    X_pca = pca.fit_transform(X_scaled)
    n_components = np.argmax(np.cumsum(pca.explained_variance_ratio_) >= VARIANCE_THRESHOLD) + 1

    X_pca_sel = X_pca[:, :n_components]
    X_pca_const = sm.add_constant(pd.DataFrame(X_pca_sel))
    model = sm.OLS(y_train.values, X_pca_const).fit()

    print(f'Model R²: {model.rsquared:.4f}, Components: {n_components}')

    # Show why predictions are always positive
    print(f'\nTraining Y stats: mean={y_train.mean():.2f}, std={y_train.std():.2f}, min={y_train.min():.1f}, max={y_train.max():.1f}')
    print(f'Model intercept (const): {model.params["const"]:.2f}')
    print(f'PC coefficient range: {model.params[1:].min():.2f} to {model.params[1:].max():.2f}')
    print(f'  -> Predictions ≈ {model.params["const"]:.1f} + small adjustments (hence always positive)')

    # Test each day
    print('\n' + '=' * 70)
    print('DAY-BY-DAY SIGN ACCURACY')
    print('=' * 70)

    print(f"\n{'Daynum':<8} {'N':>6} {'Acc%':>6} {'AvgAct':>7} | {'Top10%':>8} {'Bot10%':>9} {'Spread':>8}")
    print('-' * 70)

    all_results = []

    for daynum in test_daynums:
        day_rows = []
        raw_count = 0  # Stocks with valid X data
        excluded_count = 0  # Stocks excluded by filter

        for ticker in common_tickers:
            row = {'ticker': ticker}
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

            if not valid:
                continue

            raw_count += 1  # Valid X data

            # Apply same filtering as training (skip if no filter vars)
            if FILTER_VARS:
                is_outlier = False
                for var in FILTER_VARS:
                    if FILTER_METHOD == 'decile':
                        if var in decile_bounds and row[var] >= decile_bounds[var]:
                            is_outlier = True
                            break
                    else:
                        if row[var] < filter_stats[var]['lower'] or row[var] > filter_stats[var]['upper']:
                            is_outlier = True
                            break
                if is_outlier:
                    excluded_count += 1
                    continue

            try:
                y_val = y_df.loc[ticker, daynum]
                if pd.isna(y_val) or y_val == '':
                    continue
                row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
            except:
                continue

            day_rows.append(row)

        if not day_rows:
            continue

        day_df = pd.DataFrame(day_rows)
        X_day = day_df[x_names]
        X_day_scaled = scaler.transform(X_day)
        X_day_pca = pca.transform(X_day_scaled)[:, :n_components]
        X_day_const = sm.add_constant(pd.DataFrame(X_day_pca), has_constant='add')

        day_df['pred'] = model.predict(X_day_const)

        # Sort by prediction and get top/bottom deciles
        day_df_sorted = day_df.sort_values('pred', ascending=False)
        n_decile = max(1, len(day_df) // 10)
        top10pct = day_df_sorted.head(n_decile)
        bottom10pct = day_df_sorted.tail(n_decile)

        # Count correct signs
        correct_sign = ((day_df['pred'] > 0) == (day_df[Y_VAR] > 0)).sum()
        n_stocks = len(day_df)
        accuracy = correct_sign / n_stocks * 100

        avg_pred = day_df['pred'].mean()
        avg_actual = day_df[Y_VAR].mean()

        # Top vs bottom actual performance (same day - removes market bias)
        top_actual = top10pct[Y_VAR].mean()
        bottom_actual = bottom10pct[Y_VAR].mean()
        spread = top_actual - bottom_actual

        # Exclusion percentage (of raw stocks with valid X data)
        excl_pct = (excluded_count / raw_count * 100) if raw_count > 0 else 0
        filtered_count = raw_count - excluded_count  # After filter, before Y check

        print(f'{daynum:<8} {n_stocks:>6} {accuracy:>5.1f}% {avg_actual:>7.1f} | Top10%:{top_actual:>6.1f}  Bot10%:{bottom_actual:>6.1f}  Spread:{spread:>+6.1f}')

        all_results.append({
            'daynum': daynum,
            'raw_count': raw_count,
            'filtered_count': filtered_count,
            'excl_pct': excl_pct,
            'n_stocks': n_stocks,
            'correct': correct_sign,
            'accuracy': accuracy,
            'avg_pred': avg_pred,
            'avg_actual': avg_actual,
            'top_actual': top_actual,
            'bottom_actual': bottom_actual,
            'spread': spread
        })

    # Summary
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)

    results_df = pd.DataFrame(all_results)
    total_stocks = results_df['n_stocks'].sum()
    total_correct = results_df['correct'].sum()
    overall_acc = total_correct / total_stocks * 100

    print(f'Total stocks tested: {total_stocks}')
    print(f'Overall sign accuracy: {overall_acc:.1f}% (random=50%, improvement={overall_acc-50:+.1f}%)')

    # Ranking ability (the real test - does model ranking work?)
    print('\n--- RANKING ABILITY (removes market direction bias) ---')
    avg_spread = results_df['spread'].mean()
    positive_spread_days = (results_df['spread'] > 0).sum()
    print(f'Avg spread (top10% - bottom10%): {avg_spread:+.1f}%')
    print(f'Days with positive spread: {positive_spread_days}/{len(results_df)} ({positive_spread_days/len(results_df)*100:.0f}%)')
    print(f'Avg top10% actual: {results_df["top_actual"].mean():.1f}%')
    print(f'Avg bottom10% actual: {results_df["bottom_actual"].mean():.1f}%')

    if avg_spread > 0:
        print(f'\n=> Model HAS ranking ability: predicted best outperform predicted worst by {avg_spread:.1f}%')
    else:
        print(f'\n=> Model has NO ranking ability: spread is {avg_spread:.1f}%')


if __name__ == '__main__':
    main()
