#!/usr/bin/env python3
"""
PCA Regression: Find principal factors predicting future gains.
Stage 1: PCA on 15 X-variables to find components explaining 90% variance
Stage 2: Regress future_gain on principal components
Stage 3: Interpret loadings and validate
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

# All candidate X variables (15 total)
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

Y_VAR = 'future_gain50d'
VARIANCE_THRESHOLD = 0.90  # Keep components explaining 90% of variance


def load_csv(f):
    return pd.read_csv(OUTPUT_DIR / f, sep=';', decimal=',', index_col=0, low_memory=False)


def main():
    print('=' * 80)
    print('PCA REGRESSION ANALYSIS')
    print('=' * 80)

    # Load all X variables
    print('\nLoading X variables...')
    x_dfs = {}
    for name, filename in X_VARS.items():
        path = OUTPUT_DIR / filename
        if path.exists():
            x_dfs[name] = load_csv(filename)
            print(f'  {name}: {x_dfs[name].shape}')
        else:
            print(f'  WARNING: {filename} not found')

    # Load Y variable
    print(f'\nLoading Y variable: {Y_VAR}')
    y_df = load_csv(f'{Y_VAR}.csv')
    print(f'  {Y_VAR}: {y_df.shape}')

    # Find common tickers and daynums
    common_tickers = set(y_df.index)
    common_daynums = set(y_df.columns)
    for df in x_dfs.values():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    all_daynums = sorted(common_daynums, key=lambda x: int(x), reverse=True)
    print(f'\nCommon tickers: {len(common_tickers)}, daynums: {len(all_daynums)}')

    # Find daynums with actual Y data
    valid_daynums = []
    for dn in all_daynums:
        col = y_df[dn]
        non_empty = col.dropna()
        non_empty = non_empty[non_empty != '']
        if len(non_empty) > 500:
            valid_daynums.append(dn)

    test_daynums = valid_daynums[:10]
    train_daynums = valid_daynums[10:]

    print(f'Daynums with Y data: {len(valid_daynums)}')
    print(f'Test daynums: {len(test_daynums)} (most recent with outcomes)')
    print(f'Train daynums: {len(train_daynums)}')

    # Build training data
    print('\nBuilding training dataset...')
    rows = []
    x_names = list(x_dfs.keys())

    for ticker in common_tickers:
        for daynum in train_daynums:
            row = {'ticker': ticker, 'daynum': daynum}
            valid = True

            # Get all X values
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

            # Get Y value
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
    print(f'Training observations: {len(train_data):,}')

    # Remove inf/nan
    X_train = train_data[x_names]
    y_train = train_data[Y_VAR]
    mask = ~(X_train.isna().any(axis=1) | y_train.isna() | np.isinf(X_train).any(axis=1) | np.isinf(y_train))
    X_train = X_train[mask]
    y_train = y_train[mask]
    print(f'After removing NaN/Inf: {len(X_train):,}')

    # Standardize X variables
    print('\nStandardizing X variables...')
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    X_scaled_df = pd.DataFrame(X_scaled, columns=x_names, index=X_train.index)

    # Correlation matrix (before PCA)
    print('\n' + '=' * 80)
    print('CORRELATION MATRIX (top correlations)')
    print('=' * 80)
    corr = X_scaled_df.corr()
    corr_pairs = []
    for i, var1 in enumerate(x_names):
        for j, var2 in enumerate(x_names):
            if i < j:
                corr_pairs.append((var1, var2, corr.loc[var1, var2]))
    corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    print(f"{'Var1':<15} {'Var2':<15} {'Corr':>8}")
    print('-' * 40)
    for v1, v2, c in corr_pairs[:15]:
        print(f'{v1:<15} {v2:<15} {c:>8.3f}')

    # PCA
    print('\n' + '=' * 80)
    print('PRINCIPAL COMPONENT ANALYSIS')
    print('=' * 80)

    pca = PCA()
    X_pca = pca.fit_transform(X_scaled)

    # Variance explained
    var_explained = pca.explained_variance_ratio_
    cumulative_var = np.cumsum(var_explained)

    print(f"\n{'PC':<5} {'Var%':>8} {'Cumul%':>8}")
    print('-' * 25)
    for i, (v, c) in enumerate(zip(var_explained, cumulative_var)):
        marker = ' <-- 90%' if i > 0 and cumulative_var[i-1] < VARIANCE_THRESHOLD <= c else ''
        print(f'PC{i+1:<3} {v*100:>8.2f} {c*100:>8.2f}{marker}')
        if c > 0.99:
            break

    # Select components for threshold
    n_components = np.argmax(cumulative_var >= VARIANCE_THRESHOLD) + 1
    print(f'\nComponents for {VARIANCE_THRESHOLD*100:.0f}% variance: {n_components}')

    # Component loadings (interpretation)
    print('\n' + '=' * 80)
    print('COMPONENT LOADINGS (what each PC represents)')
    print('=' * 80)

    loadings = pd.DataFrame(
        pca.components_[:n_components].T,
        columns=[f'PC{i+1}' for i in range(n_components)],
        index=x_names
    )

    for pc in loadings.columns:
        print(f'\n--- {pc} (explains {var_explained[int(pc[2:])-1]*100:.1f}% variance) ---')
        sorted_loadings = loadings[pc].abs().sort_values(ascending=False)
        for var in sorted_loadings.head(5).index:
            val = loadings.loc[var, pc]
            direction = '+' if val > 0 else '-'
            print(f'  {direction}{var:<15} {abs(val):.3f}')

    # Regression on principal components
    print('\n' + '=' * 80)
    print(f'REGRESSION: {Y_VAR} ~ Principal Components')
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

    # Translate back to original variables
    print('\n' + '=' * 80)
    print('EFFECTIVE COEFFICIENTS (in original variable space)')
    print('=' * 80)
    print('(PC coefficients × loadings, showing net effect of each original variable)')

    pc_coefs = model.params[1:].values  # exclude const
    effective_coefs = loadings.values @ pc_coefs

    eff_df = pd.DataFrame({'Variable': x_names, 'Effective_Coef': effective_coefs})
    eff_df['Abs_Coef'] = eff_df['Effective_Coef'].abs()
    eff_df = eff_df.sort_values('Abs_Coef', ascending=False)

    print(f"\n{'Variable':<15} {'Eff.Coef':>12} {'Direction':<10}")
    print('-' * 40)
    for _, row in eff_df.iterrows():
        direction = 'POSITIVE' if row['Effective_Coef'] > 0 else 'NEGATIVE'
        print(f"{row['Variable']:<15} {row['Effective_Coef']:>12.4f} {direction:<10}")

    # Validation on test set
    print('\n' + '=' * 80)
    print('VALIDATION: Top 10 stocks per test daynum')
    print('=' * 80)

    all_preds = []
    for daynum in test_daynums:
        day_rows = []
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
                try:
                    y_val = y_df.loc[ticker, daynum]
                    if pd.isna(y_val) or y_val == '':
                        row[Y_VAR] = np.nan
                    else:
                        row[Y_VAR] = float(str(y_val).replace(',', '.')) if isinstance(y_val, str) else float(y_val)
                except:
                    row[Y_VAR] = np.nan
                day_rows.append(row)

        if not day_rows:
            continue

        day_df = pd.DataFrame(day_rows)
        X_day = day_df[x_names]

        # Scale and transform to PC space
        X_day_scaled = scaler.transform(X_day)
        X_day_pca = pca.transform(X_day_scaled)[:, :n_components]
        X_day_pca_df = pd.DataFrame(X_day_pca, columns=[f'PC{i+1}' for i in range(n_components)])
        X_day_pca_const = sm.add_constant(X_day_pca_df, has_constant='add')

        day_df['pred'] = model.predict(X_day_pca_const)
        day_df = day_df.sort_values('pred', ascending=False)
        top10 = day_df.head(10)

        print(f'\n--- Daynum {daynum} ---')
        print(f"{'Rk':<3} {'Ticker':<8} {'Pred':>8} {'Actual':>8}")
        print('-' * 30)

        for i, (_, r) in enumerate(top10.iterrows(), 1):
            actual = r[Y_VAR]
            act_s = f'{actual:.1f}' if not pd.isna(actual) else 'N/A'
            print(f"{i:<3} {r['ticker']:<8} {r['pred']:>8.1f} {act_s:>8}")
            all_preds.append({'daynum': daynum, 'ticker': r['ticker'], 'pred': r['pred'], 'actual': actual})

        valid_t10 = top10[~top10[Y_VAR].isna()]
        if len(valid_t10) > 0:
            print(f"  Avg: pred={valid_t10['pred'].mean():.1f}, actual={valid_t10[Y_VAR].mean():.1f}")

    # Summary
    print('\n' + '=' * 80)
    print('OVERALL SUMMARY')
    print('=' * 80)

    pred_df = pd.DataFrame(all_preds)
    valid = pred_df[~pred_df['actual'].isna()]

    print(f'Top-10 picks total: {len(valid)}')
    print(f'Avg predicted: {valid["pred"].mean():.1f}%')
    print(f'Avg actual: {valid["actual"].mean():.1f}%')
    print(f'Correlation (pred vs actual): {valid["pred"].corr(valid["actual"]):.3f}')
    winners = (valid['actual'] > 0).sum()
    print(f'Winners (actual>0): {winners}/{len(valid)} = {(valid["actual"]>0).mean()*100:.0f}%')

    # Market benchmark
    all_actuals = []
    for dn in test_daynums:
        for t in common_tickers:
            try:
                v = y_df.loc[t, dn]
                if not pd.isna(v) and v != '':
                    all_actuals.append(float(str(v).replace(',', '.')) if isinstance(v, str) else float(v))
            except:
                pass
    mkt_avg = np.mean(all_actuals)
    mkt_win = (np.array(all_actuals) > 0).mean() * 100

    print(f'\nBenchmark (all stocks in test period):')
    print(f'  Market avg gain: {mkt_avg:.1f}%')
    print(f'  Market win rate: {mkt_win:.0f}%')
    print(f'  Model outperformance: {valid["actual"].mean() - mkt_avg:+.1f}%')


if __name__ == '__main__':
    main()
