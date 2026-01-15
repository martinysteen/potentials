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
- **Special Coding**: For `longi_uptrend.csv`, use the mapping: `VeryGood` and `Very Good` is 5, `Good` is 4, and `Maybe` is 2. Spaces/empty values should be coded as `0` if a number is mandatory, otherwise they should be left empty.
- **Backend**: Python 3.x using Pandas, NumPy, SciPy, Seaborn, and Matplotlib in the `potsystem_env` Conda environment.

---

## 1. Task: 

**Objective**: Investigate how indicators relate to each other.

### Instructions:
- **Loading**: Merge multiple `longi_*.csv` files on Ticker and Daynum. Note that indicators may have different coverage/spans.
- **Reporting**: 
  - Generate a `x.csv` (explanation).
  - Generate a ...

---

## 4. Trial 10: Multi-Indicator Decile Analysis
**Objective**: Scale Trial 9's decile success analysis to all 20 indicators (`longi_*.csv`).
- **Logic**:
  - Window: 132 samples per ticker.
  - Ranking: `rank(method='first', ascending=False)` to ensure D1 = Top 10% highest indicator values.
  - Threshold: Gain > 10% within 21 days.
- **Code**: `code/analyze_gain_success_trial10.py`
- **Output**: `output/trial10_comparison.csv` (D1 vs D10 comparison), `output/trial10_full_decile_[INDICATOR].csv` for top 3 indicators.

## 5. Trial 11: Cross-Indicator Decile & Hurdles
**Objective**: Analyze simultaneous D1 membership overlap between indicators and determine numeric "hurdle" values.
- **Logic**: 
  - Identify (Ticker, Day) pairs in D1 for each indicator.
  - `lowerLimit`: 90th percentile value (entry hurdle).
  - `upperLimit`: Max value in D1.
  - Matrix: 20x20 count of shared D1 members.
- **Code**: `code/analyze_cross_deciles_trial11.py`
- **Output**: `output/trial11_cross_deciles.csv` (includes Limits and Matrix).

## 6. Trial 12: Combined Indicator Success Rate Lift
**Objective**: Boost the success rate of `per6m-D1` (Anchor) by adding a secondary indicator filter (D1 or D10).
- **Core Finding**: `per6m` (over 54.59) combined with `per3m` (over 34.30) increases success rate from **46.7%** to **51.75%** with high robustness (N=7,314).
- **Code**: `code/analyze_combined_lift_trial12.py`
- **Output**: `output/trial12_combined_lift.csv`

---

## <last>. Project Organization & Resumption tips

**Objective**: Ensure safe session handover.
- **Key Files**:
  - `PROMPTS.md`: Technical recipe (this file).
  - `doc/walkthrough.md`: Detailed report of results, tables, and histograms.
  - `code/`: Contains all trial scripts (`...trial10.py`, `...trial11.py`, etc.).
- **Workflow**:
  1. Verify server connection (`gandalf`).
  2. Read `PROMPTS.md` to pick up the technical thread.
  3. Reference `output/` for the latest CSV data tables.
