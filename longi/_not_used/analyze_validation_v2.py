#!/usr/bin/env python3
"""Validation: Compare predicted vs actual for top-10 picks."""

import pandas as pd
import numpy as np
from pathlib import Path
import statsmodels.api as sm
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = Path(__file__).parent.parent / 'output'
X_VARS = ['spr100d', 'vola20d', 'vola100d']
Y_VAR = 'future_gain50d'


def load_csv(f):
    return pd.read_csv(OUTPUT_DIR / f, sep=';', decimal=',', index_col=0, low_memory=False)


def main():
    x_dfs = {n: load_csv(f'longi_{n}.csv') for n in X_VARS}
    y_df = load_csv(f'{Y_VAR}.csv')

    common_tickers = set(y_df.index)
    common_daynums = set(y_df.columns)
    for df in x_dfs.values():
        common_tickers &= set(df.index)
        common_daynums &= set(df.columns)

    all_daynums = sorted(common_daynums, key=lambda x: int(x), reverse=True)

    # Find daynums with actual Y data (need >500 stocks with values)
    valid_daynums = []
    for dn in all_daynums:
        col = y_df[dn]
        non_empty = col.dropna()
        non_empty = non_empty[non_empty != '']
        if len(non_empty) > 500:
            valid_daynums.append(dn)

    test_daynums = valid_daynums[:10]
    train_daynums = valid_daynums[10:]  # Use ALL remaining data for training

    print(f'Test daynums (10 most recent with data): {test_daynums}')
    print(f'Training daynums: {len(train_daynums)}')

    # Build training data
    rows = []
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
    print(f'Training obs: {len(train_data)}')

    # Fit model
    X_train = train_data[X_VARS]
    y_train = train_data[Y_VAR]
    mask = ~(X_train.isna().any(axis=1) | y_train.isna() | np.isinf(X_train).any(axis=1) | np.isinf(y_train))
    X_train, y_train = X_train[mask], y_train[mask]
    model = sm.OLS(y_train, sm.add_constant(X_train)).fit()

    print(f'Model R2: {model.rsquared:.4f}')
    print('Coefficients:', {k: round(v, 4) for k, v in model.params.items()})

    # Validate
    print()
    print('=' * 100)
    print('VALIDATION: TOP 10 BY PREDICTED GAIN vs ACTUAL')
    print('=' * 100)

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

        day_df = pd.DataFrame(day_rows)
        X_day = sm.add_constant(day_df[X_VARS], has_constant='add')
        day_df['pred'] = model.predict(X_day)
        day_df = day_df.sort_values('pred', ascending=False)
        top10 = day_df.head(10)

        print(f'\n--- Daynum {daynum} ---')
        print(f"{'Rk':<3} {'Ticker':<8} {'Pred':>8} {'Actual':>8} {'Diff':>8} | {'spr100d':>8} {'vola20d':>8} {'vola100d':>8}")
        print('-' * 85)

        for i, (_, r) in enumerate(top10.iterrows(), 1):
            actual = r[Y_VAR]
            diff = actual - r['pred'] if not pd.isna(actual) else np.nan
            act_s = f'{actual:.1f}' if not pd.isna(actual) else 'N/A'
            diff_s = f'{diff:+.1f}' if not pd.isna(diff) else ''
            print(f"{i:<3} {r['ticker']:<8} {r['pred']:>8.1f} {act_s:>8} {diff_s:>8} | {r['spr100d']:>8.1f} {r['vola20d']:>8.2f} {r['vola100d']:>8.2f}")
            all_preds.append({'daynum': daynum, 'ticker': r['ticker'], 'pred': r['pred'], 'actual': actual})

        valid_t10 = top10[~top10[Y_VAR].isna()]
        if len(valid_t10) > 0:
            winners = (valid_t10[Y_VAR] > 0).sum()
            print(f"  Avg: pred={valid_t10['pred'].mean():.1f}, actual={valid_t10[Y_VAR].mean():.1f}, winners={winners}/10")

    # Summary
    print()
    print('=' * 100)
    print('OVERALL SUMMARY')
    print('=' * 100)
    pred_df = pd.DataFrame(all_preds)
    valid = pred_df[~pred_df['actual'].isna()]
    print(f'Top-10 picks total: {len(valid)}')
    print(f'Avg predicted: {valid["pred"].mean():.1f}%')
    print(f'Avg actual: {valid["actual"].mean():.1f}%')
    print(f'Correlation (pred vs actual): {valid["pred"].corr(valid["actual"]):.3f}')
    winners_count = (valid['actual'] > 0).sum()
    print(f'Winners (actual>0): {winners_count}/{len(valid)} = {(valid["actual"]>0).mean()*100:.0f}%')

    # Benchmark - market average
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


if __name__ == "__main__":
    main()
