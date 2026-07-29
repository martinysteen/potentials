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
    │   ├── extension.py                  # extend ALL strategies into one workbook (one sheet each)
    │   ├── shared/
    │   │   ├── config.py                 # path constants
    │   │   ├── data_loader.py            # cached CSV loaders
    │   │   ├── select.py                 # pick_by_rank — the from_rank window
    │   │   ├── engine.py                 # make_strategy + col_filter/quotient_filter/rank_by
    │   │   ├── chain.py                  # realizable_chain — the one place the chain math lives
    │   │   ├── report.py                 # per-run Excel writer (save_report) + master summary.csv
    │   │   └── extension.py              # partial-gain extension runner (period-driven)
    │   ├── strategies/                   # each = ~20-line declaration on shared/engine.py
    │   │   ├── strategy_ranknow.py       # baseline: lowest longi_rank (standalone, no filters)
    │   │   ├── strategy_Cross1020.py     # [Q10_20=MA10/MA20]
    │   │   ├── strategy_Cross2050.py     # [Q20_50=MA20/MA50]
    │   │   ├── strategy_Tally_Rank.py    # Tally build (see below), chooser = lowest longi_rank
    │   │   ├── strategy_Tally_RSI.py     # Tally build, chooser = highest RSI14
    │   │   └── strategy_Tally_2050.py    # Tally build, chooser = highest MA20/MA50 quotient
    │   └── _not_used/                    # PARKED, not discovered by the sweep:
    │       └── strategy_ZOP.py           # ZOP too volatile intraday
    ├── data/                             # scratch/temp only (not committed)
    └── report/
        ├── <strategy_name>/
        │   ├── run<N>_<YYYYMMDD>.xlsx    # one file per run (Operational + Summary + HopData sheets)
        │   ├── aggregated_summary.xlsx   # stacked summary across all runs of this strategy
        │   └── _archive/<timestamp>/     # previous runs, moved aside by run_sweep
        ├── _not_used/                    # archived report folders for the parked ZOP strategies
        ├── best_strategy_<YYYYMMDD>.xlsx # combined report: sheet 1 = cross-strategy comparison
        │                                 #   at the primary (smallest) horizon, one more sheet per
        │                                 #   further horizon (e.g. "Best Strategy 50d"), then one
        │                                 #   extension sheet per strategy (best-first)
        ├── _archive/                     # prior dated best_strategy_*.xlsx (overwrite same name)
        └── summary.csv                   # master append-log, one row per run (all strategies)
```

**The Tally strategies** (Tally_Rank / Tally_RSI / Tally_2050) are the advice product from the
`longi/expAdviceModel/` sandbox (report sections 6e-6m): the identical 3-step group build —
within-day top beta3m decile x bottom median_30d decile binned in the JOINT valid set
(`corner_filter`, `corner_bins`=10), then keep the lower-vola100d half within the survivors
(`trim_filter`, `vola_keep_frac`=0.5) — differing only by the chooser (= engine ranker): lowest
longi_rank, highest RSI14, or highest MA20/MA50 quotient. "Tally" = the group's counted
historical win/loss record (past tense by design — never presented as a forecast). 20d is the
primary horizon; the sweep also runs them at 50d (the fallback), which gets its own comparison
sheet. Buy-the-top only; buy-the-dip is out of scope by decision (low-RSI picks measured worst).

**The ZOP strategy is parked** in `code/_not_used/` (reports in `report/_not_used/`). ZOP is a good
signal but too volatile intraday; refining it is postponed in favour of the more stable cross
strategies. Move the file back to restore it. **All probability-based strategies (P20*, P50*,
P20P50*, P??dZOP) were deleted 2026-07-07** — the win/loss probability model was retired (see
`longi/expAdviceModel/` for the evidence); their report folders are archived in `report/_not_used/`.

---

## Environment

- **Conda env:** `potsystem_env` — always activate; never pip/requirements.txt
- **Python:** 3.13
- **Platform:** Ubuntu server `gandalf` (SSH via `innovia.dk:2222`). The ML/data stack lives here;
  a Windows-side conda env of the same name has only pandas/numpy (no scipy/sklearn).
- **Development:** VS Code Remote-SSH from Windows
- **Every `python` invocation goes through SSH — no exceptions:**
  `ssh -p 2222 sm@innovia.dk` then `conda activate potsystem_env`. Never invoke python directly
  on the Windows host for this project, even for quick checks.

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
python extension.py                         # build the combined best_strategy_<date>.xlsx
python best_strategy.py                     # same combined file (delegates to extension.run())
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
| `Longi/longi_rsi.csv` | RSI14 (Wilder's method) — Tally_RSI chooser + `^GSPC` etc. ref context |
| `Longi/longi_ma*.csv` | Simple moving averages (cross strategies build MA quotients) |
| `Longi/longi_beta3m.csv`, `longi_median_30d.csv`, `longi_vola100d.csv` | The Tally group build (corner + trim) |
| `Longi/longi_quot2050.csv` | MA20/MA50 speed quotient ×100 — Tally_2050 chooser |
| `data/PotDat.csv` | Raw stock prices (incl. `^VIX`) |
| `data/Stamdata.csv` | Ticker metadata: Name, Sector, GICS, Sector2, Zone, … |
| `data/Cal.csv` | daynum → date (index is float, e.g. 2055.0 — use `float(daynum)`) |

**Do not use** `Longi/longi_grp_*.csv` as per-ticker features — they are sector-row aggregates
(rows are GICS sector names, not tickers, so an inner join on ticker yields nothing). The current
families are `longi_grp_GICS_per{1d,1w,1m,3m,6m,1y}.csv` (13 rows) and
`longi_grp_Sector2_per*.csv` (50 rows), added 2026-07-29: the mean of each sector's tickers, same
shape as the matching `longi_per*.csv`.

---

## Shared Modules

### `shared/config.py`
Constants: `DATA_ROOT`, `DATA_LONGI`, `POTDAT_PATH`, `STAMDATA_PATH`, `CAL_PATH`,
`APP_ROOT`, `REPORT_ROOT`, `SUMMARY_CSV`.

### `shared/data_loader.py`
All functions are `@lru_cache`. `load_longi(filename)`, `load_potdat()`, `load_stamdata()`,
`daynum_to_date(daynum)`.

### `shared/chain.py`  — the realizable chain (single source of truth)
**Returns are ADDITIVE, not compounded.** Each lot bets the same fixed capital and the gain is
withdrawn (not reinvested), so a chain's total return is the simple **sum** of its lot gains
(`Σ gᵢ`) and the annualized figure is that sum ÷ span-years — a plain **average annual gain**, not
a compound CAGR. This deliberately avoids the exponential blow-up a compounded backtest produces
over a long history; the additive total grows only *linearly* with the number of lots.

```python
realizable_chain(rows, hold, no_go_threshold=None,
                 floor_daynum=None, cap_daynum=None, phase_average=False)
```
- `rows`: iterable of `(daynum, gain_pct, gspc_rsi)`.
- Greedily walks hops oldest→newest, taking one only once the previous position has closed
  (spaced ≥ `hold` daynums) → **non-overlapping** positions; gains are **summed** (not compounded).
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
  ladder of `n = hold // step` equal-weight tranches entered `step` daynums apart. Each sleeve
  **sums** the gains of its slots (additive, no reinvestment) and the book is the equal-weight
  **mean of the sleeve sums** — an always-invested / trend-following style.
- Differs from `realizable_chain` in no-go handling: a gated or missing slot is held in **cash
  (0%) on schedule** (no delayed re-entry), so tranches stay rigidly staggered.
- **Active-window anchored:** the span (years) and `inv%` are measured from the **first to the
  last *invested* hop**, trimming leading/trailing cash (e.g. the pre-signal warm-up daynums a
  win-prob strategy cannot trade). Without this, a late-starting strategy got padded with phantom
  cash years off the common-span floor, sinking `ladder_annual` and `inv%` far below reality.
- **Neither estimator dominates** the other. When `inv%`=100 and hops are uniformly `step`-spaced
  the sleeves *are* the chain phases, so `ladder_ret == chain_ret` exactly; but `ladder_annual`
  usually sits *below* `chain_annual` (the chain divides each phase total by that phase's own
  ragged, ~`hold`-shorter span — a smaller divisor that lifts the per-phase annual — while the
  ladder divides by one consistent full-active-window span), and with interior skips
  `ladder_ret < chain_ret` too (the ladder eats 0% cash cycles the chain skips). Ladder ≥ chain
  only for dense, skip-free strategies (e.g. Ranknow). **Diagnostic only** — best_strategy shows
  `ladder_annual`/`ladder_ret`/`ladder_n`/`ladder_inv%` as extra rows beside the chain rows, but
  ranking still keys on `chain_annual`.

### `shared/report.py`
`save_report(strategy_name, params, hop_results, run_num=None)` writes
`run<N>_<date>.xlsx` with **three sheets** and appends one row to `app/report/summary.csv`:
- **Operational** — ticker grid + the single `avg_gain` row + ref rows + attribute counts.
- **Summary** — key/value metrics (see below).
- **HopData** — machine-readable per-hop `daynum | gain | gspc_rsi` (raw numbers, *not*
  Excel formulas), so the chain can be recomputed later over any window. best_strategy reads this.

### `aggregate_summary.py`
Reads the Summary sheet from every `run*.xlsx` in a strategy folder → `aggregated_summary.xlsx`
(one row per run). Generic: any new Summary key becomes a column automatically. Still drops
legacy `acc_gain*`/`top*` columns from old files.

### `shared/extension.py` — partial-gain extension runner
Covers the recent days where the strategy's forward horizon isn't fully realized yet. The horizon
is read from `params["period"]` (loads `future_gain{period}d.csv`, so the window is ~`period`
trading days). For each entry daynum it computes partial gain `(exit_price-entry_price)/entry_price`
from PotDat up to the latest available price. `run_extension(..., workbook=None)` either writes a
standalone `report/<strategy>/extension_<YYYYMMDD>.xlsx` (returns its path) or — when given a
`workbook` — appends the content as **one sheet titled after the strategy** to that shared workbook
(returns the sheet title); `None` if the window is empty / no hops. Every active strategy exposes a
`build_extension(workbook=None)` that binds its selector and forwards `workbook` to `run_extension`.

### `extension.py` — build the single combined report
Standalone daily tool (no sweep needed; the sweep is for development) and the project's one
output entry point. Reuses `best_strategy.select_best_runs()` for the ranking and each strategy's
winning-run params. `python extension.py` (and the `run_sweep.py` auto-call) builds **one** workbook
`report/best_strategy_<YYYYMMDD>.xlsx`: **sheet 1** is the cross-strategy comparison (via
`best_strategy.fill_best_sheet`), followed by **one extension sheet per strategy, best-first** — so a
user following any strategy, not just the day's top pick, always has its recent "known future". The
prior dated workbook is moved to `report/_archive/` **only after** there is new output (same-named
archived copy overwritten; user-named keepsakes like `best_strategy_top.xlsx` are left untouched).
`python best_strategy.py` delegates here, producing the same file. (A single strategy can still be
extended to its own standalone file via `<strategy>.build_extension()`.)

---

## hop_results Structure

Each item in the list passed to `save_report`:

```python
{
    "daynum":          int,               # trading daynum for this hop
    "tickers":         list[str],         # focusset, rank-ordered best→worst
    "gains":           dict[str, float],  # {ticker: realised gain over `period` days, %}
    "ref_values":      dict[str, float],  # market context at daynum
    "n_survivors":     int,               # OPTIONAL — only the cross strategies set it
}
```

`ref_values` keys: `^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi` (RSI14) and `^VIX` (raw price),
all at daynum (the investment day).

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
| next 4 | `^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi`, `^VIX` | Yellow |
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
| `StrategyName`, `Run#`, `StartDaynum`, `N_hops`, `N_hops_active`, `EndDaynum` | identity / range. **`StartDaynum`/`EndDaynum` = the strategy's *usable* span, chronological (Start = oldest usable daynum, End = newest)** — a strategy starts where its source indicators do (e.g. MA warm-up for the cross quotients), not necessarily at the series start, even though empty warm-up hops are still recorded. `N_hops` = all evaluated hops; `N_hops_active` = hops actually invested. |
| *(PARAMS keys)* | `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, `q10_20_min`, … |
| `avg_gain` | grand average per-hop top-N gain over `period` (No_go-filtered) |
| `chain_ret`, `chain_annual`, `chain_n` | realizable chain (additive, phase-averaged; see below) |
| `origin_sens%` | spread of `chain_annual` across start origins `(max−min)/avg %` — **lower = more robust** to when you start hopping (diagnostic; never ranks) |
| `N_loss` | most negative lots in any one origin's realized chain (of `chain_n`) — worst-case count |
| `Worst` | worst single chain lot (gain%): the lowest lot over all start origins |

### Averages vs accumulation (why overlap matters)
With `step < period`, consecutive hops measure **overlapping** forward windows. Overlap does
**not** bias an *average* (`avg_gain` is valid for comparing configs) but you cannot sum
overlapping hops without double-counting. The realizable **chain** (non-overlapping) fixes this.

### The realizable chain (`chain_ret`/`chain_annual`/`chain_n`)
Non-overlapping **additive** backtest (see `shared/chain.py`): hops walked oldest→newest, taken
only once the previous closed (spaced ≥ `period`), gains **summed** (fixed capital per lot, gains
withdrawn — no reinvestment), **phase-averaged** over all start offsets so the result doesn't swing
with the anchor day. `chain_ret` is `Σ gᵢ`; `chain_annual` is that sum ÷ span-years
(`_TRADING_DAYS_YEAR = 252`) — a simple average annual gain (not a compound CAGR) and the
**primary decision metric**. Respects `No_go_GSPC_rsi`;
NaN-safe.

### Dispersion is a coherent worst-case pair (`Worst`/`N_loss`) + `origin_sens%`
`Worst` and `N_loss` (`shared/chain.chain_lot_stats`) are **not** independent averages — that
let them contradict (a mean-of-per-origin-minima could read `+0.37` beside an averaged
`N_loss=1`). They are a **worst-case pair**: `Worst` = the single lowest lot over **all** start
origins (the worst day any user could hit); `N_loss` = the **most** losers in any one origin's
chain (max, not mean). This guarantees `Worst < 0 ⇔ N_loss ≥ 1`. `avg_gain` stays the origin-mean
(a central tendency). `origin_sens%` (`chain_origin_sensitivity`) reports how much `chain_annual`
swings with the start origin, `(max−min)/|mean|·100`; **lower is better** (robust to when a user
starts). All three are computed the **same way** in `report.py` (per-run Summary, over the run's
own span) and in `best_strategy.py` (comparison sheet, over the common span), so the two files
reconcile — differing only by span, exactly like `chain_ret`. *(Retired: the old all-hops `Worst`/
`N_loss` over the full overlapping hop population.)*

### `step` is fixed at 1 (and why)
A hop's gain depends only on its entry daynum, and the chain enforces ≥`period` spacing
regardless of `step`. So for a fixed start phase, step 1 and step 5 give the *identical* chain;
they differ only in how many start-offsets the phase-average samples (step 1 → `period` phases,
the finest/most reliable; step 5 → `period/5`). `step` is therefore second-order and a confound
across strategies, so `sweep_config.DEFAULTS["step"] = 1`. (`step` still affects `avg_gain`
sample size and `N_hops`, neither of which is a decision criterion.)

### Mixed horizons — one comparison sheet per period
Runs are grouped by `period`; each horizon gets its own comparison sheet with its own common
span (chains of different hold lengths are never mixed in one table). The smallest horizon is
the primary "Best Strategy" sheet and drives the extension sheets; further horizons (e.g. the
Tally strategies' 50d fallback) each get a "Best Strategy <N>d" sheet.

### Cross-strategy comparability — the common span
Each run's Summary chain is over that run's *own* span, so it is **not** comparable across
strategies (a strategy covering only recent daynums shows a bigger chain return than one spanning
a longer, choppier history). `best_strategy.py` therefore **recomputes** the chain for every run
from its HopData over the span all compared strategies share. The span is read straight from each
run's **HopData daynum range** (NOT from the Summary `StartDaynum`/`EndDaynum`, which now carry the
per-strategy *usable* span and so differ): `floor = max(per-run oldest hop)`,
`cap = min(per-run newest hop)`, written as `chain_floor`/`chain_cap`. Each strategy's chain still
effectively starts at its own first *usable* hop within `[floor, cap]` (NaN/gated hops are skipped),
so the displayed per-strategy `StartDaynum` matches the span its chain actually used.

> Note: strategies start where their source indicators do (the cross quotients need MA warm-up).
> Ranknow uses only `longi_rank` and spans further back, which is exactly why the common-span
> clamp is needed.

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
    "No_go_GSPC_rsi": 40,     # suppress avg gains / skip chain hops when GSPC RSI (at daynum) < this
    # strategy-specific: q10_20_min, q20_50_min, corner_bins, vola_keep_frac
}
```
- `No_go_GSPC_rsi` label → A3/A2 in Operational; avg_gain cells reference it via an IF formula.
- The sweep (`sweep_config.DEFAULTS`) overlays `step`, `period`, `No_go_GSPC_rsi`,
  `focusset_size`, `from_rank` (see `sweep_config.py` for current values).

---

## Strategy Anatomy

Filter strategies are **declarations on `shared/engine.py`** — no backtest code per file.
A strategy = `STRATEGY_NAME` + `PARAMS` (the live dict the sweep overrides in place) + `FILTERS`
+ optional `ranker`. `make_strategy` returns the `(main, build_extension)` the rest of the system
discovers. The selection pipeline is:

> N filters (any longi CSV, any of `>= > <= <`) → intersect survivors → order by a **ranker**
> (any longi CSV, ascending=smaller-best or descending=larger-best) → `pick_by_rank` (`from_rank`).

```python
from shared.engine import make_strategy, col_filter, quotient_filter   # + rank_by if reordering

STRATEGY_NAME = "Cross1020"
PARAMS = {"focusset_size": 3, "step": 1, "period": 20, "No_go_GSPC_rsi": 0,
          "q10_20_min": 1.03, "from_rank": 1}
FILTERS = [
    quotient_filter("longi_ma10.csv", "longi_ma20.csv", "q10_20_min"),# MA10/MA20 >= PARAMS[param]
]
main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)
```

**To add a strategy:** drop a ~20-line file like the above into `strategies/`, then add its
`STRATEGY_NAME` (+ any threshold override, e.g. `q*_min`) to
`sweep_config.STRATEGIES`. That's it.

**Engine knobs for future ideas (no engine edit needed):**
- Other comparison: `col_filter("longi_beta1yr.csv", "beta_max", op="<")` → keeps `beta < max`.
- Other final priority: `make_strategy(..., ranker=rank_by("longi_FKplus.csv", ascending=False))`
  → picks the highest-FKplus survivors instead of the lowest rank.
- Within-day relative position instead of a fixed threshold: `bin_filter(csv, "n_bins_param")`
  (top/bottom of N equal-count bins of the day's own valid set); for a TWO-indicator corner
  cell use `corner_filter(top_csv, bottom_csv, "n_bins_param")` — binned in the joint valid
  set, byte-identical to the expAdviceModel sandbox build.
- Survivor-relative trim: `make_strategy(..., trims=[trim_filter(csv, "frac_param")])` —
  applied after the FILTERS intersection, in order, each keeping a fraction ranked WITHIN
  the then-current survivor set (e.g. the Tally low-vola half).

**Rules / invariants the engine already enforces:**
- One `gains` dict per hop, for `future_gain{period}d.csv` — never both horizons.
- Selection returns `[]` when a daynum/column is absent; never raises; `str(daynum)` for all lookups.
- Empty-focusset policy: filter strategies **skip** (record a cash hop and `continue`). `Ranknow` is
  the lone **standalone** file (no filters, **breaks** on no-pick) — left off the engine by design.
- `n_survivors` is recorded (→ `N_survivors` report row) automatically when a strategy has **≥2
  filters**, matching the historical cross-strategy behaviour.
- `quotient_filter` builds the ad-hoc MA quotient (e.g. MA10/MA20) at runtime, used like a
  preformed matrix — replacing the old per-file `build_q10_20`/`build_q20_50`.

---

## Comparison Sheet Structure

Sheet 1 ("Best Strategy") of `app/report/best_strategy_<YYYYMMDD>.xlsx`, written by
`best_strategy.fill_best_sheet` — **transposed**: metric names down column A, **one column per
strategy**, strongest `chain_annual` leftmost.

- Each column = that strategy's **best run by `chain_annual`** (tiebreaker `chain_ret`).
- The `chain_*` values shown are **re-clamped to the common span** (and phase-averaged); the
  `chain_floor`/`chain_cap` rows state that span. `period` is a row (all columns must match — a
  mixed-period comparison is rejected).
- Two side-by-side tables share the strategy columns: a left **chained** table and a right
  **Ladder investment** table, row-aligned via `_CHAINED_KEYS` + `_CHAIN_TO_LADDER`. The two
  title rows (1–2) are dynamic (newest daynum/date + horizon).
- `StartDaynum`/`EndDaynum` rows show each strategy's **usable span** (chronological; differ by
  strategy). **`N_hops`/`N_hops_active` are NOT shown** here (dropped as redundant — `chain_n`
  on the left and `ladder_n` on the right carry the counts).
- `chain_inv%` (left) / `ladder_inv%` (right) are a paired row: the share of the **active span**
  each estimator was actually invested. Both fall below 100% when **No_go gating** *or* **too few
  survivors to fill `focusset_size`** (→ NaN-gain no-pick day) leave a slot uninvestable. The
  serial chain only needs one usable day per `hold`, so it shrugs off scattered gating and
  `chain_inv%` sits **≥** `ladder_inv%` (which buys every slot); they diverge most when gating is
  scattered, and converge when a dry spell lasts longer than `hold`. Computed in `reclamp_chains`
  (chain via `shared.chain.chain_inv_pct`), best_strategy-only like the other ladder diagnostics.
- `origin_sens%` is a **chain-only** row (maps to `None` in `_CHAIN_TO_LADDER`, absent from the
  ladder table). Not because a ladder is inherently origin-free, but because it **diversifies the
  sensitivity away**: origin-sensitivity is a property of the strategy's phase-set (how differently
  the `period`-spaced chains perform by start day), and the ladder holds all `n = hold/step` entry
  origins at once, so its blend is their exact average (`blend = Σ(hops)/n`, independent of the
  start) → `origin_sens → 0` when `step ≪ period`, returning to the full chain swing only at the
  `n = 1` edge (`step = period`, ladder ≡ a single serial chain). The serial chain, which picks one
  origin, is the estimator that actually feels it — so the metric lives on the chain side. (With the
  sweep's `step = 1`, `n = hold`, so the ladder blend's own `origin_sens%` is ~0 by construction.)
  `Worst`/`N_loss` are the worst-case pair (see chain section); the ladder side keeps its own
  independent `ladder_worst`/`ladder_n_loss`.
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
| Yellow | `FFFF99` | parameter headers: `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, `q10_20_min`, `q20_50_min`, `corner_bins`, `vola_keep_frac` |
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
- The chain ranking lives once in `best_strategy.select_best_runs()`; `extension.py` reuses it for the ranking order and each strategy's winning-run params (extending all strategies best-first into one workbook).
