# Strategy Backtesting — Context for Claude Code

## Purpose

Framework for backtesting named stock-selection strategies against historical Potentials data.
Each strategy defines a *focusset selector* (picks N tickers for a given trading day) and the
framework measures how those picks performed over a single forward horizon — the **`period`**
parameter (20 or 50 trading days; default 20).

Output is Excel reports — not new data files — stored under `app/report/`.

---

## Directory Structure

```
strategy/
├── CLAUDE.md
└── app/
    ├── code/
    │   ├── run_sweep.py                  # MAIN ENTRY: archive + rebuild swept strategies, aggregate, compare
    │   ├── sweep_config.py               # the single place you edit to decide WHAT runs
    │   ├── aggregate_summary.py          # stacks Summary sheets from all run*.xlsx of a strategy
    │   ├── best_strategy.py              # cross-strategy comparison (transposed, one column per strategy)
    │   ├── extension_of_best_strategy.py # pick the winner, extend it in its folder, move xlsx to report/
    │   ├── shared/
    │   │   ├── config.py                 # path constants
    │   │   ├── data_loader.py            # cached CSV loaders
    │   │   ├── chain.py                  # realizable_chain — the one place the chain math lives
    │   │   ├── report.py                 # per-run Excel writer (save_report) + master summary.csv
    │   │   └── extension.py              # partial-gain extension runner (period-driven)
    │   ├── strategies/
    │   │   ├── strategy_ranknow.py       # baseline: lowest longi_rank
    │   │   ├── strategy_P20dWin.py       # longi_P20d_win >= threshold, then lowest rank
    │   │   ├── strategy_P50dWin.py       # longi_P50d_win >= threshold, then lowest rank
    │   │   ├── strategy_P20P50cross1020.py # P20d+P50d win AND Q10_20=MA10/MA20 >= min
    │   │   └── strategy_P20P50cross2050.py # P20d+P50d win AND Q20_50=MA20/MA50 >= min
    │   └── _not_used/                    # PARKED, not discovered by the sweep:
    │       ├── strategy_ZOP.py, strategy_P20dZOP.py,
    │       ├── strategy_P50dZOP.py, strategy_P20dP50dZOP.py   # ZOP too volatile intraday
    │       └── run_extension.py, run_extensions.py            # only drove the ZOP extension
    ├── data/                             # scratch/temp only (not committed)
    └── report/
        ├── <strategy_name>/
        │   ├── run<N>_<YYYYMMDD>.xlsx    # one file per run (Operational + Summary + HopData sheets)
        │   ├── aggregated_summary.xlsx   # stacked summary across all runs of this strategy
        │   └── _archive/<timestamp>/     # previous runs, moved aside by run_sweep
        ├── _not_used/                    # archived report folders for the parked ZOP strategies
        ├── best_strategy.xlsx            # cross-strategy comparison (rebuilt by best_strategy.py)
        └── summary.csv                   # master append-log, one row per run (all strategies)
```

**ZOP strategies are parked** in `code/_not_used/` (reports in `report/_not_used/`). ZOP is a good
signal but too volatile intraday; refining it is postponed in favour of the more stable cross
strategies. Move the files back to restore them.

---

## Environment

- **Conda env:** `potsystem_env` — always activate; never pip/requirements.txt
- **Python:** 3.13
- **Platform:** Ubuntu server `gandalf` (SSH via `innovia.dk:2222`). The ML/data stack lives here;
  a Windows-side conda env of the same name has only pandas/numpy (no scipy/sklearn).
- **Development:** VS Code Remote-SSH from Windows

---

## Running

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env
cd ~/potentials/strategy/app/code

python run_sweep.py            # archive old runs of swept strategies, rebuild, aggregate, compare
python run_sweep.py --dry-run  # show the run plan; touch nothing
python run_sweep.py --list     # list discoverable strategy names

# Standalone pieces (run_sweep already calls these at the end):
python aggregate_summary.py ["Strategy"]   # re-aggregate one or all strategies
python best_strategy.py                     # rebuild best_strategy.xlsx only
```

To analyse the **50d** horizon instead of 20d: set `period: 50` in `sweep_config.py` (or a
strategy's PARAMS) and re-run. Everything stays one-horizon-at-a-time; the report is identical
in shape, just for 50d. Mixing 20d and 50d runs in one comparison is rejected by best_strategy.py.

---

## Data Sources

All input is read from `DATA_ROOT = /home/sm/potentials/repositoryRTBI/data/` (defined in
`shared/config.py`). Never hardcode paths.

### Matrix format (all Longi files)
- **Rows:** ticker symbols (index column, no header label)
- **Columns:** daynum integers as **strings** — newest left, oldest right
- **CSV:** European — semicolon separator `;`, comma decimal `,`
- Load with: `pd.read_csv(path, sep=';', decimal=',', index_col=0)`
- Column lookup: always `df[str(daynum)]` — never bare int

### Key files

| File | Content |
|------|---------|
| `Longi/future_gain20d.csv` | Realised forward gain over next 20 trading days (%) — `period=20` |
| `Longi/future_gain50d.csv` | Realised forward gain over next 50 trading days (%) — `period=50` |
| `Longi/longi_rank.csv` | Average rank across all performance periods (1 = best) |
| `Longi/longi_P20d_win.csv`, `longi_P50d_win.csv` | Per-ticker ML win probabilities (20d/50d) |
| `Longi/longi_rsi.csv` | RSI14 (Wilder's method) — used for `^GSPC` etc. ref context |
| `Longi/longi_ma*.csv` | Simple moving averages (cross strategies build MA quotients) |
| `data/PotDat.csv` | Raw stock prices (incl. `^VIX`) |
| `data/Stamdata.csv` | Ticker metadata: Name, Sector, GICS, Sector2, Zone, … |
| `data/Cal.csv` | daynum → date (index is float, e.g. 2055.0 — use `float(daynum)`) |

**Do not use** `Longi/longi_grp_*.csv` as per-ticker features — they are sector-row aggregates.

---

## Shared Modules

### `shared/config.py`
Constants: `DATA_ROOT`, `DATA_LONGI`, `POTDAT_PATH`, `STAMDATA_PATH`, `CAL_PATH`,
`APP_ROOT`, `REPORT_ROOT`, `SUMMARY_CSV`.

### `shared/data_loader.py`
All functions are `@lru_cache`. `load_longi(filename)`, `load_potdat()`, `load_stamdata()`,
`daynum_to_date(daynum)`.

### `shared/chain.py`  — the realizable chain (single source of truth)
```python
realizable_chain(rows, hold, no_go_threshold=None,
                 floor_daynum=None, cap_daynum=None, phase_average=False)
```
- `rows`: iterable of `(daynum, gain_pct, gspc_rsi_prev)`.
- Greedily walks hops oldest→newest, taking one only once the previous position has closed
  (spaced ≥ `hold` daynums) → **non-overlapping** positions.
- `phase_average=True` runs the chain from **every start offset in the first holding window**
  and averages, removing the anchor-sensitivity a single greedy chain has (a ±10-daynum start
  shift could otherwise halve the return). Number of phases ≈ `hold ÷ step`, capped by available
  hops. Both report generation and best_strategy use `phase_average=True`.
- `floor`/`cap` clamp the daynum range (used by best_strategy for a common comparison span).

```python
laddered_portfolio(rows, hold, step, no_go_threshold=None,
                   floor_daynum=None, cap_daynum=None)
```
- A second, economically distinct estimator over the **same** hops — a continuously-invested
  ladder of `n = hold // step` equal-weight tranches entered `step` daynums apart. Reports the
  realized CAGR of the **blended portfolio** (value-blend of the staggered sleeves), an
  always-invested / trend-following style.
- Differs from `realizable_chain` in no-go handling: a gated or missing slot is held in **cash
  (0%) on schedule** (no delayed re-entry), so tranches stay rigidly staggered.
- By construction sits at/above the phase-averaged chain CAGR (the gap = start-day dispersion the
  chain averages away). **Diagnostic only** — best_strategy shows `ladder_cagr`/`ladder_ret`/
  `ladder_n`/`ladder_inv%` as extra rows beside the chain rows, but ranking still keys on
  `chain_cagr`.

### `shared/report.py`
`save_report(strategy_name, params, hop_results, run_num=None)` writes
`run<N>_<date>.xlsx` with **three sheets** and appends one row to `app/report/summary.csv`:
- **Operational** — ticker grid + the single `avg_gain` row + day-1 ref rows + attribute counts.
- **Summary** — key/value metrics (see below).
- **HopData** — machine-readable per-hop `daynum | gain | gspc_rsi_prev` (raw numbers, *not*
  Excel formulas), so the chain can be recomputed later over any window. best_strategy reads this.

### `aggregate_summary.py`
Reads the Summary sheet from every `run*.xlsx` in a strategy folder → `aggregated_summary.xlsx`
(one row per run). Generic: any new Summary key becomes a column automatically. Still drops
legacy `acc_gain*`/`top*` columns from old files.

### `shared/extension.py` — partial-gain extension runner
Covers the recent days where the strategy's forward horizon isn't fully realized yet. The horizon
is read from `params["period"]` (loads `future_gain{period}d.csv`, so the window is ~`period`
trading days). For each entry daynum it computes partial gain `(exit_price-entry_price)/entry_price`
from PotDat up to the latest available price. `run_extension(...)` writes
`report/<strategy>/extension_<YYYYMMDD>.xlsx` and **returns its path** (or `None` if the window is
empty / no hops). Every active strategy exposes a `build_extension()` that binds its selector and
calls `run_extension`.

### `extension_of_best_strategy.py` — extend the winner
Standalone daily tool (no sweep needed; the sweep is for development). Reuses
`best_strategy.select_best_runs()` to find the highest-`chain_cagr` strategy, runs that strategy's
`build_extension()` on its winning-run params **in its own folder**, then moves the result up to
`report/` beside `best_strategy.xlsx` as `extension_<name>_<YYYYMMDD>.xlsx`. `run_sweep.py` also
calls `run()` after rebuilding `best_strategy.xlsx`.

---

## hop_results Structure

Each item in the list passed to `save_report`:

```python
{
    "daynum":          int,               # trading daynum for this hop
    "tickers":         list[str],         # focusset, rank-ordered best→worst
    "gains":           dict[str, float],  # {ticker: realised gain over `period` days, %}
    "ref_values_prev": dict[str, float],  # market context at daynum-1
    "n_survivors":     int,               # OPTIONAL — only the cross strategies set it
}
```

`ref_values_prev` keys: `^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi` (RSI14) and `^VIX` (raw price),
all at daynum-1 (the decision day, before investment).

There is a **single `gains` dict** per hop — the horizon is `period`, not two fixed horizons.

---

## Operational Sheet Layout

| Rows | Content | Colour |
|------|---------|--------|
| 1 | A1=`No_go_GSPC_rsi` label \| daynum headers | Blue |
| 2 | A2=editable No_go threshold \| date headers | A2 amber, rest blue |
| 3–(N+2) | Ticker names, rank 1→N | — |
| *(optional)* | `N_survivors` per hop — only when hops carry `"n_survivors"` (cross strategies) | Pale blue |
| next | `avg_gain` (single row; top-N avg over `period`) | Green/red/grey |
| next 4 | `^GSPC_rsi (day-1)`, `^STOXX_rsi (day-1)`, `^HSI_rsi (day-1)`, `^VIX (day-1)` | Yellow |
| … | GICS / Sector2 / Zone occurrence counts | Purple / peach / teal |

The `avg_gain` cell is an Excel formula `=IF(<gspc_rsi cell> < $A$2, "", value)` — editing the
A2 threshold recalculates the no-go suppression live. report.py computes the `^GSPC_rsi` row
position dynamically, so the optional `N_survivors` row keeps the formula correct.

---

## Summary Sheet Metrics

A flat list of `(key, value)` rows; `aggregate_summary.py` and `best_strategy.py` ingest them
generically (a new row becomes a downstream column automatically). **Horizon-agnostic names** —
one run = one horizon = one set of metrics. Write order:

| Key(s) | Meaning |
|--------|---------|
| `StrategyName`, `Run#`, `StartDaynum`, `N_hops`, `N_hops_active`, `EndDaynum` | identity / range |
| *(PARAMS keys)* | `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, `p20d_win_min`, … |
| `avg_gain` | grand average per-hop top-N gain over `period` (No_go-filtered) |
| `chain_ret`, `chain_cagr`, `chain_n` | realizable chain (phase-averaged; see below) |
| `N_loss` | count of active hops with negative avg gain |
| `Worst` | worst single active-hop avg gain |

### Averages vs accumulation (why overlap matters)
With `step < period`, consecutive hops measure **overlapping** forward windows. Overlap does
**not** bias an *average* (`avg_gain` is valid for comparing configs) but you cannot sum/compound
overlapping hops without double-counting. The realizable **chain** fixes this.

### The realizable chain (`chain_ret`/`chain_cagr`/`chain_n`)
Non-overlapping compounded backtest (see `shared/chain.py`): hops walked oldest→newest, taken
only once the previous closed (spaced ≥ `period`), gains compounded, **phase-averaged** over all
start offsets so the result doesn't swing with the anchor day. `chain_cagr` is annualized
(`_TRADING_DAYS_YEAR = 252`) and is the **primary decision metric**. Respects `No_go_GSPC_rsi`;
NaN-safe.

### `step` is fixed at 1 (and why)
A hop's gain depends only on its entry daynum, and the chain enforces ≥`period` spacing
regardless of `step`. So for a fixed start phase, step 1 and step 5 give the *identical* chain;
they differ only in how many start-offsets the phase-average samples (step 1 → `period` phases,
the finest/most reliable; step 5 → `period/5`). `step` is therefore second-order and a confound
across strategies, so `sweep_config.DEFAULTS["step"] = 1`. (`step` still affects `avg_gain`
sample size and `N_hops`, neither of which is a decision criterion.)

### Cross-strategy comparability — the common span
Each run's Summary chain is over that run's *own* span, so it is **not** comparable across
strategies (a strategy covering only recent daynums shows a bigger chain return than one spanning
a longer, choppier history). `best_strategy.py` therefore **recomputes** the chain for every run
from its HopData over the span all compared strategies share:
`floor = max(EndDaynum)`, `cap = min(StartDaynum)`, written as `chain_floor`/`chain_cap`.

> Note: win-probability strategies (P*dWin, the cross strategies) cannot backtest before
> ~daynum 1797 — the ML win/loss model needs feature warm-up (~100d) + 150 per-ticker training
> rows. Ranknow uses only `longi_rank` and spans further back, which is exactly why the common-span
> clamp is needed. (Background lives in the longi project memory.)

### Retired
`acc_gain*` (summed overlapping hops) and `top{k}_gain*` (rank-marginal curve) are gone, plus the
old `*20d`/`*50d` dual-horizon split — replaced by the single `period`.

---

## PARAMS and the No_go Filter

```python
PARAMS: dict = {
    "focusset_size": 3,       # N tickers selected per hop
    "step": 1,                # daynum step between hops (sweep fixes this at 1)
    "period": 20,             # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": 40,     # suppress avg gains / skip chain hops when GSPC RSI (day-1) < this
    # strategy-specific: p20d_win_min, p50d_win_min, q10_20_min, q20_50_min
}
```
- `No_go_GSPC_rsi` label → A3/A2 in Operational; avg_gain cells reference it via an IF formula.
- The sweep (`sweep_config.DEFAULTS`) overlays `step:1`, `period:20`, `No_go_GSPC_rsi:0`,
  `focusset_size:[3,5]`, and the linked `p_win_min` (writes both `p20d_win_min`/`p50d_win_min`).

---

## Strategy Anatomy

Minimum contract for a new strategy file:

```python
STRATEGY_NAME = "My strategy"
PARAMS = {"focusset_size": 3, "step": 1, "period": 20, "No_go_GSPC_rsi": 40}

def select_focusset(daynum, <signal_df>, n) -> list[str]:
    """n tickers ranked best→worst; [] if the daynum/data is unavailable. Never raises."""

def get_reference_values(daynum) -> dict:   # copy verbatim across strategies
    ...

def main() -> None:
    period = PARAMS.get("period", 20)
    gain_df = load_longi(f"future_gain{period}d.csv")
    # hop loop (step from PARAMS); each hop:
    #   {"daynum", "tickers", "gains": get_gains(gain_df, tickers, daynum), "ref_values_prev": ...}
    save_report(STRATEGY_NAME, PARAMS, hop_results)
```

**Rules:**
- One `gains` dict per hop, for `future_gain{period}d.csv` — never compute both horizons.
- `select_focusset` returns `[]` if a daynum/column is absent; never raises.
- `str(daynum)` for all DataFrame column lookups.
- Empty-focusset policy differs by design: Ranknow **breaks** (stops), the filtered strategies
  **skip** (`continue`) — keep that per-strategy.
- Cross strategies build an ad-hoc MA-quotient table at runtime (`build_q10_20` / `build_q20_50`,
  used like a preformed matrix) and record `"n_survivors"` per hop.

---

## best_strategy.py Output Structure

`app/report/best_strategy.xlsx` — **transposed**: metric names down column A, **one column per
strategy**, strongest `chain_cagr` leftmost.

- Each column = that strategy's **best run by `chain_cagr`** (tiebreaker `chain_ret`).
- The `chain_*` values shown are **re-clamped to the common span** (and phase-averaged); the
  `chain_floor`/`chain_cap` rows state that span. `period` is a row (all columns must match — a
  mixed-period comparison is rejected).
- Adding a strategy to the sweep makes it appear automatically as a new column.

---

## Known Data Quirks

- **Series starts at daynum 1543** — PotDat/future_gain/Longi all begin there; nothing earlier.
- **Cal.csv index is float**: `2055,00` → `2055.0`. Look up with `float(daynum)`.
- **future_gain{period}d valid from ~newest-period**: the most recent ~`period` columns are NaN
  (not yet realised). `find_start_daynum()` skips them. This makes the 20d metrics ~30 daynums
  "fresher" than 50d when comparing horizons — inherent, not a bug.
- **Win-prob (`longi_P*d_win.csv`) blank before ~1797** — model warm-up; see the common-span note.
- **Stamdata.csv first column header** is a timestamp string, not a meaningful label.

---

## Excel Styling Conventions

| Fill | Hex | Used for |
|------|-----|----------|
| Blue | `BDD7EE` | normal headers |
| Grey-blue | `D6DCE4` | strategy column header (best_strategy) |
| Yellow | `FFFF99` | parameter headers: `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, `p20d_win_min`, `p50d_win_min`, `q10_20_min`, `q20_50_min` |
| Amber | `FFE599` | editable No_go cell (Operational) |
| Green / Red | `C6EFCE` / `FFC7CE` | positive / negative gains |
| Grey | `EEEEEE` | suppressed / n/a |

The `_PARAM_COLS` set is duplicated in `aggregate_summary.py` and `best_strategy.py` — keep them
in sync when adding a strategy parameter.

---

## Coding Standards

- Type hints on all function signatures; European CSV (`sep=';', decimal=','`).
- Log to stdout; exit 0/1. No hardcoded paths — use `shared/config.py`.
- Data is **read-only** — strategy code never writes to `repositoryRTBI/`. `app/data/` is scratch.

---

## Development Notes

- VS Code Remote-SSH from Windows; Danish keyboard. Claude Code: Ctrl+Alt+C, terminal Ctrl+Æ.
- The chain math (`shared/chain.py`) is shared by generation and comparison so they can't drift.
- The chain ranking lives once in `best_strategy.select_best_runs()`; `extension_of_best_strategy.py` reuses it so the extended strategy is always the one the comparison crowned.
