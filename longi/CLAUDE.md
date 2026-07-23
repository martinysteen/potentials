# Longi Project - Context for Claude Code

## Project Structure
```
/home/sm/potentials/longi/
├── start_longi.sh       # Main entry point (conda + full pipeline)
├── fetch_input.sh       # Input data provider (downloads from GDrive)
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
    │   ├── longi_across.py # Cross-sectional data extraction module
    │   └── longi_upload.py
    ├── input/           # Data from Google Drive
    └── output/          # Individual stock derived tables + aggregated + cross-sectional snapshot
```

## Environment
- **Conda env:** potsystem_env
- **Python:** 3.13
- **Platform:** Ubuntu (headless server, accessed via SSH)
- **Execution:** Scripts run via .sh files

## Data Flow
1. `start_longi.sh` → Activates conda, runs `fetch_input.sh`, then runs `longi.py`
2. `fetch_input.sh` → Downloads input files from Google Drive to `./app/input/`:
   - PotDat.csv (stock price data)
   - Stamdata.csv (stock attributes/metadata)
   - Cal.csv (date conversion reference)
   - Uses rclone to sync from GoogleDrive:PotSystem/repositoryRTBI/
3. `longi.py` orchestrator:
   - Coordinates all processing modules
   - Manages module dependencies (sequential execution)
   - Runs independent modules in parallel (when possible)
   - Handles errors and logging
4. Results go to `./app/output/` (all derived tables: individual stock, aggregated, and cross-sectional snapshot)
5. `longi.py` → Uploads to Google Drive (via longi_upload.py)

## Key Scripts
- **fetch_input.sh** - Input data provider ✓ IMPLEMENTED
  - Downloads PotDat.csv, Stamdata.csv, Cal.csv from Google Drive
  - Uses rclone with GoogleDrive:PotSystem/repositoryRTBI/
  - Called by start_longi.sh before running longi.py
- **longi.py** - Main orchestrator/manager script ✓ IMPLEMENTED
  - Manages all longi_*.py processing modules
  - Handles dependencies and parallel execution
  - See "Adding New Modules" section below
- **longi_rsi.py** - RSI14 calculation module ✓ IMPLEMENTED
- **longi_upload.py** - Upload results to Google Drive ✓ IMPLEMENTED
  - Syncs output/ directory
  - Uses rclone sync to GoogleDrive:PotSystem/repositoryRTBI/Longi/
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

1. **longi_price.csv** - Exact copy of PotDat.csv (snapshot of prices used for this pipeline run) ✓ IMPLEMENTED
2. **longi_rsi.csv** - RSI14 using Wilder's method ✓ IMPLEMENTED
3. **longi_macd.csv** - MACD(4,15,9) indicator ✓ IMPLEMENTED
4. **longi_macd_Z.csv** - MACD histogram zero-crossings (ZOP/ZNED) ✓ IMPLEMENTED
5. **longi_per1d.csv** - 1-day performance ✓ IMPLEMENTED
6. **longi_per1w.csv** - 1-week performance ✓ IMPLEMENTED
7. **longi_per1m.csv** - 1-month performance ✓ IMPLEMENTED
8. **longi_per3m.csv** - 3-month performance ✓ IMPLEMENTED
9. **longi_per6m.csv** - 6-month performance ✓ IMPLEMENTED
10. **longi_per1y.csv** - 1-year performance ✓ IMPLEMENTED
11. **longi_rank.csv** - Average rank across all performance periods ✓ IMPLEMENTED
12. **longi_median_10d.csv** - 10-day rolling median of rank ✓ IMPLEMENTED
13. **longi_median_20d.csv** - 20-day rolling median of rank ✓ IMPLEMENTED
14. **longi_median_30d.csv** - 30-day rolling median of rank ✓ IMPLEMENTED
15. **longi_median_40d.csv** - 40-day rolling median of rank ✓ IMPLEMENTED
16. **longi_median_50d.csv** - 50-day rolling median of rank ✓ IMPLEMENTED
17. **longi_median_100d.csv** - 100-day rolling median of rank ✓ IMPLEMENTED
18. **longi_stepup.csv** - Step-up count (0-3) as uptrend measure ✓ IMPLEMENTED
19. **longi_spr100d.csv** - Spread to 100-day maximum (% growth needed) ✓ IMPLEMENTED
20. **longi_spr250d.csv** - Spread to 250-day maximum (% growth needed) ✓ IMPLEMENTED
21. **longi_vola20d.csv** - 20-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
22. **longi_vola100d.csv** - 100-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
23. **longi_ma10.csv** - 10-day Simple Moving Average ✓ IMPLEMENTED
24. **longi_ma20.csv** - 20-day Simple Moving Average ✓ IMPLEMENTED
25. **longi_ma50.csv** - 50-day Simple Moving Average ✓ IMPLEMENTED
26. **longi_ma200.csv** - 200-day Simple Moving Average ✓ IMPLEMENTED
27. **longi_PdivMA20.csv** - Price / MA20 ratio (>100 = bullish) ✓ IMPLEMENTED
28. **longi_PdivMA50.csv** - Price / MA50 ratio (>100 = bullish) ✓ IMPLEMENTED
29. **longi_PdivMA200.csv** - Price / MA200 ratio (>100 = bullish) ✓ IMPLEMENTED
30. **longi_sh3m.csv** - 3-month Sharpe ratio (return/volatility over 67 days) ✓ IMPLEMENTED
31. **longi_sh6m.csv** - 6-month Sharpe ratio (return/volatility over 133 days) ✓ IMPLEMENTED
32. **longi_sh1yr.csv** - 1-year Sharpe ratio (return/volatility over 265 days) ✓ IMPLEMENTED
33. **longi_quot1020.csv** - MA10/MA20 quotient ×100, momentum speed (>100 = accelerating) ✓ IMPLEMENTED
34. **longi_quot2050.csv** - MA20/MA50 quotient ×100, momentum speed (>100 = accelerating) ✓ IMPLEMENTED

### Aggregated Tables (Grouped by Stock Attributes)
Output directory: `app/output/` (same as individual stock tables)

**Format:** `longi_grp_{Column}_{Period}.csv`
- Rows: Unique values from grouping column in Stamdata.csv
- Columns: All daynums from corresponding performance file
- Values: Sector-averaged growth rates using formula: `average(1 + growth_rate) - 1`
- Aggregates individual stock growth by specified attribute for trend analysis

**Available aggregations:**
- **longi_grp_GICS_1yr.csv** (13 GICS sectors: Basi, C-Di, C-St, Ener, Fina, Heal, Index, Indu, REIT, Tech, Tele, Util, na) ✓ IMPLEMENTED
- **longi_grp_Sector2_1yr.csv** (56 Sector2 values) ✓ IMPLEMENTED
- **longi_grp_GICS_3m.csv** - GICS sector-aggregated 3-month growth ✓ IMPLEMENTED
- **longi_grp_Sector2_3m.csv** - Sector2-aggregated 3-month growth ✓ IMPLEMENTED

### Cross-Sectional Data
Output directory: `app/output/`

**across_<daynum>.csv** - Cross-sectional view for most recent daynum ✓ IMPLEMENTED
    - Rows: Stock tickers
    - Columns: ticker_<daynum> (first column includes daynum), then metrics from all longi_*.csv files, plus sector aggregates
    - Example columns: ticker_2009, rsi, macd_line, per1d, rank, median_10d, stepup, **GICS_1yr, Sector2_1yr**
    - **GICS_1yr**: Sector-aggregated 1-year performance for the stock's GICS sector (enables sector-relative analysis)
    - **Sector2_1yr**: Sector-aggregated 1-year performance for the stock's Sector2 (enables sector-relative analysis)
    - Generated by longi.py calling longi_across.make_across() (runs last, depends on all other modules)
    - Uses maximum (newest) daynum from PotDat.csv
    - **Manual historical generation**: Use longi_across.make_across(daynum, target_folder) to create backfilled files for specific daynums
      - Example: `python3 -c "from longi_across import make_across; make_across(1950, './historical/')"`
      - Existing across_*.csv files in target folder are deleted before creating new ones

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

#### longi_macd_Z.py - MACD Zero-Crossing Detection Module ✓ IMPLEMENTED
- Detects transitions in MACD histogram values across time
- Reads longi_macd_histogram.csv → outputs longi_macd_Z.csv
- **Zero-crossing detection**:
  - **ZOP**: Negative → Positive transition (zero crossing to positive)
  - **ZNED**: Positive → Negative transition (zero crossing negative)
  - All other values remain empty
- **Output structure**: Same as input (rows=tickers, columns=daynums)
- **Dependencies**: Requires longi_macd.csv (MACD histogram output)

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
- Contains `make_across(daynum, target_folder=None)` function
  - Creates cross-sectional snapshot for specified daynum
  - Defaults to app/output if target_folder not specified
  - Deletes existing across_*.csv files in target_folder before creating new one
  - Returns exit code 0 on success, 1 on failure
- **longi.py integration**:
  - Calls longi_across.make_across(max_daynum, app/output) directly (not via subprocess)
  - Runs after all other dependencies complete
  - Only creates one file per daily run (the most recent daynum)
- **Output structure**:
  - Rows: Stock tickers
  - Columns: ticker_<daynum> (first column), then metric names (extracted from filenames), plus sector aggregates
  - Example columns: ticker_2009, rsi, macd_line, macd_signal, macd_histogram, per1d, per1w, per1m, per3m, per6m, per1y, rank, median_10d, median_20d, median_30d, median_40d, median_50d, median_100d, stepup, **GICS_1yr, Sector2_1yr**
  - **GICS_1yr**: Adds sector-aggregated 1-year performance for each stock's GICS sector
  - **Sector2_1yr**: Adds sector-aggregated 1-year performance for each stock's Sector2
  - Enables sector-relative analysis (e.g., stock per1y vs. sector GICS_1yr/Sector2_1yr)
- **Manual historical generation**: Use make_across() function for creating backfilled files for specific daynums
  - From Python: `from longi_across import make_across; make_across(1950, "/path/to/folder")`
  - From CLI: `python3 longi_across.py 1950 --target-folder=/path/to/folder`
  - Accepts optional daynum and --target-folder parameters when run as script
- **Dependencies**: Must run last (depends on all other modules including grp_GICS_1yr and grp_Sector2_1yr)

#### longi_grp_GICS_1yr.py - GICS Sector Aggregation Module ✓ IMPLEMENTED
- Calculates sector-aggregated 1-year growth rates grouped by GICS
- Reads Stamdata.csv (ticker→GICS mapping) and longi_per1y.csv → outputs longi_grp_GICS_1yr.csv
- **Output structure**:
  - Rows: Unique GICS sector values (13 sectors including Index, na)
  - Columns: All daynums from longi_per1y.csv
  - Values: Sector-averaged growth rates
- **Aggregation formula**: `average(1 + growth_rate) - 1`
  - Converts growth rates to multipliers (1 + r)
  - Averages across all stocks in sector
  - Converts back to growth rate (avg - 1)
  - This gives proper compounded average return for the sector
- **Dependencies**: Requires performance module (longi_per1y.csv)
- **Extensible**: Can be adapted for other grouping attributes (Sector, Homeland, etc.)

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
  - 38 modules registered: price, rsi, macd, performance, rank, medians, stepup, spr100d, spr250d, vola20d, vola100d, ma10, ma20, ma50, ma200, PdivMA20, PdivMA50, PdivMA200, quot1020, quot2050, grp_GICS_1yr, grp_Sector2_1yr, grp_GICS_3m, grp_Sector2_3m, coreindex, coreindexRSI, beta3m, beta6m, beta1yr, trump, iran, macd_Z, sh3m, sh6m, sh1yr, future_gain20d, future_gain50d, across
- ✓ longi_price.py fully implemented
  - Outputs: longi_price.csv (byte-exact copy of PotDat.csv via shutil.copyfile, no reformatting)
  - Purpose: (a) reference raw price data under the longi_ naming convention, (b) record the exact PotDat.csv snapshot used to derive all longi_*.csv outputs for this run, since PotDat.csv is updated asynchronously relative to them
  - Independent module (no dependencies, nothing else depends on it)
- ✓ longi_rsi.py fully implemented and tested
- ✓ longi_macd.py fully implemented and tested
- ✓ longi_macd_Z.py fully implemented and tested
  - Outputs: longi_macd_Z.csv (MACD histogram zero-crossings)
  - Detects ZOP (negative→positive) and ZNED (positive→negative) transitions
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
- ✓ longi_ma10.py, longi_ma20.py, longi_ma50.py, longi_ma200.py fully implemented
  - Simple Moving Averages (SMA) for 10, 20, 50, and 200 days
- ✓ longi_PdivMA20.py, longi_PdivMA50.py, longi_PdivMA200.py fully implemented
  - Price/MA ratios (>100 = price above MA = bullish)
  - Dependencies: require corresponding MA module
- ✓ longi_sh3m.py, longi_sh6m.py, longi_sh1yr.py fully implemented
  - Sharpe ratio = Period Return / Period Volatility
  - Periods: 67 days (3m), 133 days (6m), 265 days (1yr)
  - Independent modules (read only PotDat.csv)
- ✓ longi_quot1020.py, longi_quot2050.py fully implemented
  - MA speed quotients: (fast MA / slow MA) * 100 (>100 = accelerating/bullish)
  - Dependencies: corresponding MA modules (ma10+ma20 resp. ma20+ma50)
  - Choosers for the advice strategies (see expAdviceModel/REPORT 6k/6l)
- ✓ longi_grp_GICS_1yr.py fully implemented
  - Outputs: output/longi_grp_GICS_1yr.csv (GICS sector-aggregated 1-year growth)
  - Aggregates individual stock growth by GICS sector (13 sectors)
  - Formula: average(1 + growth_rate) - 1
- ✓ longi_grp_Sector2_1yr.py fully implemented
  - Outputs: output/longi_grp_Sector2_1yr.csv (Sector2-aggregated 1-year growth)
  - Aggregates individual stock growth by Sector2 attribute (56 sectors)
  - Formula: average(1 + growth_rate) - 1
- ✓ longi_across.py fully implemented
  - make_across(daynum, target_folder) function for programmatic use
  - Creates one cross-sectional snapshot per call
  - Called directly from longi.py with max daynum → outputs to app/output
  - Includes sector-aggregated performance columns: GICS_1yr, Sector2_1yr
  - Enables sector-relative analysis (stock performance vs. sector average)
  - Deletes existing across_*.csv files before creating new ones
  - Manual historical generation available via CLI or Python import
  - Runs last (depends on all other modules including grp_GICS_1yr and grp_Sector2_1yr)
- ✓ longi_upload.py fully implemented
  - Uses rclone sync to upload output/ directory
  - Cyclical architecture for easy addition of new upload targets
  - Excludes .txt and .gdoc files from sync
  - Destination folders cleaned to match source (old files removed)
- GDrive integration working (shared gd_download.py, longi_upload.py)
- Shared modules in /home/sm/potentials/shared/app/code/

### Unregistered/Experimental Modules (in code/, not yet in pipeline)
- **longi_beta1yr.py**, **longi_beta6m.py** - Beta (market sensitivity) over 265/133 days; same pattern as beta3m

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
- **Multiple dependencies** (depends_on=["rsi", "macd"]): Run after all dependencies complete

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

## Logging Format
Hierarchical log markers for readable output in start_longi.log:

- **`===`** - Top level: Wave starts in pipeline orchestrator
  - Example: `=== Wave 1: 10 module(s) ready to execute ===`
- **`---`** - Second level: Python module starts (added by orchestrator)
  - Example: `--- RSI14 (longi_rsi.py) ---`
- **`**`** - Notable status: Final pipeline status
  - Example: `** Pipeline completed successfully **`
- **`*`** - Shell script markers
  - Example: `* Fetch input data START: ...`
- Plain text for all other output (progress, success messages, data counts, etc.)

**Important**: Individual longi_*.py modules should NOT use `===` or `---` markers in their output - the orchestrator wraps their output with `---` automatically.

## Unit testing
- Individual modules can be testet for syntax errors by running from CLI: python3 longi_XX.py
- Production-correct testing requires dependency order which is only obtained by running longi.py