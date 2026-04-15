# Project Startup & Technical Recipe: Gainsuccess

This document combines the technical recipe and restart guidelines for the Gainsuccess project. It preserves the sequence of core instructions, technical constraints, and environment details necessary to resume work.

## 1. Environment & Connectivity
- **Location**: All computational work is executed on the remote Ubuntu server `gandalf` (`sm@gandalf`) connected by SSH (ssh sm@gandalf)
- **Application Root**: `~/potentials/gainsuccess`
- **Network Path**: `\\gandalf\sm-home\potentials\gainsuccess`
- **Conda Environment**: All code runs in the `potsystem_env` Conda environment on `gandalf`.
- **Python Path**: `/home/sm/miniconda3/envs/potsystem_env/bin/python`

## 2. File Organization
- **Python Code**: `code/` (trial scripts like `...trial10.py`, etc.)
- **Documentation**: `doc/` (`task.md`, `walkthrough.md`, `implementation_plan.md`)
- **Input Data**: `input/` (European CSV: `;` separator, `,` decimal, naming `longi_*.csv`)
- **Output Results**: `output/` (CSV data tables, plots, histograms)
- **Data Update**: Run `fetch_input.sh` in the app root daily.

## 3. Technical Constraints & Data Processing
- **CSV Format**: European style (`;` separator, `,` decimal, no thousand separators).
- **Mapping (`longi_uptrend.csv`)**: 
  - `VeryGood` or `Very Good` = 5
  - `Good` = 4
  - `Maybe` = 2
  - Spaces/empty = 0 (if mandatory)
- **Mapping (`longi_macd_Z.csv`)**:
  - `ZOP` = 1
  - `ZNED` = -1
- **Backend**: Python 3.x with Pandas, NumPy, SciPy, Seaborn, and Matplotlib.

## 3b. Data Quirks & Specifications (CRITICAL)
- **First Column Header**: The first column header is often a timestamp (e.g., `Thu Jan 29...`). This effectively acts as the 'ticker' column. Code MUST rename/treat index 0 as 'ticker' and ignore the actual header text.
- **Time Columns**: Columns 1..N are integer 'daynums' (e.g., `2072`, `2071`) representing trading dates.
- **Time Direction**: Reverse chronological order (Newest = Left/Lower Index).
- **Line Endings**: Files may contain Windows-style CRLF (`\r\n`).
- **Separators**: European style (`;` separator, `,` decimal).

## 4. Resumption Workflow
1. Verify SSH connection to `sm@gandalf`.
2. Ensure access to the `~/potentials/gainsuccess` directory.
3. Read this `STARTUP_INFO.md` file to pick up the technical thread.
4. Reference `output/` for the latest results and `doc/walkthrough.md` for detailed findings.
5. Tell the AI: *"I am resuming work on the Gainsuccess project. Please review the technical recipe in STARTUP_INFO.md."*

## 5. Key Documentation Files
- `doc/task.md`: Checklist of completed work.
- `doc/walkthrough.md`: Detailed results and findings.
- `doc/implementation_plan.md`: Planning for current/future steps.
