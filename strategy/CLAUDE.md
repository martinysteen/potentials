# Strategy Backtesting — Context for Claude Code

## Purpose

Framework for backtesting named stock-selection strategies against historical Potentials data.
Each strategy defines a *focusset selector* (picks N tickers for a given trading day) and the
framework measures how those picks performed over 20d and 50d forward horizons.

Output is Excel reports — not new data files — stored under `app/report/`.

---

## Directory Structure

```
strategy/
├── CLAUDE.md
└── app/
    ├── code/
    │   ├── aggregate_summary.py          # Standalone: stacks Summary sheets from all run*.xlsx
    │   ├── shared/
    │   │   ├── config.py                 # Path constants
    │   │   ├── data_loader.py            # Cached CSV loaders
    │   │   └── report.py                 # Excel report writer (save_report)
    │   └── strategies/
    │       └── strategy_best_ranknow.py  # First strategy
    ├── data/                             # Scratch/temp only
    └── report/
        └── <strategy_name>/
            ├── run<N>_<YYYYMMDD>.xlsx    # One file per run
            └── aggregated_summary.xlsx   # Stacked summary across all runs
```

---

## Environment

- **Conda env:** `potsystem_env` — always activate; never pip/requirements.txt
- **Python:** 3.13
- **Platform:** Ubuntu server `gandalf` (SSH via `innovia.dk:2222`)
- **Development:** VS Code Remote-SSH from Windows

---

## Running

```bash
# Run a strategy
source ~/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env
cd ~/potentials/strategy/app/code
python strategies/strategy_best_ranknow.py

# Aggregate summaries across runs of one strategy
python aggregate_summary.py "BestRanknow"

# Aggregate all strategies at once
python aggregate_summary.py
```

---

## Data Sources

All input is read from `DATA_ROOT = /home/sm/potentials/repositoryRTBI/data/` (defined in `shared/config.py`).
Never hardcode paths.

### Matrix format (all Longi files)
- **Rows:** ticker symbols (index column, no header label)
- **Columns:** daynum integers as **strings** — newest left, oldest right
- **CSV:** European — semicolon separator `;`, comma decimal `,`
- Load with: `pd.read_csv(path, sep=';', decimal=',', index_col=0)`
- Column lookup: always `df[str(daynum)]` — never bare int

### Key files

| File | Content |
|------|---------|
| `Longi/future_gain20d.csv` | Realised forward gain over next 20 trading days (%) |
| `Longi/future_gain50d.csv` | Realised forward gain over next 50 trading days (%) — NaN for recent ~50 daynums |
| `Longi/longi_rank.csv` | Average rank across all performance periods (1 = best) |
| `Longi/longi_rsi.csv` | RSI14 (Wilder's method) |
| `Longi/longi_per*.csv` | Performance over 1d/1w/1m/3m/6m/1y |
| `Longi/longi_median_*.csv` | Rolling median of rank (10d–100d) |
| `Longi/longi_vola*.csv` | Returns-based volatility |
| `Longi/longi_sh*.csv` | Sharpe ratios |
| `Longi/longi_ma*.csv` | Simple moving averages |
| `Longi/longi_PdivMA*.csv` | Price / MA ratio |
| `Longi/longi_macd_*.csv` | MACD line / signal / histogram / zero-crossings |
| `Longi/longi_beta*.csv` | Beta (market sensitivity) |
| `data/PotDat.csv` | Raw stock prices |
| `data/Stamdata.csv` | Ticker metadata: Name, Sector, GICS, Sector2, Zone, Homeland, … |
| `data/Cal.csv` | daynum → date (index is float, e.g. 2055.0 — use `float(daynum)` to look up) |

**Do not use** `Longi/longi_grp_*.csv` as per-ticker features — they are sector-row aggregates.

---

## Shared Modules

### `shared/config.py`
Constants: `DATA_ROOT`, `DATA_LONGI`, `POTDAT_PATH`, `STAMDATA_PATH`, `CAL_PATH`,
`APP_ROOT`, `REPORT_ROOT`, `SUMMARY_CSV`.

### `shared/data_loader.py`
All functions are `@lru_cache` — files are loaded once per process.

| Function | Returns |
|----------|---------|
| `load_longi(filename)` | DataFrame (rows=tickers, cols=daynum strings) |
| `load_potdat()` | PotDat.csv as DataFrame |
| `load_stamdata()` | Stamdata.csv as DataFrame (cols: Name, Sector, GICS, Sector2, Zone, …) |
| `daynum_to_date(daynum)` | Date string from Cal.csv |

### `shared/report.py`
Single public function:

```python
save_report(strategy_name, params, hop_results, run_num=None)
```

Writes `run<N>_<date>.xlsx` with two sheets:
- **Operational** — see layout below
- **Summary** — key/value pairs of params + avg gains

Also appends one row to `app/report/summary.csv` (master cross-strategy CSV).

### `aggregate_summary.py`
Standalone script. Reads the Summary sheet from every `run*.xlsx` in a strategy folder
and writes `aggregated_summary.xlsx` with one row per run, columns coloured by gain sign.

---

## hop_results Structure

Each item in the list passed to `save_report`:

```python
{
    "daynum":          int,               # trading daynum for this hop
    "tickers":         list[str],         # focusset, rank-ordered best→worst
    "gains_20d":       dict[str, float],  # {ticker: realised_20d_gain_%}
    "gains_50d":       dict[str, float],  # {ticker: realised_50d_gain_%} — NaN if unavailable
    "ref_values_prev": dict[str, float],  # market context at daynum-1
                                          # keys: "^GSPC_rsi", "^STOXX_rsi", "^HSI_rsi", "^VIX"
}
```

`ref_values_prev` is the *decision-day* context (the day before investment).
`^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi` are RSI14 values; `^VIX` is raw price.

---

## Operational Sheet Layout

| Rows | Content | Colour |
|------|---------|--------|
| 1 | Daynum headers | Blue |
| 2 | Date headers | Blue |
| 3–(N+2) | Ticker names, rank 1→N (col A vacant except A3="No_go_GSPC_rsi", A4=threshold) | — |
| N+3 | `avg_gain20d` | Green/red/grey |
| N+4 | `avg_gain50d` | Blue-grey sep / green/red/grey |
| N+5 to N+8 | `^GSPC_rsi (day-1)`, `^STOXX_rsi (day-1)`, `^HSI_rsi (day-1)`, `^VIX (day-1)` | Yellow |
| N+9 … | GICS occurrence counts (sorted by frequency), labelled `GICS_Tech` etc. | Purple |
| … | Sector2 occurrence counts | Peach |
| … | Zone occurrence counts | Teal |

**avg_gain cells use Excel formulas** referencing the `^GSPC_rsi (day-1)` row and `$A$4`:
`=IF(Bn_gspc < $A$4, "", value)` — change A4 to try a different no-go threshold live.

---

## PARAMS and the No_go Filter

```python
PARAMS: dict = {
    "focusset_size": 3,       # N tickers selected per hop
    "step": 1,                # daynum step between hops
    "No_go_GSPC_rsi": 40,     # suppress avg gains when GSPC RSI (day-1) < this value
}
```

- `No_go_GSPC_rsi` label is written to **A3**, value to **A4** (amber input cell).
- Avg gain cells use an IF formula referencing A4 — editing A4 in Excel recalculates immediately.
- Fill colour is static (grey = suppressed at generation-time threshold; green/red = active).

---

## Strategy Anatomy

Minimum contract for a new strategy file:

```python
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.data_loader import load_longi, load_potdat, daynum_to_date
from shared.report import save_report

STRATEGY_NAME = "My strategy"
PARAMS: dict = {
    "focusset_size": 3,
    "step": 10,
    "No_go_GSPC_rsi": 40,   # optional; omit to disable the no-go filter
}

def select_focusset(daynum: int, <signal_df>: pd.DataFrame, n: int) -> list[str]:
    """Return n tickers ranked best→worst by your signal. Return [] if unavailable."""
    col = str(daynum)
    if col not in <signal_df>.columns:
        return []
    return <signal_df>[col].dropna().nsmallest(n).index.tolist()  # or nlargest

def get_reference_values(daynum: int) -> dict[str, float]:
    # copy verbatim from strategy_best_ranknow.py — same market context for all strategies

def main() -> None:
    # Load data, run hop loop, call save_report(STRATEGY_NAME, PARAMS, hop_results)
    # Each hop appends: {daynum, tickers, gains_20d, gains_50d, ref_values_prev}
```

**Rules:**
- `select_focusset` returns `[]` if daynum absent; never raises
- `str(daynum)` for all DataFrame column lookups
- Load only files your strategy actually uses
- Do not store `ref_values` (current-day) — only `ref_values_prev` (day-1) is used by report.py

---

## Known Data Quirks

- **Cal.csv index is float**: `2055,00` → `2055.0`. Look up with `float(daynum)`.
- **future_gain20d valid from ~daynum-20**: The most recent ~20 columns are NaN (future not yet realized). `find_start_daynum()` skips these automatically.
- **future_gain50d valid from ~daynum-50**: NaN for most recent ~50 hops; expected.
- **Data gap at daynums 1543→1288**: No columns exist between these values. Hops landing in this gap return `[]` from `select_focusset` and stop the loop.
- **Stamdata.csv first column header** is a timestamp string (e.g. `"03-06-26  23:02"`), not a meaningful label.

---

## Coding Standards

Match longi conventions:
- Type hints on all function signatures
- European CSV: `sep=';', decimal=','`
- Log to stdout; exit 0/1
- No hardcoded paths — use `shared/config.py` constants

---

## Development Notes

- VS Code Remote-SSH from Windows; Danish keyboard layout
- Claude Code shortcut: Ctrl+Alt+C  |  Terminal: Ctrl+Æ
- Data is **read-only** — strategy code never writes to `repositoryRTBI/`
- `app/data/` is scratch only — not committed, not depended upon
