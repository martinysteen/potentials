# Stock Indicator correlation Analysis Project

This project contains tools to analyze correlations between stock indicators and their predictive power for future price movements.

## Project Structure
- **`code/`**: Python scripts for data processing and analysis.
- **`input/`**: Raw CSV data files (European format: `;` separator, `,` decimal).
- **`output/`**: Generated CSV reports, statistics, and visualizations.
- **`docs/`**: Detailed documentation and walkthroughs for each task.

## Analysis Tasks

### 1. Internal Correlation Among Indicators
Investigate how indicators relate to each other to identify redundancies.
- **Script**: `code/analyze_correlations.py`
- **Outputs**: `correlation_matrix.csv`, `correlation_matrix_complete.csv`, `correlation_heatmap.png`, `indicator_spans.csv`
- **Documentation**: [docs/1_internal_correlation.md](docs/1_internal_correlation.md)

### 2. Predictive Power towards Performance
Measure how well indicators predict 20-day forward price gains.
- **Script**: `code/analyze_perfcorr.py`
- **Output**: `performance_correlation_20d_augmented.csv`
- **Documentation**: [docs/2_predictive_power.md](docs/2_predictive_power.md)

### 3. Distribution of Predictive Power
Histogram-like view of how predictive power is distributed across ~1086 stocks.
- **Script**: `code/analyze_distribution.py`
- **Output**: `correlation_distribution.csv`
- **Documentation**: [docs/3_predictive_power_distribution.md](docs/3_predictive_power_distribution.md)

## Usage
Run scripts using the dedicated Conda environment on `gandalf`:
```bash
ssh gandalf "/home/sm/miniconda3/envs/potsystem_env/bin/python ~/potentials/correlation/code/[SCRIPT_NAME].py"
```

## Requirements
- Python 3.x
- Pandas, NumPy, Scipy, Seaborn, Matplotlib (available in `potsystem_env`)
