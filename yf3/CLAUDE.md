# yf3 app - Context for Claude Code

## Project Structure
```
/home/sm/potentials/yf3/app/
├── code/          # Python modules
├── input/         # Input data from Potentials repository
├── output/        # Output data (yFinance fundamentals)
└── CLAUDE.md      # This file
```

## Environment
- **Execution:** Ubuntu server
- **Development:** Windows 11 connected via SSH
- **Run Python on the server:** `ssh -p 2222 sm@innovia.dk` then `conda activate potsystem_env` — the Windows host has no usable Python
- **Conda env:** potsystem_env (shared)
- **Python:** 3.13
- **Shared code:** /home/sm/potentials/shared/

## Purpose
The yf3 app fetches fundamentals from yFinance for all tickers in the Potentials system. Execution is managed by:

- **start_yf3.sh** - Activates the conda environment and runs yf3.py, which:
     - (a) calls in input data from Potentials' repository and stores those in input/
     - (b) fetches desired fundamentals from yFinance.com and stores those in output/
- **updgd_yf3.sh** - Uploads the content of output/ to Google Drive

The personal crontab calls `~/potentials/yf3/yf3_wrapper.sh` (in line with the other Potentials
families) which takes care of activating start_yf3.sh and updgd_yf3.sh at desired points of time
around the clock. At rather random occasions those yFinance calls result in successful catch of
data, others do not.

**Log files:** All in `~/logs/` (also matching the other families): `yf3_wrapper.log`
(wrapper's own run log), `yf3_timing_results.log` (one-line success/fail per fired hour),
`start_yf3.log`, `updgd_yf3.log`.

## Notes
- Existing app, developed without Claude Code
- European CSV format
