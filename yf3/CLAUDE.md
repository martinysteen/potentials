# yf3 app - Context for Claude Code

## Project Structure
```
/home/sm/potentials/yf3/app/
├── code/          # Python modules
├── input/         # Input data from Potentials repository
├── output/        # Output data (yFinance fundamentals)
├── output_stacked # Output data stacked
└── CLAUDE.md      # This file
```

## Environment
- **Execution:** Ubuntu server
- **Development:** Windows 11 connected via SSH
- **Conda env:** potsystem_env (shared)
- **Python:** 3.13
- **Shared code:** /home/sm/potentials/shared/

## Purpose
The yf3 app fetches fundamentals from yFinance for all tickers in the Potentials system. Execution is managed by:

- **start_yf3.sh** - Activates the conda environment and runs yf3.py, which:
     - (a) calls in input data from Potentials' repository and stores those in input/
     - (b) fetches desired fundamentals from yFinance.com and stores those in output/
- **updgd_yf3.sh** - Uploads the content of output/ to Google Drive

The personal crontab calls ~/time_wrapper.sh which takes care of activating start_yf3.sh and updgd_yf3.sh at desired points of time around the clock. At rather random occasions those yFinance calls result in successful catch of data, others do not.

**Log files:** Both shell scripts write their logs to /home/sm/ (start_yf3.log and updgd_yf3.log)

## Data Format
- **CSV format:** European — semicolon (`;`) delimiter, comma (`,`) as decimal separator, UTF-8 encoding
- **Output filenames:** `StockData2-YYYYMMDD-HHMM.csv` (36 columns, ~1 068 rows per file)
- **Key columns:** Symbol, FetchedDate (format `YYYY-MM-DD HH:MM`), Currency, prices, ratios, analyst targets

## Code Modules
| File | Purpose |
|------|---------|
| `yf3.py` | Main orchestration: loads tickers, calls fetch loop, saves output |
| `getYfinanceData.py` | yFinance API wrapper; returns dict of 36 metrics per ticker |
| `gd_download.py` | Downloads input CSV from Google Drive (OAuth2) |
| `stackYfinanceData.py` | Stacks all daily output files into one long-form CSV in output_stacked/ |

## Stacking (output_stacked/)
- **Script:** `stackYfinanceData.py` — called by `start_yf3.sh` after `yf3.py`
- **Output:** `output_stacked/StockData2_stacked.csv` — single long-form table of all historical fetches
- **Deduplication:** uses `FetchedDate` column; rows with an already-present FetchedDate are never re-added
- **Format:** same European CSV as source files

## Notes
- Existing app, developed without Claude Code
- `start_yf3.sh` exit code follows `yf3.py`; stacking exit code is logged separately
