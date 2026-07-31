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
    │   ├── longi_grp_{GICS,Sector2}_per*.py  # Sector-aggregate modules (thin; see aux_grp_shared.py)
    │   ├── longi_future_performance.py  # Forward-looking twin of longi_performance.py
    │   ├── longi_across.py # Cross-sectional data extraction module
    │   └── longi_upload.py
    ├── input/           # Data from Google Drive
    └── output/          # Individual stock derived tables + sector aggregates + cross-sectional snapshot
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
4. Results go to `./app/output/` (all derived tables: individual stock, sector aggregates, and cross-sectional snapshot)
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
6. **longi_per5d.csv** - 5-day performance ✓ IMPLEMENTED
7. **longi_per10d.csv** - 10-day performance ✓ IMPLEMENTED
8. **longi_per20d.csv** - 20-day performance ✓ IMPLEMENTED
9. **longi_per50d.csv** - 50-day performance ✓ IMPLEMENTED
10. **longi_per100d.csv** - 100-day performance ✓ IMPLEMENTED
11. **longi_per200d.csv** - 200-day performance ✓ IMPLEMENTED
12. **longi_rank.csv** - Average rank across all performance periods ✓ IMPLEMENTED
13. **longi_median_10d.csv** - 10-day rolling median of rank ✓ IMPLEMENTED
14. **longi_median_20d.csv** - 20-day rolling median of rank ✓ IMPLEMENTED
15. **longi_median_30d.csv** - 30-day rolling median of rank ✓ IMPLEMENTED
16. **longi_median_40d.csv** - 40-day rolling median of rank ✓ IMPLEMENTED
17. **longi_median_50d.csv** - 50-day rolling median of rank ✓ IMPLEMENTED
18. **longi_median_100d.csv** - 100-day rolling median of rank ✓ IMPLEMENTED
19. **longi_stepup.csv** - Step-up count (0-3) as uptrend measure ✓ IMPLEMENTED
20. **longi_spr100d.csv** - Spread to 100-day maximum (% growth needed) ✓ IMPLEMENTED
21. **longi_spr250d.csv** - Spread to 250-day maximum (% growth needed) ✓ IMPLEMENTED
22. **longi_vola20d.csv** - 20-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
23. **longi_vola100d.csv** - 100-day volatility (returns-based stdev in %) ✓ IMPLEMENTED
24. **longi_ma10.csv** - 10-day Simple Moving Average ✓ IMPLEMENTED
25. **longi_ma20.csv** - 20-day Simple Moving Average ✓ IMPLEMENTED
26. **longi_ma50.csv** - 50-day Simple Moving Average ✓ IMPLEMENTED
27. **longi_ma200.csv** - 200-day Simple Moving Average ✓ IMPLEMENTED
28. **longi_PdivMA20.csv** - Price / MA20 ratio (>100 = bullish) ✓ IMPLEMENTED
29. **longi_PdivMA50.csv** - Price / MA50 ratio (>100 = bullish) ✓ IMPLEMENTED
30. **longi_PdivMA200.csv** - Price / MA200 ratio (>100 = bullish) ✓ IMPLEMENTED
31. **longi_sh3m.csv** - 3-month Sharpe ratio (return/volatility over 67 days) ✓ IMPLEMENTED
32. **longi_sh6m.csv** - 6-month Sharpe ratio (return/volatility over 133 days) ✓ IMPLEMENTED
33. **longi_sh1yr.csv** - 1-year Sharpe ratio (return/volatility over 265 days) ✓ IMPLEMENTED
34. **longi_quot1020.csv** - MA10/MA20 quotient ×100, momentum speed (>100 = accelerating) ✓ IMPLEMENTED
35. **longi_quot2050.csv** - MA20/MA50 quotient ×100, momentum speed (>100 = accelerating) ✓ IMPLEMENTED

### Forward-Looking Tables (longi_future_per*) — the backtest targets

`longi_future_performance.py` is the forward-looking twin of `longi_performance.py` and emits
the **same seven-period "seven-pack" ladder**, same day counts, same shape:

| File | Days held | Newest blank columns |
|------|-----------|----------------------|
| `longi_future_per1d.csv` | 1 | 2 |
| `longi_future_per5d.csv` | 5 | 6 |
| `longi_future_per10d.csv` | 10 | 11 |
| `longi_future_per20d.csv` | 20 | 21 |
| `longi_future_per50d.csv` | 50 | 51 |
| `longi_future_per100d.csv` | 100 | 101 |
| `longi_future_per200d.csv` | 200 | 201 |

Where `longi_per*` assigns a **trailing** gain to the end date, these assign a **forward** gain
to the **signal date** — at daynum `d` the cell answers "what would a position opened on the
strength of day d's data have returned?".

**The signal day is not traded.** Day `d`'s close is what the decision is made on, so it cannot
also be the entry price. Entry is the NEXT trading day and exit is `period_days` after that:

```
gain[d] = (P[d+1+period_days] - P[d+1]) / P[d+1] * 100
```

Hence `period_days + 1` blank columns at the newest end, not `period_days`.

This family **replaced `future_gain20d.csv` / `future_gain50d.csv` on 2026-07-31** (scripts moved
to `_not_used/`), in two steps the same day. First to a semantic ladder mirroring `longi_per*`'s
old labels (`1d/1w/1m/3m/6m/1y` ≈ 1/5/22/66/132/264 days) — then, hours later, `longi_per*`
itself was redefined to the literal **"seven-pack"** (1/5/10/20/50/100/200 days) because the
semantic labels were unpopular and four of six didn't match a round day count anyway. The
forward family follows suit. So relative to the *original* `future_gain20d/50d.csv`, two things
changed: the day counts (20→20 and 50→50 are coincidentally unchanged in the final seven-pack,
but the intermediate step wasn't — don't assume any given "N" survived unchanged without
checking), and entry moved from `P[d]` to `P[d+1]` — the old files quietly assumed you could
trade the very close you were reading.

**These are NOT per-ticker features, despite the `longi_` prefix.** They are ticker-keyed and
would join perfectly, which is exactly the danger. `longi_across.py` skips them by the
`longi_future_` prefix; without that guard a backfilled `across_<daynum>.csv` would carry the
answer alongside the features. Keep them out of `aux_winloss_shared.FEATURE_FILES` too.

Verified on creation against the trailing family, which is the cheapest correctness check
available — the two must satisfy `longi_future_perX[i] == longi_perX[i - 1 - days]` exactly.
It held over all ~4.99M overlapping cells (seven periods; re-verified after the seven-pack
correction, having first held over 4.09M cells for the six-period version).

**QC interaction:** the blank newest columns are legitimate, so `aux_qc_repo.BLANK_LEAD_COLS`
tells check 3 (data density) to start counting *after* that lead rather than flagging it. Add an
entry there if the ladder ever gains a period.

### Sector-Aggregated Tables (Grouped by Stock Attributes)
Output directory: `app/output/` (same as individual stock tables)

**Format:** `longi_grp_{Attribute}_{metric}.csv` — the same shape as the per-ticker
`longi_{metric}.csv` it is built from (same daynum columns, same European CSV, same 2 decimals),
but **rows are sector names**, one per distinct value of a `Stamdata.csv` attribute.
- Values: the plain **mean** of that sector's tickers for that daynum, NaN-skipping (a sector's
  average uses whichever of its tickers have data that day)
- Row set is the full sorted attribute value list, held stable across metrics and over time — a
  sector with no data on a daynum gets a blank cell, not a missing row
- Header row is `-;<daynum>;<daynum>;…`, mirroring `longi_per*.csv`

**Available aggregations** — two performance families, one table per `longi_per*` metric (the
"seven-pack" ladder: 1d/5d/10d/20d/50d/100d/200d):
- **longi_grp_GICS_per1d.csv**, **_per5d**, **_per10d**, **_per20d**, **_per50d**, **_per100d**, **_per200d**
  (13 GICS sectors: Basi, C-Di, C-St, Ener, Fina, Heal, Index, Indu, REIT, Tech, Tele, Util, na)
  ✓ IMPLEMENTED
- **longi_grp_Sector2_per1d.csv**, **_per5d**, **_per10d**, **_per20d**, **_per50d**, **_per100d**, **_per200d**
  (50 Sector2 values — the finer taxonomy; every ticker in Stamdata carries one, none blank)
  ✓ IMPLEMENTED

**These are NOT per-ticker feature files.** Row keys are sector names, so they can never be
inner-joined to ticker-keyed data. `longi_across.py` skips them by the `longi_grp_` prefix, and
they must stay out of `aux_winloss_shared.FEATURE_FILES`. (An older, unrelated
`longi_grp_*_{1yr,3m}` family was deleted 2026-07-29; it had no consumer.)

**Implementation:** all the work lives in `aux_grp_shared.build_group_average(metric, group_col)`.
A single script, `longi_grp_performance.py`, loops over `GROUP_COLS x METRICS` and calls it 14
times — one `longi.py` module (`grp_performance`) produces the whole family, mirroring how
`longi_performance.py` loops its own `PERIODS` internally rather than being one script per period.
(Until 2026-07-31 this was 14 separate ~15-line one-metric wrapper scripts, each its own `longi.py`
module; consolidated since they carried no logic beyond naming a metric and a group column.)
`group_col` is a parameter, so a further family (Zone, Homeland, …) is a drop-in — add it to
`GROUP_COLS`, add the filenames to `aux_qc_repo.EXPECTED_FILES`; no edit to the shared builder.

### Cross-Sectional Data
Output directory: `app/output/`

**across_<daynum>.csv** - Cross-sectional view for most recent daynum ✓ IMPLEMENTED
    - Rows: Stock tickers
    - Columns: ticker_<daynum> (first column includes daynum), then metrics from all longi_*.csv files, alphabetically sorted
    - Example columns: ticker_2009, rsi, macd_line, per1d, rank, median_10d, stepup
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
- First 20 days (from left) are usable for correlation with 20-day forward gains

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
  - Columns: ticker_<daynum> (first column), then metric names (extracted from filenames), alphabetically sorted
  - Example columns: ticker_2009, rsi, macd_line, macd_signal, macd_histogram, per1d, per5d, per10d, per20d, per50d, per100d, per200d, rank, median_10d, median_20d, median_30d, median_40d, median_50d, median_100d, stepup
- **Manual historical generation**: Use make_across() function for creating backfilled files for specific daynums
  - From Python: `from longi_across import make_across; make_across(1950, "/path/to/folder")`
  - From CLI: `python3 longi_across.py 1950 --target-folder=/path/to/folder`
  - Accepts optional daynum and --target-folder parameters when run as script
- **Dependencies**: Must run last (depends on all other modules)

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
  - 34 modules registered: price, rsi, macd, performance, rank, medians, stepup, spr100d, spr250d, vola20d, vola100d, ma10, ma20, ma50, ma200, PdivMA20, PdivMA50, PdivMA200, quot1020, quot2050, grp_performance, coreindex, coreindexRSI, beta3m, beta6m, beta1yr, trump, iran, macd_Z, sh3m, sh6m, sh1yr, future_performance, across
    (`future_gain20d`/`future_gain50d` were retired 2026-07-31 — one `future_performance`
    module now emits the whole `longi_future_per*` "seven-pack" ladder — 1d/5d/10d/20d/50d/100d/200d,
    replacing the earlier six-entry semantic ladder the same day. The 14 `grp_{GICS,Sector2}_per*`
    modules were consolidated into a single `grp_performance` module the same day too — was 47
    modules briefly, now 34.)
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
- ✓ longi_grp_performance.py fully implemented (one module, `grp_performance`)
  - Loops GROUP_COLS=[GICS, Sector2] x METRICS=[per1d..per200d], calling
    aux_grp_shared.build_group_average(metric, group_col) 14 times
  - Outputs: output/longi_grp_GICS_per{1d,5d,10d,20d,50d,100d,200d}.csv (13 GICS sector rows each)
  - Outputs: output/longi_grp_Sector2_per{1d,5d,10d,20d,50d,100d,200d}.csv (50 Sector2 rows each)
  - Values: plain mean of the sector's tickers, NaN-skipping
  - Dependencies: performance module (all 7 longi_per*.csv files)
- ✓ longi_future_performance.py fully implemented
  - Outputs: longi_future_per{1d,5d,10d,20d,50d,100d,200d}.csv — forward gains on the same day
    counts as longi_performance.py, assigned to the SIGNAL day, entered at signal+1
  - Independent module (reads only PotDat.csv); nothing depends on it — and `across`
    deliberately does NOT, see the skip guard in longi_across.py
- ✓ longi_across.py fully implemented
  - make_across(daynum, target_folder) function for programmatic use
  - Skips longi_grp_* (sector rows) and longi_future_* (look-ahead) by filename prefix
  - Creates one cross-sectional snapshot per call
  - Called directly from longi.py with max daynum → outputs to app/output
  - Deletes existing across_*.csv files before creating new ones
  - Manual historical generation available via CLI or Python import
  - Runs last (depends on all other modules)
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