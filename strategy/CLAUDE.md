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
    │   ├── best_strategy.py              # Cross-strategy comparison (sections per criterion)
    │   ├── run_extension.py              # Extension for P20dP50dZOP (see Extension Files section)
    │   ├── run_extension.py             # Multi-strategy stub — grows as strategies are wired up
    │   ├── shared/
    │   │   ├── config.py                 # Path constants
    │   │   ├── data_loader.py            # Cached CSV loaders
    │   │   ├── extension.py              # Extension runner + Excel writer
    │   │   └── report.py                 # Excel report writer (save_report)
    │   └── strategies/
    │       ├── strategy_ranknow.py       # Baseline: lowest longi_rank
    │       ├── strategy_ZOP.py           # ZOP-flagged tickers by rank
    │       ├── strategy_P20dWin.py       # longi_P20d_win >= threshold, then lowest rank
    │       ├── strategy_P50dWin.py       # longi_P50d_win >= threshold, then lowest rank
    │       ├── strategy_P20dZOP.py       # ZOP-flagged AND P20d_win >= threshold
    │       ├── strategy_P50dZOP.py       # ZOP-flagged AND P50d_win >= threshold
    │       ├── strategy_P20dP50dZOP.py   # ZOP-flagged AND both P20d+P50d win filters
    │       ├── strategy_P20P50cross1020.py # P20d+P50d win AND ad-hoc Q10_20=MA10/MA20 >= min
    │       └── strategy_P20P50cross2050.py # P20d+P50d win AND ad-hoc Q20_50=MA20/MA50 >= min
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
python strategies/strategy_ranknow.py

# Aggregate summaries across runs of one strategy
python aggregate_summary.py "Ranknow"

# Aggregate all strategies at once
python aggregate_summary.py

# Cross-strategy comparison (best run per strategy + overall best, per criterion)
python best_strategy.py

# Build extension for P20dP50dZOP (partial-gain snapshot of the most recent ~20 days)
python run_extension.py
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
- **Summary** — key/value metrics (params, avg gains, realizable chain, loss/worst
  stats) — see "Summary Sheet Metrics" below

Also appends one row to `app/report/summary.csv` (master cross-strategy CSV).

### `aggregate_summary.py`
Standalone script. Reads the Summary sheet from every `run*.xlsx` in a strategy folder
and writes `aggregated_summary.xlsx` with one row per run, columns coloured by gain sign.

---

## Extension Files

`run_extension.py` builds a snapshot of the current portfolio situation for strategies
that have a `build_extension()` function. Currently only P20dP50dZOP is wired up — other
strategies can be added to `run_extension.py` once their `build_extension()` is implemented.

### What it does

The most recent ~20 trading days have no realized 20d gain in `future_gain20d.csv`.
The extension covers exactly this gap: from `start_daynum+step` (one step beyond the
last valid backtest daynum) up to the most recent daynum in `PotDat.csv`.

For each entry daynum D, the partial gain is computed from prices:
`(price[exit] - price[D]) / price[D] * 100`

where `exit` = latest available price daynum (same for all hops in one extension run).

### Extension Operational sheet layout

| Rows | Content | Colour |
|------|---------|--------|
| 1 | A1=`"Size/Step/No_RSI/P20/P50"` \| daynum headers | Blue |
| 2 | A2=param values e.g. `"5/5/45/0.8/0.8"` \| date headers | Blue |
| 3–(N+2) | Ticker names (rank 1→N) | — |
| N+3 | Per-column labels: `"avg_gain15d"`, `"avg_gain10d"`, … | Light green |
| N+4 | `avg_partial_gain` values (no-go suppressed at write time) | Orange(−) / Light yellow(+) / Grey(suppressed) |
| N+5 | *(reserved — 50d labels)* | — |
| N+6 | *(reserved — 50d results)* | — |
| N+7+ | `^GSPC_rsi (day-1)`, `^STOXX_rsi (day-1)`, … | Yellow |
| … | GICS / Sector2 / Zone counts | Purple/peach/teal |

For `focusset_size=5` (current default): labels at row 8, values at row 9, 50d reserved at rows 10–11, ref rows from row 12.

Param values use `"-"` for keys absent from the strategy's PARAMS (e.g. a strategy without `p50d_win_min` shows `"5/5/45/0.8/-"`).

### Adding a strategy to run_extension.py

1. Add `build_extension()` to the strategy file (mirror P20dP50dZOP as template)
2. Import and add to the loop in `run_extension.py`

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
| *(optional)* | `N_survivors` per hop — **only** when hops carry an `"n_survivors"` key; inserted directly below the tickers, shifting every row below it down by 1 | Pale blue |
| N+3 | `avg_gain20d` | Green/red/grey |
| N+4 | `avg_gain50d` | Blue-grey sep / green/red/grey |
| N+5 to N+8 | `^GSPC_rsi (day-1)`, `^STOXX_rsi (day-1)`, `^HSI_rsi (day-1)`, `^VIX (day-1)` | Yellow |
| N+9 … | GICS occurrence counts (sorted by frequency), labelled `GICS_Tech` etc. | Purple |
| … | Sector2 occurrence counts | Peach |
| … | Zone occurrence counts | Teal |

**avg_gain cells use Excel formulas** referencing the `^GSPC_rsi (day-1)` row and `$A$4`:
`=IF(Bn_gspc < $A$4, "", value)` — change A4 to try a different no-go threshold live.

`report.py` computes the `^GSPC_rsi` row position dynamically, so the optional `N_survivors`
row keeps the formulas correct when present. A strategy opts in by adding `"n_survivors": <int>`
to each `hop_results` dict (see `strategy_P20P50cross1020.py`).

---

## Summary Sheet Metrics

The Summary sheet is a flat list of `(key, value)` rows. `aggregate_summary.py` and
`best_strategy.py` ingest these keys **generically** — any new Summary row automatically
becomes a column downstream, so adding a metric only means appending a row in `report.py`.

Rows, in write order:

| Key(s) | Meaning |
|--------|---------|
| `StrategyName`, `Run#`, `StartDaynum`, `EndDaynum` | Identity / daynum range |
| `N_hops`, `N_hops_active` | Total hops / hops surviving the No_go filter |
| *(PARAMS keys)* | `focusset_size`, `step`, `No_go_GSPC_rsi`, `p20d_win_min`, … |
| `avg_gain20d`, `avg_gain50d` | Grand average per-hop top-N gain (No_go-filtered) |
| `chain_ret20d/50d`, `chain_cagr20d/50d`, `chain_n20d/50d` | **Realizable chain** (see below) |
| `N_20d_loss`, `N_50d_loss` | Count of active hops with negative avg gain |
| `Worst_20d`, `Worst_50d` | Worst single active-hop avg gain |

### Two ways to read performance — and why overlap matters

With `step < horizon`, consecutive hops measure **overlapping** forward windows, so you cannot
*sum/compound* per-hop gains into a portfolio return without massive double-counting. But overlap
does **not** bias an *average*. So the metrics split along that line:

- **Averages → valid for comparing configs.** `avg_gain*` is a mean; overlap only reduces sample
  independence, not the point estimate.
- **Accumulation → must be made realizable.** The retired `acc_gain*` summed overlapping hops and
  overstated returns; the `chain_*` family replaces it with a non-overlapping compound.

To study `focusset_size`, just run it as a sweep axis (`focusset_size: [1, 3, 5]`) and compare
`avg_gain*` across runs — quality degrades monotonically with size, so a per-run rank-marginal
curve was redundant.

### Realizable chain (`chain_ret/cagr/n` × `20d/50d`)

A non-overlapping compounded backtest: hops are walked oldest→newest and a hop is taken only once the
previous position has closed (daynums spaced ≥ the holding horizon: 20 or 50). The chained hops'
top-N avg gains are compounded. **This is the clean way to study `step`** — and reveals it directly:

- `chain_n20d/50d` — realizable trade count (≈ span ÷ horizon, capped by holding period, **not** by step)
- `chain_ret20d/50d` — total compounded return %
- `chain_cagr20d/50d` — annualized (`_TRADING_DAYS_YEAR = 252`; 1 daynum ≈ 1 trading day)

Implication: `step < horizon` yields no realizable benefit (capital locked); `step ≈ horizon` is the
sweet spot; `step > horizon` idles capital and lowers CAGR. Respects `No_go_GSPC_rsi`; NaN-safe.
A chain spanning the 1543→1288 daynum gap has a slightly distorted span — an acceptable edge case.

### Retired: `acc_gain*` and `top{k}_gain*`

Two metric families are **removed**:
- `acc_gain{20d,50d}_w{20,50,100,200}` (sum of per-hop gains over trailing nominal-daynum windows) —
  double-counted overlapping positions.
- `top{k}_gain{20d,50d}` (the rank-marginal curve, k = 1…N) — quality degradation with `focusset_size`
  is monotonic and already evident from comparing `avg_gain*` across `focusset_size` sweep runs, so the
  per-run curve only bloated the table.

`aggregate_summary.py` actively **drops any legacy `acc_gain*` or `top*` column** still present in
older `run*.xlsx`, so both are gone from all downstream output without needing to delete history.

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

### Ad-hoc feature tables

A strategy may build a signal matrix at runtime from existing Longi matrices and use it exactly like
a preformed CSV (same tickers×daynum shape, `df[str(daynum)]` lookups). Used by the `cross` strategies:

```python
def build_q10_20() -> pd.DataFrame:           # MA quotient; == 1 at the golden cross
    ma_fast = load_longi("longi_ma10.csv")     # cross1020: MA10/MA20, threshold key q10_20_min
    ma_slow = load_longi("longi_ma20.csv")     # cross2050 names it build_q20_50: MA20/MA50, q20_50_min
    return ma_fast.divide(ma_slow.replace(0, float("nan")))  # NaN-safe; aligns on index+cols
```

The quotient name encodes its MA pair: `cross1020` → `Q10_20` / `build_q10_20` / `q10_20_min`;
`cross2050` → `Q20_50` / `build_q20_50` / `q20_50_min`.

To also surface a pre-prioritisation count (e.g. how many tickers passed all filters before the
rank cut), add `"n_survivors": <int>` to each `hop_results` dict — `report.py` then renders the
optional `N_survivors` row (see Operational Sheet Layout).

---

## Known Data Quirks

- **Cal.csv index is float**: `2055,00` → `2055.0`. Look up with `float(daynum)`.
- **future_gain20d valid from ~daynum-20**: The most recent ~20 columns are NaN (future not yet realized). `find_start_daynum()` skips these automatically.
- **future_gain50d valid from ~daynum-50**: NaN for most recent ~50 hops; expected.
- **Data gap at daynums 1543→1288**: No columns exist between these values. Hops landing in this gap return `[]` from `select_focusset` and stop the loop. Daynum 1288 itself is a lone outlier present for a special non-strategy purpose — ignore it in strategy work.
- **Stamdata.csv first column header** is a timestamp string (e.g. `"03-06-26  23:02"`), not a meaningful label.

---

## Excel Styling Conventions

Consistent across all xlsx output (`aggregate_summary.py`, `best_strategy.py`):

| Fill colour | Hex | Used for |
|-------------|-----|----------|
| Blue | `BDD7EE` | Normal column headers (`_HDR_FILL`) |
| Yellow | `FFFF99` | Simulation parameter column headers: `focusset_size`, `step`, `No_go_GSPC_rsi`, `p20d_win_min`, `p50d_win_min` (`_PARAM_FILL`) |
| Amber | `FFE599` | "Best overall" row in best_strategy.xlsx; editable No_go threshold cell in Operational sheet |
| Green | `C6EFCE` | Positive gains |
| Red | `FFC7CE` | Negative gains |
| Grey | `EEEEEE` | Suppressed / n/a values |

The `_PARAM_COLS` set is defined in both `aggregate_summary.py` and `best_strategy.py` and must be kept in sync if new strategy parameters are added.

---

## best_strategy.py Output Structure

`app/report/best_strategy.xlsx` has one section per criterion (4 total):
- Grey section header row (criterion label)
- One data row per strategy, sorted best→worst by that criterion
- Amber "Best overall" row (the single cross-strategy winner)
- Blank separator row

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
