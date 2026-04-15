#!/usr/bin/env python3
"""
PCA Regression with Outlier Filtering
Excludes extreme values (decile 10 or >3 sigma) from spr100d, vola20d, vola100d.
These are marked "prediction not possible" and excluded from analysis.
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

# Variables with outlier filtering
FILTER_VARS = ['spr100d', 'vola20d', 'vola100d']

# All X variables
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

Y_VAR = 'future_gain20d'
print(f'Y_VAR: {Y_VAR}')
VARIANCE_THRESHOLD = 0.90

# Filtering method: 'decile' or 'sigma'
FILTER_METHOD = 'sigma'  # 'decile' excludes decile 10, 'sigma' excludes beyond mean +/- 3*std
SIGMA_THRESHOLD = 3.0


def load_csv(f):
    return pd.read_csv(OUTPUT_DIR / f, sep=';', decimal=',', index_col=0, low_memory=False)


def load_decile_boundaries():
    """Load decile boundaries from aux_deciles.csv"""
    df = pd.read_csv(OUTPUT_DIR / 'aux_deciles.csv', sep=';', decimal=',')
    boundaries = {}
    for indicator in df['Indicator'].unique():
        ind_data = df[df['Indicator'] == indicator].sort_values('Decile')
        # Get lower limit of decile 10 (values >= this are in decile 10)
        d10 = ind_data[ind_data['Decile'] == 10]
        if len(d10) > 0:
            boundaries[indicator] = float(d10['LowerLimit'].values[0])
    return boundaries


def main():
    print('=' * 80)
    print('PCA REGRESSION WITH OUTLIER FILTERING')
    print('=' * 80)
    print(f'Filter method: {FILTER_METHOD}')
    print(f'Variables filtered: {FILTER_VARS}')

    # Load decile boundaries if using decile method
    decile_bounds = {}
    if FILTER_METHOD == 'decile':
        decile_bounds = load_decile_boundaries()
        print('\nDecile 10 lower bounds (will exclude >= these values):')
        for var in FILTER_VARS:
            if var in decile_bounds:
                print(f'  {var}: {decile_bounds[var]:.2f}')
    else:
        print(f'\nUsing {SIGMA_THRESHOLD}-sigma rule: values beyond mean +/- {SIGMA_THRESHOLD}*std will be excluded')

    # Load all X variables
    print('\nLoading X variables...')
    x_dfs = {}
    for name, filename in X_VARS.items():
        path = OUTPUT_DIR / filename
        if path.exists():
            x_dfs[name] = load_csv(filename)

    # Load Y variable
    y_df = load_csv(f'{Y_VAR}.csv')

    # Find common tickers and daynums
    common_tickers = set(y_df.index)
    common_daynums = set(y_df.columns)
    for df in x_dfs.values():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    all_daynums = sorted(common_daynums, key=lambda x: int(x), reverse=True)
    print(f'Common tickers: {len(common_tickers)}, daynums: {len(all_daynums)}')

    # Find daynums with Y data
    valid_daynums = []
    for dn in all_daynums:
        col = y_df[dn]
        non_empty = col.dropna()
        non_empty = non_empty[non_empty != '']
        if len(non_empty) > 500:
            valid_daynums.append(dn)

    test_daynums = valid_daynums[:10]
    train_daynums = valid_daynums[10:]
    print(f'Train daynums: {len(train_daynums)}, Test daynums: {len(test_daynums)}')

    # Build training data
    print('\nBuilding training dataset...')
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
    print(f'Raw training observations: {len(train_data):,}')

    # Apply outlier filtering
    print('\n' + '=' * 80)
    print('OUTLIER FILTERING')
    print('=' * 80)

    filter_stats = {}

    if FILTER_METHOD == 'decile':
        # Exclude decile 10 for each filter variable
        mask = pd.Series(True, index=train_data.index)
        for var in FILTER_VARS:
            if var in decile_bounds:
                threshold = decile_bounds[var]
                excluded = train_data[var] >= threshold
                filter_stats[var] = {
                    'threshold': threshold,
                    'excluded': excluded.sum(),
                    'pct': excluded.mean() * 100
                }
                mask = mask & ~excluded
                print(f'{var}: excluded {excluded.sum():,} obs >= {threshold:.2f} ({excluded.mean()*100:.1f}%)')
    else:
        # 3-sigma rule
        mask = pd.Series(True, index=train_data.index)
        for var in FILTER_VARS:
            mean = train_data[var].mean()
            std = train_data[var].std()
            upper = mean + SIGMA_THRESHOLD * std
            lower = mean - SIGMA_THRESHOLD * std
            excluded = (train_data[var] > upper) | (train_data[var] < lower)
            filter_stats[var] = {
                'mean': mean,
                'std': std,
                'upper': upper,
                'lower': lower,
                'excluded': excluded.sum(),
                'pct': excluded.mean() * 100
            }
            mask = mask & ~excluded
            print(f'{var}: excluded {excluded.sum():,} obs outside [{lower:.2f}, {upper:.2f}] ({excluded.mean()*100:.1f}%)')

    train_filtered = train_data[mask].copy()
    print(f'\nAfter filtering: {len(train_filtered):,} observations ({len(train_filtered)/len(train_data)*100:.1f}% retained)')

    # Remove inf/nan
    X_train = train_filtered[x_names]
    y_train = train_filtered[Y_VAR]
    clean_mask = ~(X_train.isna().any(axis=1) | y_train.isna() | np.isinf(X_train).any(axis=1) | np.isinf(y_train))
    X_train = X_train[clean_mask]
    y_train = y_train[clean_mask]
    print(f'After NaN/Inf removal: {len(X_train):,}')

    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    X_scaled_df = pd.DataFrame(X_scaled, columns=x_names, index=X_train.index)

    # PCA
    print('\n' + '=' * 80)
    print('PCA ON FILTERED DATA')
    print('=' * 80)

    pca = PCA()
    X_pca = pca.fit_transform(X_scaled)

    var_explained = pca.explained_variance_ratio_
    cumulative_var = np.cumsum(var_explained)

    print(f"\n{'PC':<5} {'Var%':>8} {'Cumul%':>8}")
    print('-' * 25)
    for i, (v, c) in enumerate(zip(var_explained, cumulative_var)):
        marker = ' <-- 90%' if i > 0 and cumulative_var[i-1] < VARIANCE_THRESHOLD <= c else ''
        print(f'PC{i+1:<3} {v*100:>8.2f} {c*100:>8.2f}{marker}')
        if c > 0.99:
            break

    n_components = np.argmax(cumulative_var >= VARIANCE_THRESHOLD) + 1
    print(f'\nComponents for 90% variance: {n_components}')

    # Loadings
    loadings = pd.DataFrame(
        pca.components_[:n_components].T,
        columns=[f'PC{i+1}' for i in range(n_components)],
        index=x_names
    )

    # Regression
    print('\n' + '=' * 80)
    print('REGRESSION ON FILTERED DATA')
    print('=' * 80)

    X_pca_selected = X_pca[:, :n_components]
    X_pca_df = pd.DataFrame(X_pca_selected, columns=[f'PC{i+1}' for i in range(n_components)])
    X_pca_const = sm.add_constant(X_pca_df)
    model = sm.OLS(y_train.values, X_pca_const).fit()

    print(f'\nR-squared: {model.rsquared:.4f}')
    print(f'Adjusted R-squared: {model.rsquared_adj:.4f}')

    print(f"\n{'Variable':<10} {'Coef':>10} {'t-stat':>10} {'P>|t|':>10} {'Sig':<5}")
    print('-' * 50)
    for var in model.params.index:
        coef = model.params[var]
        tstat = model.tvalues[var]
        pval = model.pvalues[var]
        sig = '***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else ''
        print(f'{var:<10} {coef:>10.4f} {tstat:>10.2f} {pval:>10.4f} {sig:<5}')

    # Effective coefficients
    pc_coefs = model.params[1:].values
    effective_coefs = loadings.values @ pc_coefs
    eff_df = pd.DataFrame({'Variable': x_names, 'Eff_Coef': effective_coefs})
    eff_df = eff_df.reindex(eff_df['Eff_Coef'].abs().sort_values(ascending=False).index)

    print('\n' + '=' * 80)
    print('EFFECTIVE COEFFICIENTS (filtered model)')
    print('=' * 80)
    print(f"\n{'Variable':<15} {'Eff.Coef':>12} {'Direction':<10}")
    print('-' * 40)
    for _, row in eff_df.iterrows():
        direction = 'POSITIVE' if row['Eff_Coef'] > 0 else 'NEGATIVE'
        print(f"{row['Variable']:<15} {row['Eff_Coef']:>12.4f} {direction:<10}")

    # Residual analysis on training data
    print('\n' + '=' * 80)
    print('RESIDUAL ANALYSIS')
    print('=' * 80)

    y_pred_train = model.predict(X_pca_const)
    residuals = y_train.values - y_pred_train

    print(f'Residual stats:')
    print(f'  Mean: {residuals.mean():.4f} (should be ~0)')
    print(f'  Std: {residuals.std():.2f}')
    print(f'  Min: {residuals.min():.1f}, Max: {residuals.max():.1f}')

    # Residuals by predicted value bins
    pred_bins = pd.cut(y_pred_train, bins=10)
    resid_by_bin = pd.DataFrame({'pred': y_pred_train, 'resid': residuals, 'bin': pred_bins})

    print(f"\n{'Pred Bin':<25} {'N':>8} {'Mean Resid':>12} {'Std Resid':>12}")
    print('-' * 60)
    for bin_label, group in resid_by_bin.groupby('bin', observed=True):
        print(f'{str(bin_label):<25} {len(group):>8} {group["resid"].mean():>12.2f} {group["resid"].std():>12.2f}')

    # Validation with filtering
    print('\n' + '=' * 80)
    print('VALIDATION: Top 10 stocks (excluding outliers)')
    print('=' * 80)

    if FILTER_METHOD == 'decile':
        filter_thresholds = decile_bounds
    else:
        filter_thresholds = {var: filter_stats[var]['upper'] for var in FILTER_VARS}

    all_preds = []
    excluded_counts = []
    excluded_actuals = []  # Track actual outcomes of filtered-out stocks

    for daynum in test_daynums:
        day_rows = []
        excluded_this_day = 0
        excluded_rows = []  # Stocks excluded this day

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

            if valid:
                # Check if should be filtered
                is_outlier = False
                for var in FILTER_VARS:
                    if FILTER_METHOD == 'decile':
                        if var in filter_thresholds and row[var] >= filter_thresholds[var]:
                            is_outlier = True
                            break
                    else:
                        if var in filter_stats:
                            if row[var] > filter_stats[var]['upper'] or row[var] < filter_stats[var]['lower']:
                                is_outlier = True
                                break

                # Get Y value for both included and excluded
                try:
                    y_val = y_df.loc[ticker, daynum]
                    if pd.isna(y_val) or y_val == '':
                        row[Y_VAR] = np.nan
                    else:
                        row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
                except:
                    row[Y_VAR] = np.nan

                if is_outlier:
                    excluded_this_day += 1
                    excluded_rows.append(row)
                    continue

                day_rows.append(row)

        excluded_counts.append(excluded_this_day)

        # Collect excluded stocks' actuals
        for er in excluded_rows:
            excluded_actuals.append({'daynum': daynum, 'ticker': er['ticker'], 'actual': er[Y_VAR]})

        if not day_rows:
            continue

        day_df = pd.DataFrame(day_rows)
        X_day = day_df[x_names]
        X_day_scaled = scaler.transform(X_day)
        X_day_pca = pca.transform(X_day_scaled)[:, :n_components]
        X_day_pca_df = pd.DataFrame(X_day_pca, columns=[f'PC{i+1}' for i in range(n_components)])
        X_day_pca_const = sm.add_constant(X_day_pca_df, has_constant='add')

        day_df['pred'] = model.predict(X_day_pca_const)
        day_df_sorted = day_df.sort_values('pred', ascending=False)
        top10 = day_df_sorted.head(10)
        bottom10 = day_df_sorted.tail(10)

        print(f'\n--- Daynum {daynum} (excluded {excluded_this_day} outliers) ---')

        # TOP 10 (highest predicted)
        print(f"\nTOP 10 (highest predicted gain):")
        print(f"{'Rk':<3} {'Ticker':<8} {'Pred':>8} {'Actual':>8} {'Resid':>8}")
        print('-' * 40)

        for i, (_, r) in enumerate(top10.iterrows(), 1):
            actual = r[Y_VAR]
            resid = actual - r['pred'] if not pd.isna(actual) else np.nan
            act_s = f'{actual:.1f}' if not pd.isna(actual) else 'N/A'
            res_s = f'{resid:+.1f}' if not pd.isna(resid) else ''
            print(f"{i:<3} {r['ticker']:<8} {r['pred']:>8.1f} {act_s:>8} {res_s:>8}")
            all_preds.append({'daynum': daynum, 'ticker': r['ticker'], 'pred': r['pred'], 'actual': actual, 'group': 'top10'})

        valid_t10 = top10[~top10[Y_VAR].isna()]
        if len(valid_t10) > 0:
            avg_resid = (valid_t10[Y_VAR] - valid_t10['pred']).mean()
            print(f"  Avg: pred={valid_t10['pred'].mean():.1f}, actual={valid_t10[Y_VAR].mean():.1f}, resid={avg_resid:+.1f}")

        # BOTTOM 10 (lowest predicted)
        print(f"\nBOTTOM 10 (lowest predicted gain):")
        print(f"{'Rk':<3} {'Ticker':<8} {'Pred':>8} {'Actual':>8} {'Resid':>8}")
        print('-' * 40)

        for i, (_, r) in enumerate(bottom10.iterrows(), 1):
            actual = r[Y_VAR]
            resid = actual - r['pred'] if not pd.isna(actual) else np.nan
            act_s = f'{actual:.1f}' if not pd.isna(actual) else 'N/A'
            res_s = f'{resid:+.1f}' if not pd.isna(resid) else ''
            print(f"{i:<3} {r['ticker']:<8} {r['pred']:>8.1f} {act_s:>8} {res_s:>8}")
            all_preds.append({'daynum': daynum, 'ticker': r['ticker'], 'pred': r['pred'], 'actual': actual, 'group': 'bottom10'})

        valid_b10 = bottom10[~bottom10[Y_VAR].isna()]
        if len(valid_b10) > 0:
            avg_resid = (valid_b10[Y_VAR] - valid_b10['pred']).mean()
            print(f"  Avg: pred={valid_b10['pred'].mean():.1f}, actual={valid_b10[Y_VAR].mean():.1f}, resid={avg_resid:+.1f}")

    # Summary
    print('\n' + '=' * 80)
    print('OVERALL SUMMARY (FILTERED MODEL)')
    print('=' * 80)

    print(f'Avg outliers excluded per day: {np.mean(excluded_counts):.1f}')

    pred_df = pd.DataFrame(all_preds)

    # Separate top10 and bottom10
    top10_df = pred_df[pred_df['group'] == 'top10']
    bottom10_df = pred_df[pred_df['group'] == 'bottom10']

    valid_top = top10_df[~top10_df['actual'].isna()]
    valid_bottom = bottom10_df[~bottom10_df['actual'].isna()]

    print(f"\n{'Metric':<25} {'TOP 10':>15} {'BOTTOM 10':>15}")
    print('-' * 58)
    print(f"{'Picks total':<25} {len(valid_top):>15} {len(valid_bottom):>15}")
    print(f"{'Avg predicted':<25} {valid_top['pred'].mean():>14.1f}% {valid_bottom['pred'].mean():>14.1f}%")
    print(f"{'Avg actual':<25} {valid_top['actual'].mean():>14.1f}% {valid_bottom['actual'].mean():>14.1f}%")
    print(f"{'Avg residual':<25} {(valid_top['actual'] - valid_top['pred']).mean():>+14.1f}% {(valid_bottom['actual'] - valid_bottom['pred']).mean():>+14.1f}%")
    print(f"{'Correlation':<25} {valid_top['pred'].corr(valid_top['actual']):>15.3f} {valid_bottom['pred'].corr(valid_bottom['actual']):>15.3f}")

    top_winners = (valid_top['actual'] > 0).sum()
    bottom_winners = (valid_bottom['actual'] > 0).sum()
    print(f"{'Winners (actual>0)':<25} {top_winners}/{len(valid_top)} ({(valid_top['actual']>0).mean()*100:.0f}%)      {bottom_winners}/{len(valid_bottom)} ({(valid_bottom['actual']>0).mean()*100:.0f}%)")

    # Correct sign: predicted sign matches actual sign
    top_correct_sign = ((valid_top['pred'] > 0) == (valid_top['actual'] > 0)).sum()
    bottom_correct_sign = ((valid_bottom['pred'] > 0) == (valid_bottom['actual'] > 0)).sum()
    print(f"{'Correct sign':<25} {top_correct_sign}/{len(valid_top)} ({top_correct_sign/len(valid_top)*100:.0f}%)      {bottom_correct_sign}/{len(valid_bottom)} ({bottom_correct_sign/len(valid_bottom)*100:.0f}%)")

    # Wrong direction analysis
    top_wrong = valid_top[(valid_top['pred'] > 0) & (valid_top['actual'] < 0)]
    bottom_wrong = valid_bottom[(valid_bottom['pred'] < 0) & (valid_bottom['actual'] > 0)]
    print(f"{'Predicted + got -':<25} {len(top_wrong)}/{len(valid_top)} ({len(top_wrong)/len(valid_top)*100:.0f}%)      -")
    print(f"{'Predicted - got +':<25} -                {len(bottom_wrong)}/{len(valid_bottom)} ({len(bottom_wrong)/len(valid_bottom)*100:.0f}%)")

    # Excluded stocks analysis
    print('\n' + '=' * 80)
    print('EXCLUDED STOCKS (filtered out as outliers)')
    print('=' * 80)

    excluded_df = pd.DataFrame(excluded_actuals)
    valid_excluded = excluded_df[~excluded_df['actual'].isna()]

    if len(valid_excluded) > 0:
        exc_avg = valid_excluded['actual'].mean()
        exc_winners = (valid_excluded['actual'] > 0).sum()
        exc_correct_sign = (valid_excluded['actual'] < 0).sum()  # We expect them to lose

        print(f'Excluded stocks total: {len(valid_excluded)}')
        print(f'Avg actual gain: {exc_avg:.1f}%')
        print(f'Winners (actual>0): {exc_winners}/{len(valid_excluded)} ({exc_winners/len(valid_excluded)*100:.0f}%)')
        print(f'Losers (actual<0): {exc_correct_sign}/{len(valid_excluded)} ({exc_correct_sign/len(valid_excluded)*100:.0f}%)')
        print(f'\nIf filtering helps, excluded stocks should underperform:')
        print(f'  Excluded avg: {exc_avg:.1f}%')
        print(f'  Top 10 avg: {valid_top["actual"].mean():.1f}%')
        print(f'  Bottom 10 avg: {valid_bottom["actual"].mean():.1f}%')
    else:
        print('No excluded stocks with actual data.')

    # Market benchmark (also filtered)
    all_actuals = []
    for dn in test_daynums:
        for t in common_tickers:
            try:
                # Check if outlier
                is_outlier = False
                for var in FILTER_VARS:
                    val = x_dfs[var].loc[t, dn]
                    if pd.isna(val) or val == '':
                        is_outlier = True
                        break
                    val = float(str(val).replace(',', '.')) if isinstance(val, str) else float(val)
                    if FILTER_METHOD == 'decile':
                        if var in filter_thresholds and val >= filter_thresholds[var]:
                            is_outlier = True
                            break
                    else:
                        if var in filter_stats:
                            if val > filter_stats[var]['upper'] or val < filter_stats[var]['lower']:
                                is_outlier = True
                                break

                if is_outlier:
                    continue

                v = y_df.loc[t, dn]
                if not pd.isna(v) and v != '':
                    all_actuals.append(float(str(v).replace(',', '.')) if isinstance(v, str) else float(v))
            except:
                pass

    mkt_avg = np.mean(all_actuals)
    mkt_win = (np.array(all_actuals) > 0).mean() * 100

    print(f'\nBenchmark (filtered stocks in test period):')
    print(f'  Filtered market avg gain: {mkt_avg:.1f}%')
    print(f'  Filtered market win rate: {mkt_win:.0f}%')
    print(f'  TOP 10 outperformance: {valid_top["actual"].mean() - mkt_avg:+.1f}%')
    print(f'  BOTTOM 10 outperformance: {valid_bottom["actual"].mean() - mkt_avg:+.1f}%')


if __name__ == '__main__':
    main()
