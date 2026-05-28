# Longi Project - Shared Context

## Project Structure
```
/home/sm/potentials/longi/
├── start_longi.sh       # Main entry point (conda + full pipeline)
├── fetch_input.sh       # Input data provider (downloads from GDrive)
├── PROJECT_EXP.md       # Experiment index and short-lived notes
└── app/
    ├── code/            # Python modules
    │   ├── longi.py     # Pipeline orchestrator
    │   ├── longi_rsi.py
    │   ├── longi_macd.py
    │   ├── longi_performance.py
    │   ├── longi_rank.py
    │   ├── longi_medians.py
    │   ├── longi_stepup.py
    │   ├── longi_grp_*.py  # Aggregation modules (GICS, Sector2, etc.)
    │   ├── aux_across.py  # Auto-updates all historical cross-sectional files
    │   ├── aux_deciles.py # Global decile boundaries for all indicators
    │   ├── aux_win-loss.py  # Daily per-ticker Win/Loss production scoring
    │   ├── QA_win-loss.py  # QA metrics for Win/Loss models
    │   ├── aux_win_loss_shared.py  # Shared Win/Loss modeling utilities
    │   ├── aux_upload.py  # Upload results to Google Drive
    │   └── aux_shared.py  # Shared utility functions
    ├── code_exp/        # Experimental scripts and prototype modules
    ├── input/           # Data from Google Drive
    ├── output/          # Individual stock derived tables
    │   └── exp/         # Experimental output artifacts
    ├── output_grp/      # Aggregated tables (grouped by attributes)
    └── across/          # Cross-sectional data files
```

## Environment
- **Conda env:** potsystem_env
- **Python:** 3.13
- **Platform:** Ubuntu (headless server, accessed via SSH)
- **Execution:** Scripts run via .sh files

## Data Flow
1. `start_longi.sh` -> Activates conda, runs `fetch_input.sh`, then runs `longi.py`
2. `fetch_input.sh` -> Downloads input files from Google Drive to `./app/input/`:
   - PotDat.csv (stock price data)
   - Stamdata.csv (stock attributes/metadata)
   - Cal.csv (date conversion reference)
   - Uses rclone to sync from GoogleDrive:PotSystem/repositoryRTBI/
3. `longi.py` orchestrator:
   - Coordinates all processing modules
   - Manages module dependencies (sequential execution)
   - Runs independent modules in parallel (when possible)
   - Handles errors and logging
4. Results go to `./app/output/` (individual stock tables + operational outputs) and `./app/output_grp/` (aggregated tables)
   - Includes daily `aux_win-loss.csv` (alphabetical ticker order) from `aux_win-loss.py`
   - QA artifacts go to `./app/output/QA/` when `QA_win-loss.py` is run manually
5. `longi.py` -> Uploads to Google Drive (via aux_upload.py)

## Key Scripts
- **fetch_input.sh** - Input data provider (implemented)
  - Downloads PotDat.csv, Stamdata.csv, Cal.csv from Google Drive
  - Uses rclone with GoogleDrive:PotSystem/repositoryRTBI/
  - Called by start_longi.sh before running longi.py
- **longi.py** - Main orchestrator/manager script (implemented)
  - Manages all longi_*.py processing modules
  - Handles dependencies and parallel execution
  - See "Adding New Modules" section below
- **longi_rsi.py** - RSI14 calculation module (implemented)
- **aux_upload.py** - Upload results to Google Drive (implemented)
  - Syncs output/, output_grp/, and across/ directories
  - Uses rclone sync to GoogleDrive:PotSystem/repositoryRTBI/Longi/
- **aux_win-loss.py** - Daily Win/Loss production scorer (implemented)
  - Creates `app/output/aux_win-loss.csv`
  - Uses per-ticker multinomial models for both targets:
    - 20d (`future_gain20d.csv`, Win>6, Loss<0)
    - 50d (`future_gain50d.csv`, Win>10, Loss<0)
  - Output is sorted alphabetically by ticker and excludes caret-prefixed tickers
- **QA_win-loss.py** - Win/Loss quality assurance runner (implemented)
  - Writes QA artifacts to `app/output/QA/`
  - Focuses on validity and error-rate diagnostics (split-level + ticker-level)
  - Intended for periodic checks when adding tickers/features or retuning setup
- **start_longi.sh** - Shell entry point, handles conda activation

## Application Purpose and Data Model

### Input Data
- **PotDat.csv** - Main stock price data
  - Row structure: First column = ticker, subsequent columns = stock prices
  - Column headers: daynum (proxy for date, see cal.csv for conversion)
  - **Time scale**: Column order is **left-to-right = newest-to-oldest**
    - Leftmost columns: newest data (e.g., 2009, 2008, 2007...)
    - Rightmost columns: oldest data (e.g., 1545, 1544, 1543)
    - Array index [0] = newest, [n-1] = oldest
  - European CSV format (`;` separator, `,` decimal)
  - **Empty value pattern**: Empty cells represent "stock did not exist yet" for historical periods
    - Empty values only occur from some daynum backward to the oldest daynum (right side of row)
    - Once a cell is empty, all subsequent cells to the right (older daynums) are also empty
    - No gaps in the middle: if a cell has data, all cells to its left (newer daynums) also have data
    - Example: A ticker may have data from daynum 2009->1896, then empty from 1895->1543

- **cal.csv** - Date conversion reference
  - Maps daynum -> actual dates

- **Stamdata.csv** - Stock attributes/metadata
  - Row structure: First column = ticker, subsequent columns = stock attributes
  - Key columns: Name, Sector, Homeland, GICS, etc.
  - European CSV format (`;` separator, `,` decimal)
  - Used for grouping/aggregating stocks by attributes

### Output Data (Derived Tables)
All derived tables follow same structure as PotDat.csv:
- Same number of rows (one per ticker + features)
- Same column structure (daynum headers)
- Different values (derived metrics instead of prices)

### Derived Tables (Time-Series Format)
All tables follow PotDat.csv structure (rows=tickers, columns=daynums):

1. **longi_rsi.csv** - RSI14 using Wilder's method (implemented)
2. **longi_macd.csv** - MACD(4,15,9) indicator (implemented)
3. **longi_macd_Z.csv** - MACD histogram zero-crossings (ZOP/ZNED) (implemented)
4. **longi_per1d.csv** - 1-day performance (implemented)
5. **longi_per1w.csv** - 1-week performance (implemented)
6. **longi_per1m.csv** - 1-month performance (implemented)
7. **longi_per3m.csv** - 3-month performance (implemented)
8. **longi_per6m.csv** - 6-month performance (implemented)
9. **longi_per1y.csv** - 1-year performance (implemented)
10. **longi_rank.csv** - Average rank across all performance periods (implemented)
11. **longi_median_10d.csv** - 10-day rolling median of rank (implemented)
12. **longi_median_20d.csv** - 20-day rolling median of rank (implemented)
13. **longi_median_30d.csv** - 30-day rolling median of rank (implemented)
14. **longi_median_40d.csv** - 40-day rolling median of rank (implemented)
15. **longi_median_50d.csv** - 50-day rolling median of rank (implemented)
16. **longi_median_100d.csv** - 100-day rolling median of rank (implemented)
17. **longi_stepup.csv** - Step-up count (0-3) as uptrend measure (implemented)
18. **longi_spr100d.csv** - Spread to 100-day maximum (% growth needed) (implemented)
19. **longi_spr250d.csv** - Spread to 250-day maximum (% growth needed) (implemented)
20. **longi_vola20d.csv** - 20-day volatility (returns-based stdev in %) (implemented)
21. **longi_vola100d.csv** - 100-day volatility (returns-based stdev in %) (implemented)
22. **longi_ma20.csv** - 20-day Simple Moving Average (implemented)
23. **longi_ma50.csv** - 50-day Simple Moving Average (implemented)
24. **longi_ma200.csv** - 200-day Simple Moving Average (implemented)
25. **longi_PdivMA20.csv** - Price / MA20 ratio (>100 = bullish) (implemented)
26. **longi_PdivMA50.csv** - Price / MA50 ratio (>100 = bullish) (implemented)
27. **longi_PdivMA200.csv** - Price / MA200 ratio (>100 = bullish) (implemented)
28. **longi_sh3m.csv** - 3-month Sharpe ratio (return/volatility over 67 days) (implemented)
29. **longi_sh6m.csv** - 6-month Sharpe ratio (return/volatility over 133 days) (implemented)
30. **longi_sh1yr.csv** - 1-year Sharpe ratio (return/volatility over 265 days) (implemented)
31. **longi_trump.csv** - Price index relative to daynum 1863 (2 Apr 2025, Trump tariff day); 1,0 at origin, empty for older daynums (implemented)
32. **longi_iran.csv** - Price index relative to daynum 2094 (27 Feb 2026, last day before Iran War); 1,0 at origin, empty for older daynums (implemented)

### Aggregated Tables (Grouped by Stock Attributes)
Output directory: `app/output_grp/`

**Format:** `longi_grp_{Column}_{Period}.csv`
- Rows: Unique values from grouping column in Stamdata.csv
- Columns: All daynums from corresponding performance file
- Values: Sector-averaged growth rates using formula: `average(1 + growth_rate) - 1`
- Aggregates individual stock growth by specified attribute for trend analysis

**Available aggregations:**
- **longi_grp_GICS_1yr.csv** 1 year growth per each of 13 GICS sectors: Basi, C-Di, C-St, Ener, Fina, Heal, Index, Indu, REIT, Tech, Tele, Util, na (implemented)
- **longi_grp_Sector2_1yr.csv** 1 year growth rates per each of 56 Sector2 values (implemented)
- Future: Sector2_3m, Sector2_6m, Sgrp1_1yr, Zone_1yr, GrType_1yr, etc.

### Cross-Sectional Data
Output directory: `app/across/`

**longi_across_<daynum>.csv** - Cross-sectional view for specific daynum (implemented)
- Rows: Stock tickers
- Columns: ticker_<daynum> (first column includes daynum), then metrics from all longi_*.csv files, plus sector aggregates
- Example columns: ticker_2009, rsi, macd_line, per1d, rank, median_10d, stepup, **GICS_1yr, Sector2_1yr**
- **GICS_1yr**: Sector-aggregated 1-year performance for the stock's GICS sector
- **Sector2_1yr**: Sector-aggregated 1-year performance for the stock's Sector2
- Generated by aux_across.py (runs last, depends on all other modules)
- If no daynum specified, uses max daynum from PotDat.csv
- **Auto-maintenance**: aux_across.py automatically updates all historical files before creating new one
  - Ensures ticker population stays in sync across all cross-sectional files
  - No manual maintenance needed

### Operational Outputs
Output directory: `app/output/`

- **aux_win-loss.csv** - Daily production Win/Loss probabilities (implemented)
  - Rows: All non-caret tickers from PotDat universe
  - Columns: `daynum_in_case`, ticker, 20d label/probabilities, 50d label/probabilities
  - Sort order: Alphabetical by ticker
  - Generated by `aux_win-loss.py` and included in `longi.py` pipeline

Output directory: `app/output/QA/`

- **qa_win-loss_*.csv/json** - QA diagnostics for Win/Loss models (implemented)
  - Split-level metrics (accuracy + error counts/rates)
  - Ticker-level validity and error profiles
  - Optional row-level predictions for inspection
  - Generated on demand by `QA_win-loss.py` (not a daily pipeline module)

## Code Architecture

### longi.py - Pipeline Orchestrator (implemented)
Main orchestrator that manages all processing modules with intelligent execution:
- Dependency management: Modules with dependencies run sequentially
- Parallel execution: Independent modules run concurrently (up to 4 workers)
- Module registry: Central registry in MODULES dict
- Error handling: Catches module failures, continues with independent modules
- Progress tracking: Real-time status updates with timestamps
- Validation: Detects circular dependencies and missing modules

### longi_rsi.py - RSI14 Calculation Module (implemented)
- Implements Wilder's RSI method (14-period)
- Reads PotDat.csv -> outputs longi_rsi.csv
- Properly handles left-to-right time scale (newest->oldest)
- Important: Wilder's smoothing requires sequential calculation from oldest->newest
  - Implementation reverses array, calculates oldest->newest, then reverses back
  - Output RSI values start at leftmost column (newest daynum, e.g., 2009)

### longi_macd_Z.py - MACD Zero-Crossing Detection Module (implemented)
- Detects transitions in MACD histogram values across time
- Reads longi_macd_histogram.csv -> outputs longi_macd_Z.csv
- Zero-crossing detection:
  - **ZOP**: Negative -> Positive transition
  - **ZNED**: Positive -> Negative transition
  - All other values remain empty
- Output structure: Same as input (rows=tickers, columns=daynums)
- Dependencies: Requires longi_macd.csv (MACD histogram output)

### longi_medians.py - Rolling Median Calculation Module (implemented)
- Calculates rolling medians over 10d, 20d, 30d, 40d, 50d, and 100d windows
- Reads longi_rank.csv -> outputs longi_median_10d.csv, longi_median_20d.csv, longi_median_30d.csv, longi_median_40d.csv, longi_median_50d.csv, longi_median_100d.csv
- Properly handles left-to-right time scale (newest->oldest)
- For day at index i, window uses [i:i+window] (includes current day plus preceding days)
- Last (window-1) columns contain NaN due to insufficient history

### longi_stepup.py - Step-up Count Module (implemented)
- Counts step-ups as measure of uptrend strength
- Reads all six median files (median_10d, median_20d, median_30d, median_40d, median_50d, median_100d) -> outputs longi_stepup.csv
- **Step-up logic** (each comparison adds +1):
  1. median_10d > median_20d -> +1
  2. median_20d > median_50d -> +1
  3. median_50d > median_100d -> +1
- Score range: 0-3 (higher = stronger uptrend)
- NaN where any median is missing (first 99 columns from right have insufficient 100d history)
- First 22 days (from left) are usable for correlation with 22-day forward gains

### aux_across.py - Cross-Sectional Data Extraction Module (implemented)
- Extracts data for a specific daynum across all derived tables
- Reads all longi_*.csv files -> outputs longi_across_<daynum>.csv to across/ directory
- Automatic update feature: before creating the new file, updates all existing historical cross-sectional files to sync with current ticker population
  - Ensures all files stay consistent when tickers are added/removed from PotDat.csv
  - Updates happen automatically every time the module runs
  - No separate maintenance script needed
- Output structure:
  - Rows: Stock tickers
  - Columns: ticker_<daynum> (first column), then metric names (extracted after-the-underscore from filenames), plus sector aggregates
  - Includes: GICS_1yr, Sector2_1yr
- Usage: `python3 aux_across.py [daynum]`
- Dependencies: Must run last (depends on all other modules including grp_GICS_1yr and grp_Sector2_1yr)

### aux_deciles.py - Global Decile Boundary Calculator (implemented)
- Calculates global decile boundaries for each numeric indicator
- Reads all longi_*.csv files from output/ and output_grp/ -> outputs aux_deciles.csv to output/
- Global: pools all values across all tickers and all daynums per indicator
- Output structure:
  - Columns: Indicator, Decile (1-10), UpperLimit, LowerLimit
  - One row per indicator-decile pair
  - Decile 1 = lowest values, Decile 10 = highest values
- Skips non-numeric files (macd_Z) automatically
- Dependencies: Runs after "across"

### aux_win-loss.py - Daily Win/Loss Production Module (implemented)
- Produces one operational scoring file each run: `app/output/aux_win-loss.csv`
- Scores newest available daynum from PotDat by default (or explicit daynum argument)
- Runs per-ticker multinomial models with minimum history guard (`min_stock_samples=150`)
- Includes both:
  - 20d classes (`Win>6`, `Loss<0`, otherwise `Nothing`)
  - 50d classes (`Win>10`, `Loss<0`, otherwise `Nothing`)
- Dependencies in `longi.py`: required feature modules + `future_gain20d` + `future_gain50d`

### QA_win-loss.py - Win/Loss Quality Assurance Module (implemented)
- Runs walk-forward per-stock QA on newest test daynums (default 10)
- Writes diagnostics to `app/output/QA/`:
  - `qa_win-loss_<target>_metrics_by_split.csv`
  - `qa_win-loss_<target>_ticker_quality.csv`
  - `qa_win-loss_<target>_summary.json`
  - optional: `qa_win-loss_<target>_predictions.csv`
- Intended for operational quality checks after schema or feature-universe changes

### longi_grp_GICS_1yr.py - GICS Sector Aggregation Module (implemented)
- Calculates sector-aggregated 1-year growth rates grouped by GICS
- Reads Stamdata.csv (ticker->GICS mapping) and longi_per1y.csv -> outputs longi_grp_GICS_1yr.csv
- Output structure:
  - Rows: Unique GICS sector values (13 sectors including Index, na)
  - Columns: All daynums from longi_per1y.csv
  - Values: Sector-averaged growth rates
- Aggregation formula: `average(1 + growth_rate) - 1`
- Dependencies: Requires performance module (longi_per1y.csv)
- Extensible: Can be adapted for other grouping attributes (Sector, Homeland, etc.)

### longi_trump.py - Trump Tariff Index Module (implemented)
- Price index relative to daynum 1863 (2 April 2025, Trump tariff announcement)
- Reads PotDat.csv -> outputs longi_trump.csv
- Index = price[daynum X] / price[daynum 1863]; value is 1,0 at origin
- Daynums older than 1863: empty. Tickers with no price at origin: entire row empty

### longi_iran.py - Iran War Index Module (implemented)
- Price index relative to daynum 2094 (27 February 2026, last ordinary trading day before Iran War)
- Reads PotDat.csv -> outputs longi_iran.csv
- Index = price[daynum X] / price[daynum 2094]; value is 1,0 at origin
- Daynums older than 2094: empty. Tickers with no price at origin: entire row empty

### Future longi_*.py Modules
Follow the same pattern:
- Read from input/ or output/ (if depends on another module)
- Write to output/
- Use European CSV format
- Preserve table structure (same rows/columns)
- Return exit code 0 on success, 1 on failure

## Current Status
- Pipeline orchestrator (longi.py) fully implemented
  - Dependency management working
  - Parallel execution capability ready
  - Module registry includes full indicator stack plus operational module `win_loss` (`aux_win-loss.py`)
- longi_rsi.py fully implemented and tested
- longi_macd.py fully implemented and tested
- longi_macd_Z.py fully implemented and tested
- longi_performance.py fully implemented and tested
- longi_rank.py fully implemented and tested
- longi_medians.py fully implemented
- longi_stepup.py fully implemented
- longi_spr100d.py fully implemented
- longi_spr250d.py fully implemented
- longi_vola20d.py fully implemented
- longi_vola100d.py fully implemented
- longi_ma20.py, longi_ma50.py, longi_ma200.py fully implemented
- longi_PdivMA20.py, longi_PdivMA50.py, longi_PdivMA200.py fully implemented
- longi_sh3m.py, longi_sh6m.py, longi_sh1yr.py fully implemented
- longi_trump.py fully implemented (Trump tariff index, origin daynum 1863)
- longi_iran.py fully implemented (Iran War index, origin daynum 2094)
- longi_grp_GICS_1yr.py fully implemented
- longi_grp_Sector2_1yr.py fully implemented
- aux_across.py fully implemented
- aux_deciles.py fully implemented
- aux_win-loss.py fully implemented
- QA_win-loss.py fully implemented
- aux_upload.py fully implemented
- GDrive integration working (shared gd_download.py, aux_upload.py)
- Shared modules in /home/sm/potentials/shared/app/code/

## Development Notes
- VS Code connected via Remote-SSH from Windows
- Danish keyboard layout
- Terminal shortcut: Ctrl+Æ
- CSV files are European style with separator: semicolon, decimal: comma, thousands: not used

## Adding New Modules to Pipeline

To add a new indicator calculation module to the pipeline:

### 1. Create the Module File
Create `code/longi_xxx.py` following the pattern:
```python
# Read from input/PotDat.csv or output/longi_*.csv
# Process data
# Write to output/longi_xxx.csv
# Return exit code 0 on success, 1 on failure
```

### 2. Register in longi.py
Edit `code/longi.py` and add to MODULES dict:
```python
MODULES: Dict[str, Module] = {
    "rsi": Module(...),
    "xxx": Module(
        name="Your Module Name",
        script="longi_xxx.py",
        depends_on=["rsi"],
    ),
}
```

### 3. Dependencies
- **Independent modules** (`depends_on=[]`): Run in parallel with other independent modules
- **Dependent modules** (`depends_on=["rsi"]`): Run after dependencies complete
- **Multiple dependencies** (`depends_on=["rsi", "macd"]`): Run after all dependencies complete

### 4. Execution
Run `python3 code/longi.py`:
- Validates dependencies (no circular refs, all deps exist)
- Executes modules in correct order
- Runs independent modules in parallel (up to 4 workers)
- Reports errors without stopping independent modules

## Coding Standards
- Use type hints in Python
- Keep modules focused and testable
- Log to stdout (longi.py captures it, start_longi.sh logs to /home/sm/start_longi.log)
- Exit codes matter (0 success, 1 failure)
- Handle European CSV format correctly (`sep=';'`, `decimal=','`)
- Preserve table structure across transformations (same rows/columns, different values)

## Logging Format
Hierarchical log markers for readable output in start_longi.log:
- `===` top level: Wave starts in pipeline orchestrator
- `---` second level: Python module starts (added by orchestrator)
- `**` notable status: Final pipeline status
- `*` shell script markers
- Plain text for all other output

Important: Individual longi_*.py modules should not use `===` or `---` markers in their output. The orchestrator wraps their output with `---` automatically.

## Unit Testing
- Individual modules can be syntax-tested via CLI: `python3 longi_XX.py`
- Production-correct testing requires dependency order obtained by running `longi.py`
