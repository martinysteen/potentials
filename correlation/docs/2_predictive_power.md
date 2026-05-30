# Task 2: Predictive Power of Indicators

This task evaluates the predictive capability of indicators towards future stock performance, specifically 20-day forward gains.

## Script: `analyze_perfcorr.py`

### Goal
Calculate the correlation between an indicator at time $t$ and the stock's performance between time $t$ and $t+21$ (20 trading days).

### Usage
```bash
ssh gandalf "/home/sm/miniconda3/envs/potsystem_env/bin/python ~/potentials/correlation/code/analyze_perfcorr.py"
```

### Key Features
- **Price Loading**: Parses `PotDat.csv` for historical price data.
- **Future Gain Calculation**: Computes $Gain = Price_{t+21} / Price_t - 1$.
- **Per-Stock Granularity**: In addition to global correlation, it calculates min, max, and mean correlation for each ticker individually.
- **Categorical Handling**: Automatically maps categorical indicators like `uptrend` (e.g., 'VeryGood' -> 5) to numerical values.

### Outputs
- `performance_correlation_20d_augmented.csv`: A summary table containing:
    - **Global_Corr**: Correlation across all data points.
    - **Min_Corr / Max_Corr**: The range of correlations found across individual stocks.
    - **Mean_Stock_Corr**: The average per-stock correlation.
    - **Total_Samples**: Total data points used.

## Methodology
The script aligns each indicator observation with a future price change. By looking at the distribution of correlations across stocks, we can determine if an indicator is universally predictive or if its effectiveness varies significantly by ticker.
