# Production Recipe: Stock Indicator Correlation Analysis

This document preserves the "technical recipe" — the sequence of core instructions, technical constraints, and design requirements — used to build this project. It provides the full picture necessary to recreate the project or move it to another LLM-backed IDE.

## 0. General Context & Environment

- **Hybrid Setup**: The IDE (Antigravity/VS Code) is hosted on a **Windows 11 PC**, but all computational work is executed on a remote **Ubuntu server (`gandalf`)** via SSH.
- **Data Access**: Files are located on `gandalf` and accessed via UNC paths (e.g., `\\gandalf\sm-home\...`) for editing, while execution happens directly on the server.
- **Execution Workflow**: Commands are issued from the Windows host to the Ubuntu server using SSH:
  `ssh gandalf "/home/sm/miniconda3/envs/potsystem_env/bin/python ~/potentials/correlation/code/[SCRIPT].py"`
- **Data Source**: CSV files from Google Cloud Drive, sync'd to `gandalf`.
- **File Format**: European CSV (`;` separator, `,` decimal, no thousand separators).
- **Naming Pattern**: `longi_*.csv` (where `*` is the indicator name).
- **Backend**: Python 3.x using Pandas, NumPy, SciPy, Seaborn, and Matplotlib in the `potsystem_env` Conda environment.

---

## 1. Task: Internal Correlation Among Indicators

**Objective**: Investigate how indicators relate to each other.

### Instructions:
- **Loading**: Merge multiple `longi_*.csv` files on Ticker and Daynum. Note that indicators may have different coverage/spans.
- **Reporting**: 
  - Generate a `correlation_matrix.csv` (pairwise using available data).
  - Generate a `correlation_matrix_complete.csv` (Complete-Case Analysis: only rows where ALL indicators have values).
  - Generate `indicator_spans.csv` showing the date range (min/max daynum) and count for each indicator.
- **Refinement**: Implement a way to exclude "bottleneck" indicators (like `per1y`) that have very low coverage to increase the "complete-case" sample size.

---

## 2. Task: Visualization (Heatmap)

**Objective**: Create a high-quality visualization of the indicator correlations.

### Instructions:
- **Library**: Use Seaborn/Matplotlib.
- **Aesthetics**:
  - Use a symmetric Red-White-Green gradient (`RdYlGn` or similar) where 0 is neutral (white).
  - Sort the indicators alphabetically on both axes for symmetry.
  - Ensure labels are readable and the plot is saved as `correlation_heatmap.png`.

---

## 3. Task: Predictive Power towards Performance

**Objective**: Measure the correlation between indicators and future stock price gains.

### Instructions:
- **Data Source**: Load price data from `PotDat.csv` (European format) and indicator values from `longi_*.csv`.
- **Preprocessing**: Map categorical indicator values (e.g., 'VeryGood'=3, 'Good'=2, 'Maybe'=1, 'No'=0) to numerical values.
- **Calculation**: 
  - Define `FutureGain` as the price gain over a 20-day horizon (comparing price at $t$ vs $t+21$).
  - Calculate the Pearson correlation between Indicator Value at $t$ and `FutureGain` from $t \to t+21$.
- **Augmentation**: For each indicator, report the global correlation AND per-stock statistics (min, max, mean correlation) to see if power varies by ticker.

---

## 4. Task: Distribution of Predictive Power

**Objective**: Visualize how predictive power (correlation) is distributed across the universe of stocks.

### Instructions:
- **Logic**: Instead of a single number, create a "histogram-ready" table.
- **Processing**: Calculate the indicator-to-gain correlation for *every* individual stock.
- **Output**: Save results to `correlation_distribution.csv` to allow for further statistical distribution analysis.

---

## 5. Project Organization & Maintenance

**Objective**: Consolidate output and ensure reproducibility.

### Instructions:
- **Workspace**: Organize files into `code/`, `docs/`, `input/`, and `output/`.
- **Documentation**: 
  - Create a central `README.md` and detailed walkthroughs in `docs/` for each specific analysis.
  - Walkthroughs should detail the specific methodology, usage commands, and key findings.
- **Consistency**: Ensure all output CSV tables are sorted alphabetically by the `indicator` column (when present as the first column) for easy comparison.
