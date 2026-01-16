# Longi Project - Context for Claude Code

## Project Structure
```
/home/sm/potentials/longi/
├── start_longi.sh       # Main entry point (conda + full pipeline)
└── app/
    ├── code/            # Python modules
    │   ├── longi.py     # Pipeline orchestrator (includes download)
    │   ├── longi_rsi.py
    │   ├── longi_macd.py
    │   ├── longi_uptrend.py
    │   ├── longi_performance.py
    │   ├── longi_rank.py
    │   ├── longi_medians.py
    │   ├── longi_stepup.py
    │   ├── longi_across.py  # Auto-updates all historical cross-sectional files
    │   └── longi_upload.py
    ├── input/           # Data from Google Drive
    ├── output/          # Results to upload
    └── across/          # Cross-sectional data files
```

## Environment
- **Conda env:** potsystem_env
- **Python:** 3.13
- **Platform:** Ubuntu (headless server, accessed via SSH)
- **Execution:** Scripts run via .sh files

## Data Flow
1. `start_longi.sh` → Activates conda + runs `longi.py`
2. `longi.py` orchestrator:
   - Downloads PotDat.csv and cal.csv from Google Drive to `./input/`
   - Uses shared gd_download module from `/home/sm/potentials/shared/app/code/`
   - Coordinates all processing modules
   - Manages module dependencies (sequential execution)
   - Runs independent modules in parallel (when possible)
   - Handles errors and logging
3. Results go to `./output/`
4. `longi.py` → Uploads to Google Drive (via longi_upload.py)

## Key Scripts
- **longi.py** - Main orchestrator/manager script ✓ IMPLEMENTED
  - Downloads input data using shared gd_download module
  - Manages all longi_*.py processing modules
  - Handles dependencies and parallel execution
  - See "Adding New Modules" section below
- **longi_rsi.py** - RSI14 calculation module ✓ IMPLEMENTED
- **longi_uptrend.py** - Uptrend grading module ✓ IMPLEMENTED
- **longi_upload.py** - Upload results to Google Drive
- **start_longi.sh** - Shell entry point, handles conda activation

## Application Purpose & Data Model

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
    - Empty values ONLY occur from some daynum backward to the oldest daynum (right side of row)
    - Once a cell is empty, ALL subsequent cells to the right (older daynums) are also empty
    - No gaps in the middle: if a cell has data, all cells to its left (newer daynums) also have data
    - Example: A ticker may have data from daynum 2009→1896, then empty from 1895→1543

- **cal.csv** - Date conversion reference
  - Maps daynum → actual dates

### Output Data (Derived Tables)
All derived tables follow same structure as PotDat.csv:
- Same number of rows (one per ticker + features)
- Same column structure (daynum headers)
- Different values (derived metrics instead of prices)

### Derived Tables (Time-Series Format)
All tables follow PotDat.csv structure (rows=tickers, columns=daynums):

1. **longi_rsi.csv** - RSI14 using Wilder's method ✓ IMPLEMENTED
2. **longi_macd.csv** - MACD(4,15,9) indicator ✓ IMPLEMENTED
3. **longi_uptrend.csv** - Uptrend grades (VeryGood/Good/Maybe) ✓ IMPLEMENTED
4. **longi_per1d.csv** - 1-day performance ✓ IMPLEMENTED
5. **longi_per1w.csv** - 1-week performance ✓ IMPLEMENTED
6. **longi_per1m.csv** - 1-month performance ✓ IMPLEMENTED
7. **longi_per3m.csv** - 3-month performance ✓ IMPLEMENTED
8. **longi_per6m.csv** - 6-month performance ✓ IMPLEMENTED
9. **longi_per1y.csv** - 1-year performance ✓ IMPLEMENTED
10. **longi_rank.csv** - Average rank across all performance periods ✓ IMPLEMENTED
11. **longi_median_10d.csv** - 10-day rolling median of rank ✓ IMPLEMENTED
12. **longi_median_20d.csv** - 20-day rolling median of rank ✓ IMPLEMENTED
13. **longi_median_30d.csv** - 30-day rolling median of rank ✓ IMPLEMENTED
14. **longi_median_40d.csv** - 40-day rolling median of rank ✓ IMPLEMENTED
15. **longi_median_50d.csv** - 50-day rolling median of rank ✓ IMPLEMENTED
16. **longi_median_100d.csv** - 100-day rolling median of rank ✓ IMPLEMENTED
17. **longi_stepup.csv** - Step-up count (0-3) as uptrend measure ✓ IMPLEMENTED
18. **longi_spr100d.csv** - Spread to 100-day maximum (% growth needed) ✓ IMPLEMENTED
19. **longi_spr250d.csv** - Spread to 250-day maximum (% growth needed) ✓ IMPLEMENTED
20. **longi_vola20d.csv** - 20-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
21. **longi_vola100d.csv** - 100-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
22. **longi_ma20.csv** - 20-day Simple Moving Average ✓ IMPLEMENTED
23. **longi_ma50.csv** - 50-day Simple Moving Average ✓ IMPLEMENTED
24. **longi_ma200.csv** - 200-day Simple Moving Average ✓ IMPLEMENTED
25. **longi_PdivMA20.csv** - Price / MA20 ratio (>100 = bullish) ✓ IMPLEMENTED
26. **longi_PdivMA50.csv** - Price / MA50 ratio (>100 = bullish) ✓ IMPLEMENTED
27. **longi_PdivMA200.csv** - Price / MA200 ratio (>100 = bullish) ✓ IMPLEMENTED

### Cross-Sectional Data
18. **longi_across_<daynum>.csv** - Cross-sectional view for specific daynum ✓ IMPLEMENTED
    - Rows: Stock tickers
    - Columns: ticker_<daynum> (first column includes daynum), then metrics from all longi_*.csv files
    - Example columns: ticker_2009, rsi, macd_line, uptrend, per1d, rank, median_10d, stepup
    - Generated by longi_across.py (runs last, depends on all other modules)
    - If no daynum specified, uses max daynum from PotDat.csv
    - **Auto-maintenance**: longi_across.py automatically updates all historical files before creating new one
      - Ensures ticker population stays in sync across all cross-sectional files
      - No manual maintenance needed

### Code Architecture

#### longi.py - Pipeline Orchestrator ✓ IMPLEMENTED
Main orchestrator that manages all processing modules with intelligent execution:
- **Dependency management**: Modules with dependencies run sequentially
- **Parallel execution**: Independent modules run concurrently (up to 4 workers)
- **Module registry**: Central registry in MODULES dict (line 33-51)
- **Error handling**: Catches module failures, continues with independent modules
- **Progress tracking**: Real-time status updates with timestamps
- **Validation**: Detects circular dependencies and missing modules

#### longi_rsi.py - RSI14 Calculation Module ✓ IMPLEMENTED
- Implements Wilder's RSI method (14-period)
- Reads PotDat.csv → outputs longi_rsi.csv
- Properly handles left-to-right time scale (newest→oldest)
- IMPORTANT: Wilder's smoothing requires sequential calculation from oldest→newest
  - Implementation reverses array, calculates oldest→newest, then reverses back
  - Output RSI values start at leftmost column (newest daynum, e.g., 2009)

#### longi_uptrend.py - Uptrend Grading Module ✓ IMPLEMENTED
- Grades uptrend strength based on 5 preceding RSI values
- Reads longi_rsi.csv → outputs longi_uptrend.csv
- **Grading rules** (evaluated in order, first match wins):
  1. VeryGood: average(5 RSI) >= 70
  2. Good: minimum(5 RSI) > 50
  3. Maybe: average(5 RSI) > 50
  4. Empty: None of the above
- **Easily extensible**: Add grades by modifying GRADE_RULES list (line 27-32)
- Properly handles time scale: for day at index i, preceding = indices [i+1...i+5]

#### longi_medians.py - Rolling Median Calculation Module ✓ IMPLEMENTED
- Calculates rolling medians over 10d, 20d, 30d, 40d, 50d, and 100d windows
- Reads longi_rank.csv → outputs longi_median_10d.csv, longi_median_20d.csv, longi_median_30d.csv, longi_median_40d.csv, longi_median_50d.csv, longi_median_100d.csv
- Properly handles left-to-right time scale (newest→oldest)
- For day at index i, window uses [i:i+window] (includes current day plus preceding days)
- Last (window-1) columns contain NaN due to insufficient history

#### longi_stepup.py - Step-up Count Module ✓ IMPLEMENTED
- Counts step-ups as measure of uptrend strength
- Reads all six median files (median_10d, median_20d, median_30d, median_40d, median_50d, median_100d) → outputs longi_stepup.csv
- **Step-up logic** (each comparison adds +1):
  1. median_10d > median_20d → +1
  2. median_20d > median_50d → +1
  3. median_50d > median_100d → +1
- Score range: 0-3 (higher = stronger uptrend)
- NaN where any median is missing (first 99 columns from right have insufficient 100d history)
- First 22 days (from left) are usable for correlation with 22-day forward gains

#### longi_across.py - Cross-Sectional Data Extraction Module ✓ IMPLEMENTED
- Extracts data for a specific daynum across all derived tables
- Reads all longi_*.csv files → outputs longi_across_<daynum>.csv to across/ directory
- **AUTOMATIC UPDATE FEATURE**: Before creating the new file, automatically updates all existing historical cross-sectional files to sync with current ticker population
  - Ensures all files stay consistent when tickers are added/removed from PotDat.csv
  - Updates happen automatically every time the module runs (fast process)
  - No separate maintenance script needed
- **Output structure**:
  - Rows: Stock tickers
  - Columns: ticker_<daynum> (first column), then metric names (extracted after-the-underscore from filenames)
  - Example columns: ticker_2009, rsi, macd_line, macd_signal, macd_histogram, uptrend, per1d, per1w, per1m, per3m, per6m, per1y, rank, median_10d, median_20d, median_30d, median_40d, median_50d, median_100d, stepup
- **Usage**: `python3 longi_across.py [daynum]`
  - If daynum specified: extracts that specific daynum
  - If no parameter: uses maximum (newest) daynum from PotDat.csv
- **Dependencies**: Must run last (depends on all other modules)
- Automatically discovers available output files (scans output/ directory)

#### Future longi_*.py Modules
Follow the same pattern:
- Read from input/ or output/ (if depends on another module)
- Write to output/
- Use European CSV format
- Preserve table structure (same rows/columns)
- Return exit code 0 on success, 1 on failure

### Current Status
- ✓ Pipeline orchestrator (longi.py) fully implemented
  - Dependency management working
  - Parallel execution capability ready
  - 18 modules registered: rsi, macd, uptrend, performance, rank, medians, stepup, spr100d, spr250d, vola20d, vola100d, ma20, ma50, ma200, PdivMA20, PdivMA50, PdivMA200, across
- ✓ longi_rsi.py fully implemented and tested
- ✓ longi_macd.py fully implemented and tested
- ✓ longi_uptrend.py fully implemented and tested
- ✓ longi_performance.py fully implemented and tested
- ✓ longi_rank.py fully implemented and tested
- ✓ longi_medians.py fully implemented
  - Outputs: longi_median_10d.csv, longi_median_20d.csv, longi_median_30d.csv, longi_median_40d.csv, longi_median_50d.csv, longi_median_100d.csv
- ✓ longi_stepup.py fully implemented
  - Outputs: longi_stepup.csv (step-up counts 0-3)
- ✓ longi_spr100d.py fully implemented
  - Formula: ((max_100d - current_price) / current_price) * 100
- ✓ longi_spr250d.py fully implemented
  - Formula: ((max_250d - current_price) / current_price) * 100
- ✓ longi_vola20d.py fully implemented
  - Returns-based volatility: stdev(daily_returns_over_20_days)
- ✓ longi_vola100d.py fully implemented
  - Returns-based volatility: stdev(daily_returns_over_100_days)
- ✓ longi_ma20.py, longi_ma50.py, longi_ma200.py fully implemented
  - Simple Moving Averages (SMA) for 20, 50, and 200 days
- ✓ longi_PdivMA20.py, longi_PdivMA50.py, longi_PdivMA200.py fully implemented
  - Price/MA ratios (>100 = price above MA = bullish)
  - Dependencies: require corresponding MA module
- ✓ longi_across.py fully implemented
  - Outputs: longi_across_<daynum>.csv (cross-sectional view with ticker_<daynum> column)
  - Runs last (depends on all other modules)
  - Automatically updates all historical cross-sectional files before creating new one
  - Ensures ticker population stays in sync across all files
- ✓ longi_upload.py fully implemented
  - Uses rclone sync to upload output/ and across/ directories
  - Cyclical architecture for easy addition of new upload targets
  - Excludes .txt and .gdoc files from sync
  - Destination folders cleaned to match source (old files removed)
- GDrive integration working (shared gd_download.py, longi_upload.py)
- Shared modules in /home/sm/potentials/shared/app/code/

## Development Notes
- VS Code connected via Remote-SSH from Windows
- Danish keyboard layout
- Claude Code shortcut: Ctrl+Alt+C
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
Edit `code/longi.py` and add to MODULES dict (line ~35):
```python
MODULES: Dict[str, Module] = {
    "rsi": Module(...),
    "uptrend": Module(...),
    "xxx": Module(                    # <-- Add your module here
        name="Your Module Name",
        script="longi_xxx.py",
        depends_on=["rsi"],           # or [] if independent
    ),
}
```

### 3. Dependencies
- **Independent modules** (depends_on=[]): Run in parallel with other independent modules
- **Dependent modules** (depends_on=["rsi"]): Run after dependencies complete
- **Multiple dependencies** (depends_on=["rsi", "uptrend"]): Run after all dependencies complete

### 4. Execution
Simply run `python3 code/longi.py` - the orchestrator handles everything:
- Validates dependencies (no circular refs, all deps exist)
- Executes modules in correct order
- Runs independent modules in parallel (up to 4 workers)
- Reports errors without stopping independent modules

## Coding Standards
- Use type hints in Python
- Keep modules focused and testable
- Log to stdout (longi.py captures it, start_longi.sh logs to /home/sm/start_longi.log)
- Exit codes matter - return 0 for success, 1 for failure
- Handle European CSV format correctly (sep=';', decimal=',')
- Preserve table structure across transformations (same rows/columns, different values)

## Unit testing
- Individual modules can be testet for syntax errors by running from CLI: python3 longi_XX.py
- Production-correct testing requires dependency order which is only obtained by running longi.py