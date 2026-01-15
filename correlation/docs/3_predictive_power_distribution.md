# Task 3: Distribution of Predictive Power

This task provides a deeper dive into the predictive power of indicators by analyzing how correlations are distributed across the entire universe of stocks (~1086 tickers).

## Script: `analyze_distribution.py`

### Goal
Count how many stocks fall into various correlation buckets for each indicator, providing a "histogram-like" view of indicator performance.

### Usage
```bash
ssh gandalf "/home/sm/miniconda3/envs/potsystem_env/bin/python ~/potentials/correlation/code/analyze_distribution.py"
```

### Key Features
- **Bucketing**: Groups per-stock correlations into 10 intervals of width 0.2:
    - `[-1, -0.8], (-0.8, -0.6], ..., (0.8, 1]`
- **Midpoint Labeling**: Buckets are labeled by their centers for clarity:
    - `-0,9, -0,7, -0,5, -0,3, -0,1, 0,1, 0,3, 0,5, 0,7, 0,9`
- **European Formatting**: Outputs CSVs with `;` separator and `,` decimal.
- **Robustness**: Automatically handles mixed data types and suppresses warnings via modern pandas practices.

### Outputs
- `correlation_distribution.csv`: A matrix where rows are indicators and columns are correlation buckets. Each cell contains the count of stocks whose individual correlation falls within that bucket.

## Methodology
For each indicator, we calculate a Pearson correlation for every ticker with at least 2 data points and non-zero variance. These correlations are then categorized using `pd.cut` and tallied. This view reveals if an indicator has a "thick tail" of high correlation or if it is mostly centered around zero.
