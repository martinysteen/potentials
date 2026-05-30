# Task 1: Internal Correlation Among Indicators

This task investigates the statistical relationships between various stock indicators to identify redundancies and patterns.

## Script: `analyze_correlations.py`

### Goal
Quantify how strongly different indicators are linearly related to each other.

### Usage
```bash
ssh gandalf "/home/sm/miniconda3/envs/potsystem_env/bin/python ~/potentials/correlation/code/analyze_correlations.py"
```

### Key Features
- **Data Alignment**: Merges multiple `longi_*.csv` files on Ticker (Yahoo) and Daynum.
- **European Formatting**: Handles `;` as separator and `,` as decimal.
- **Filtering**: Allows excluding specific indicators (e.g., those with low coverage like `per1y`).
- **Complete-Case Analysis**: Optionally synchronizes rows to ensure correlation is calculated on an identical temporal subset.

### Outputs
- `correlation_matrix.csv`: Pairwise correlations using all available overlapping data.
- `correlation_matrix_complete.csv`: Correlations calculated only on rows where ALL indicators have values.
- `correlation_heatmap.png`: A visual representation (Red-White-Green) of the correlation matrix.
- `indicator_spans.csv`: Date range coverage for each indicator.

## Methodology
The script uses the Pearson correlation coefficient. Indicators are pivoted and merged into a wide format before calculating the pairwise covariance.
