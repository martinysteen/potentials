
# Strategy_grp Backtesting — Context for Claude Code

## Purpose

Framework for backtesting **named stock-selection strategies** against historical Potentials data.
Each strategy defines a *focusset selector* (picks N tickers for a given trading day) and the
framework measures how those picks performed over a single forward horizon — the **`period`**
parameter (20 or 50 trading days; default 20).

Output is Excel reports — not new data files — stored under `app/report/`.

**This project is a standalone sibling of `../strategy/`.** It shares the same generic backtest
engine and reporting machinery (copied in verbatim — see below), and reads the same underlying
data in `../repositoryRTBI/`, but defines and tests its **own** named strategies, selected by
principles distinct from `strategy`'s. **No strategy, config entry, or report from `strategy` is
reused as data here** — `strategy`'s strategies (Ranknow, Cross1020/2050, Tally_Rank/RSI/2050) and
its report history only ever served as a *structural template* for how this pipeline is shaped, and
have been stripped back out. This project's own named strategies, once defined, are tested one by
one via the sweep, with results assembled into this project's own `best_strategy.xlsx` —
independent of `strategy`'s roster and history.

**Current status: the DomGICS_* family (GICS-sector "domination") is the first named strategy
group** — `DomGICS_now`, `DomGICS_20d`, `DomGICS_50d`, registered in `sweep_config.py`. See
"GICS Domination Strategy Family" below for the selection logic and `shared/dominance.py` for
the implementation. Add further strategies (filter-based or otherwise) the same way: drop a file
in `strategies/`, register it in `sweep_config.py`, and it shows up everywhere automatically.

---

## Directory Structure

```
strategy_grp/
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
    │   │   ├── extension.py              # partial-gain extension runner (period-driven)
    │   │   └── dominance.py              # GICS-domination pipeline for DomGICS_* (see below)
    │   ├── run_config.py                 # tunables for the DomGICS_* family (separate from sweep_config.py)
    │   └── strategies/
    │       ├── strategy_DomGICS_now.py   # dominating GICS THIS daynum
    │       ├── strategy_DomGICS_20d.py   # + persistence over trailing 20 daynums
    │       └── strategy_DomGICS_50d.py   # + persistence over trailing 50 daynums
    ├── data/                             # scratch/temp only (not committed)
    └── report/                           # populated once strategies run
        ├── <strategy_name>/
        │   ├── run<N>_<YYYYMMDD>.xlsx    # one file per run (Operational + Summary + HopData sheets)
        │   ├── aggregated_summary.xlsx   # stacked summary across all runs of this strategy
        │   └── _archive/<timestamp>/     # previous runs, moved aside by run_sweep
        ├── best_strategy_<YYYYMMDD>.xlsx # combined report: sheet 1 = cross-strategy comparison
        │                                 #   at the primary (smallest) horizon, one more sheet per
        │                                 #   further horizon, then one extension sheet per strategy
        ├── _archive/                     # prior dated best_strategy_*.xlsx (overwrite same name)
        └── summary.csv                   # master append-log, one row per run (all strategies)
```

---

## Environment

- **Conda env:** `potsystem_env` — always activate; never pip/requirements.txt
- **Python:** 3.13
- **Platform:** Ubuntu server `gandalf` (SSH via `innovia.dk:2222`). The ML/data stack lives here;
  a Windows-side conda env of the same name has only pandas/numpy (no scipy/sklearn).
- **Development:** VS Code Remote-SSH from Windows
- **Every `python` invocation goes through SSH — no exceptions:**
  `ssh -p 2222 sm@innovia.dk` then `conda activate potsystem_env`. Never invoke python directly
  on the Windows host for this project, even for quick checks, because python is not installed there.

---

## Running

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env
cd ~/potentials/strategy_grp/app/code

python run_sweep.py            # archive old runs of swept strategies, rebuild, aggregate, compare
python run_sweep.py --dry-run  # show the run plan; touch nothing
python run_sweep.py --list     # list discoverable strategy names

# Standalone pieces (run_sweep already calls these at the end):
python aggregate_summary.py ["Strategy"]   # re-aggregate one or all strategies
python extension.py                         # build the combined best_strategy_<date>.xlsx
python best_strategy.py                     # same combined file (delegates to extension.run())

# Out-of-sample check (read-only; touches none of the files above):
python walkforward.py                       # walk-forward score of the sweep_config grid
python walkforward.py --wide                # add numeric axes for a real selection test
python walkforward.py --dry-run             # fold layout + grid size only
```

To analyse the **50d** horizon instead of 20d: set `period: 50` in `sweep_config.py` (or a
strategy's PARAMS) and re-run. Everything stays one-horizon-at-a-time; the report is identical
in shape, just for 50d. Mixing 20d and 50d runs in one comparison is rejected by best_strategy.py.

---

## Data Sources

All input is read from `DATA_ROOT = /home/sm/potentials/repositoryRTBI/data/` (defined in
`shared/config.py`) — the same data source `../strategy/` reads. Never hardcode paths.

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
| `Longi/longi_rsi.csv` | RSI14 (Wilder's method) |
| `Longi/longi_ma*.csv` | Simple moving averages |
| `Longi/longi_beta3m.csv`, `longi_median_30d.csv`, `longi_vola100d.csv` | Beta / momentum / volatility factors |
| `data/PotDat.csv` | Raw stock prices (incl. `^VIX`) |
| `data/Stamdata.csv` | Ticker metadata: Name, Sector, GICS, Sector2, Zone, … |
| `data/Cal.csv` | daynum → date (index is float, e.g. 2055.0 — use `float(daynum)`) |

Full factor set (all in `Longi/`, see `../repositoryRTBI/data/Longi/`): trailing returns
(`longi_per1d/1w/1m/3m/6m/1y`), moving averages & ratios (`longi_ma10/20/50/200`,
`longi_PdivMA*`), momentum (`longi_macd_*`), beta (`longi_beta3m/6m/1yr`), volatility/spread
(`longi_vola20d/100d`, `longi_spr100d/250d`), medians (`longi_median_10..100d`), MA-cross
quotients (`longi_quot1020`, `longi_quot2050`), composite rank (`longi_rank`), plus normalized
prices (`PotNdx.csv`), a rich ranking snapshot (`PotRank.csv`), and historical fundamentals
(`Yfinance/StockData2_stacked.csv` — P/E, margins, growth, analyst targets) not yet tapped by
any strategy in `../strategy/`.

*(The `Longi/longi_grp_*.csv` sector-row aggregates were deleted 2026-07-29 — never usable as
per-ticker features. Any lingering copy in `repositoryRTBI/` is stale.)*

---

## Shared Modules

(`config.py`/`data_loader.py`/`select.py`/`engine.py`/`chain.py`/`report.py`/`extension.py` are
identical to `../strategy/shared/` — copied verbatim; keep in sync manually if the engine improves.
`dominance.py` is new to this project — see below.)

### `shared/config.py`
Constants: `DATA_ROOT`, `DATA_LONGI`, `POTDAT_PATH`, `STAMDATA_PATH`, `CAL_PATH`, `APP_ROOT`, `REPORT_ROOT`, `SUMMARY_CSV`.

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
  last *invested* hop**, trimming leading/trailing cash. Without this, a late-starting strategy
  got padded with phantom cash years off the common-span floor, sinking `ladder_annual` and `inv%`
  far below reality.
- **Neither estimator dominates** the other. When `inv%`=100 and hops are uniformly `step`-spaced
  the sleeves *are* the chain phases, so `ladder_ret == chain_ret` exactly; but `ladder_annual`
  usually sits *below* `chain_annual`, and with interior skips `ladder_ret < chain_ret` too.
  **Diagnostic only** — best_strategy shows `ladder_annual`/`ladder_ret`/`ladder_n`/`ladder_inv%`
  as extra rows beside the chain rows, but ranking still keys on `chain_annual`.

### `shared/report.py`
`save_report(strategy_name, params, hop_results, run_num=None)` writes
`run<N>_<date>.xlsx` with **three sheets** and appends one row to `app/report/summary.csv`:
- **Operational** — ticker grid + the single `avg_gain` row + ref rows + attribute counts.
- **Summary** — key/value metrics (see below).
- **HopData** — machine-readable per-hop `daynum | gain | gspc_rsi | mkt_gain | beta` (raw
  numbers, *not* Excel formulas), so the chain — and `avg_alpha`/`avg_beta` with it — can be
  recomputed later over any window. best_strategy reads this.

### `aggregate_summary.py`
Reads the Summary sheet from every `run*.xlsx` in a strategy folder → `aggregated_summary.xlsx`
(one row per run). Generic: any new Summary key becomes a column automatically.

### `shared/extension.py` — partial-gain extension runner
Covers the recent days where the strategy's forward horizon isn't fully realized yet. The horizon
is read from `params["period"]` (loads `future_gain{period}d.csv`, so the window is ~`period`
trading days). For each entry daynum it computes partial gain `(exit_price-entry_price)/entry_price`
from PotDat up to the latest available price. `run_extension(..., workbook=None)` either writes a
standalone `report/<strategy>/extension_<YYYYMMDD>.xlsx` (returns its path) or — when given a
`workbook` — appends the content as **one sheet titled after the strategy** to that shared workbook
(returns the sheet title); `None` if the window is empty / no hops. Every active strategy exposes a
`build_extension(workbook=None)` that binds its selector and forwards `workbook` to `run_extension`.

Below `avg_partial_gain` it writes the same benchmark block as the main Operational sheet —
`mkt_partial_gain`, `alpha`, and (when `longi_beta3m.csv` loads) `beta`. The benchmark here is
computed **differently and must stay that way**: `_market_partial_gain` takes the equal-weighted
cross-sectional mean of every ticker's partial price return over the same still-open window,
because `future_gain{period}d` by definition does not exist yet for these entries — that is the
whole reason the extension exists. In a flat tape these rows mostly restate `avg_partial_gain`;
they earn their place in an index selloff, where an open position's loss belongs to the market
rather than to the picks. Row offsets advance through `next_row`, so inserting the block could
not desync the informational/ref rows the way it did on the main sheet.

### `shared/dominance.py` — GICS-domination pipeline (new, not from `../strategy/`)
The preprocessing stage behind the DomGICS_* family — see "GICS Domination Strategy Family" below
for the full write-up. `make_dom_strategy(strategy_name, params, dom_col)` is this module's
`make_strategy()` analog: it returns the same `(main, build_extension)` pair, so a DomGICS_*
strategy file is still a short declaration, just built on this pipeline instead of the filter chain.

### `extension.py` — build the single combined report
Standalone daily tool (no sweep needed; the sweep is for development) and the project's one
output entry point. Reuses `best_strategy.select_best_runs()` for the ranking and each strategy's
winning-run params. `python extension.py` (and the `run_sweep.py` auto-call) builds **one** workbook
`report/best_strategy_<YYYYMMDD>.xlsx`: **sheet 1** is the cross-strategy comparison (via
`best_strategy.fill_best_sheet`), followed by **one extension sheet per strategy, best-first** — so a
user following any strategy, not just the day's top pick, always has its recent "known future". The
prior dated workbook is moved to `report/_archive/` **only after** there is new output (same-named
archived copy overwritten; user-named keepsakes are left untouched).
`python best_strategy.py` delegates here, producing the same file.

---

## hop_results Structure

Each item in the list passed to `save_report`:

```python
{
    "daynum":          int,               # trading daynum for this hop
    "tickers":         list[str],         # focusset, rank-ordered best→worst
    "gains":           dict[str, float],  # {ticker: realised gain over `period` days, %}
    "ref_values":      dict[str, float],  # market context at daynum
    "n_survivors":     int,               # OPTIONAL — set when a strategy has ≥2 filters
    "dom_cutoff":      float,             # OPTIONAL — DomGICS_* only: that daynum's Step-1
                                           # dominance cutoff (see dominance_cutoff row/avg)
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
| 3 *(optional)* | `dominance_cutoff` per hop — only when hops carry `"dom_cutoff"` (DomGICS_* family); label (A) bold, data cells plain text | Pale green |
| next N rows | Ticker names, rank 1→N | — |
| *(optional)* | `N_survivors` per hop — only when hops carry `"n_survivors"` | Pale blue |
| next | `avg_gain` (single row; top-N avg over `period`) | Green/red/grey |
| next 2 | `mkt_gain` (benchmark for that daynum) and `alpha` (`avg_gain − mkt_gain`) | Green/red/grey |
| *(optional)* | `beta` — mean `beta3m` of the focusset; only when `longi_beta3m.csv` loads | Pale grey |
| next 2 per informational attribute | `<attr>_mean` / `<attr>_median` | — |
| next 4 | `^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi`, `^VIX` | Yellow |
| … | GICS / Sector2 / Zone occurrence counts | Purple / peach / teal |

`avg_gain`, `mkt_gain` and `alpha` are all Excel formulas `=IF(<gspc_rsi cell> < $A$2, "", value)`
— editing the A2 threshold recalculates the no-go suppression live, and all three blank together
(a visible alpha beside a blanked `avg_gain` would read as a trade the strategy never took).
`beta` is a plain value that greys out under the gate.

**Row offsets are derived, never re-added.** `_fill_operational` computes `ticker_top` →
`avg_top` → `bench_top` → `info_top` → `ref_top` as a single chain, each from the one above.
This used to be four independent copies of the same running sum, and inserting the benchmark
rows desynced them: the ref rows overwrote the informational rows while the No_go formula
pointed at `^VIX` instead of `^GSPC_rsi`. If you add a section, add its height to the chain —
do not write out the sum again.

---

## Summary Sheet Metrics

A flat list of `(key, value)` rows; `aggregate_summary.py` and `best_strategy.py` ingest them
generically (a new row becomes a downstream column automatically). **Horizon-agnostic names** —
one run = one horizon = one set of metrics. Write order:

| Key(s) | Meaning |
|--------|---------|
| `StrategyName`, `Run#`, `StartDaynum`, `N_hops`, `N_hops_active`, `EndDaynum` | identity / range. **`StartDaynum`/`EndDaynum` = the strategy's *usable* span, chronological** — a strategy starts where its source indicators do, not necessarily at the series start. `N_hops` = all evaluated hops; `N_hops_active` = hops actually invested. |
| *(PARAMS keys)* | `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, … |
| `dominance_cutoff_avg` | DomGICS_* only — run-average of the per-daynum Step-1 dominance cutoff; inserted right after `dominance_attribute_direction` here and in `aggregated_summary.xlsx`; shown in `best_strategy.py`'s comparison sheet as the row directly below `dom_count_threshold` |
| `avg_gain` | grand average per-hop top-N gain over `period` (No_go-filtered) |
| `avg_alpha` | same hops, measured against the benchmark instead of against zero — **active return, not Jensen's alpha** (see below) |
| `avg_beta` | mean `beta3m` of the picks; omitted when `longi_beta3m.csv` is absent. Not a performance metric — the number you discount `avg_alpha` by |
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
**primary decision metric**. Respects `No_go_GSPC_rsi`; NaN-safe.

### Dispersion is a coherent worst-case pair (`Worst`/`N_loss`) + `origin_sens%`
`Worst` and `N_loss` (`shared/chain.chain_lot_stats`) are **not** independent averages — they are
a **worst-case pair**: `Worst` = the single lowest lot over **all** start origins; `N_loss` = the
**most** losers in any one origin's chain (max, not mean). This guarantees `Worst < 0 ⇔ N_loss ≥ 1`.
`avg_gain` stays the origin-mean (a central tendency). `origin_sens%` (`chain_origin_sensitivity`)
reports how much `chain_annual` swings with the start origin, `(max−min)/|mean|·100`; **lower is
better**. All three are computed the **same way** in `report.py` (per-run Summary, over the run's
own span) and in `best_strategy.py` (comparison sheet, over the common span).

### `step` is fixed at 1 (and why)
A hop's gain depends only on its entry daynum, and the chain enforces ≥`period` spacing
regardless of `step`. So for a fixed start phase, step 1 and step 5 give the *identical* chain;
they differ only in how many start-offsets the phase-average samples. `step` is therefore
second-order and a confound across strategies, so `sweep_config.DEFAULTS["step"]` should stay low.

### Mixed horizons — one comparison sheet per period
Runs are grouped by `period`; each horizon gets its own comparison sheet with its own common
span (chains of different hold lengths are never mixed in one table). The smallest horizon is
the primary "Best Strategy" sheet and drives the extension sheets.

### Cross-strategy comparability — the common span
Each run's Summary chain is over that run's *own* span, so it is **not** comparable across
strategies. `best_strategy.py` therefore **recomputes** the chain for every run from its HopData
over the span all compared strategies share: `floor = max(per-run oldest hop)`,
`cap = min(per-run newest hop)`, written as `chain_floor`/`chain_cap`.

### Every figure in best_strategy.xlsx is IN-SAMPLE
The sweep scores each parameter-set over the whole history and reports the winner's score over
that same history. That number is biased upward by however many sets were tried, and it cannot
say whether the winner would have been picked *in advance*. `walkforward.py` answers that
separately (below); nothing in the sweep path corrects for it.

Two specific traps this exposes:
* **`chain_annual` is degenerate on sparse configs — GUARDED, see below.** `_additive` divides
  the additive sum by the chain's own span, so a parameter-set that realizes a single lucky lot
  annualizes it over ~one holding window and posts a headline in the hundreds. Seen for real: a
  `dominance_threshold_decile=0.05, tickers_per_gics=2` config scored 445 on one lot — and
  because `best_run()` ranks on `chain_annual`, it would have *become* that strategy's column,
  displacing a healthy 31-lot run. Inspecting the run file does not help when the healthy run is
  the one pushed out. Now floored by `run_config.MIN_CHAIN_LOTS`.
* **Absolute return cannot separate a good strategy from a good market — ADDRESSED.** This is
  what made the 2026-05/06 drawdown legible (picks −10.3% while the market was −0.2%: the loss
  was the strategy's, not the tape's). Now reported as `alpha`/`avg_alpha` throughout — see the
  next section for what it is and, importantly, what it is not.

### `alpha` here is ACTIVE RETURN, not Jensen's alpha
`alpha = focusset gain − benchmark gain` for the same daynum. It assumes **β = 1** and a zero
risk-free rate, and fits no regression. Jensen's alpha is the intercept of
`R_p − R_f = α + β(R_m − R_f) + ε` — a different quantity.

The distinction is **not academic for this strategy**: the focusset runs at ~1.7× market beta
(mean `beta3m` 1.68; 1.87 realized by regression on 20d hops). Measured over all hops, active
return is **+7.04** where the regression intercept is **+5.57** — roughly 1.5 points of the
apparent edge is levered market exposure rather than selection. That is exactly why `beta` /
`avg_beta` is reported beside it: **read the two together and discount alpha when beta is high.**

Jensen's alpha was considered and rejected: it needs a fitted β, and with ~31 *independent* 20d
lots (124 hops overlapping 4× at `step=5`) and R² ≈ 0.05, the intercept carries more estimation
noise than the correction removes. Active return is definitional — nothing to estimate, nothing
to drift run-to-run.

**Benchmark** = the equal-weighted cross-sectional mean of *every* ticker that daynum,
deliberately not a cap-weighted index: "the average stock you could have picked that day" is the
right counterfactual for a stock picker.

**Alpha is a post-hoc attribution, not a trading signal.** It says the loss was the stocks rather
than the tape, *after* the horizon closes. Its job is to let you validate a candidate pre-trade
gate — without it you cannot tell a gate that dodges bad picks from one that merely dodges bad
weeks. A search over entry-time observables (GSPC RSI, VIX, breadth, focusset RSI/MACD, sector
rollover) found **no usable pre-signal**: every |r| ≤ 0.16 and every quartile pattern was either
non-monotone or sign-flipped between the early and late halves of the history. Leaving
`NO_GO_GSPC_RSI` at 0 is the defensible reading of that.

**Span consistency**: `best_strategy.py` recomputes `avg_alpha`/`avg_beta` over the **common
span and the chain's own lots**, exactly as it does `avg_gain` — via `shared.chain.chain_lot_alpha`,
which shares `_filter_usable_ext`'s single hop-selection rule. `HopData` therefore carries
`mkt_gain` and `beta` columns; `beta` in particular cannot be recovered later, since it needs the
hop's tickers and HopData does not store them. Runs written before those columns existed still
load — they just yield a blank alpha rather than breaking the comparison.

### `MIN_CHAIN_LOTS` — the eligibility floor (not a warning, not a stop)
`run_config.MIN_CHAIN_LOTS` (default 4) is the minimum lots a run's chain must realize before it
may **represent** its strategy in `best_strategy.xlsx`. Deliberately an eligibility rule, not
either of the alternatives:
* **Not a hard stop.** A narrow decile is legitimate exploration, and `run_sweep.run_strategy`
  catches per-run exceptions — a `raise` would silently drop the run, the opposite of visible.
* **Not a warning alone.** Console output scrolls past and the artifact outlives it; the wrong
  number would still sit in the comparison sheet as the strategy's headline.

Behaviour in `best_run()`:
1. Runs below the floor cannot win a column. Nothing else changes — every run still executes,
   still writes its `run*.xlsx`, still appears in `aggregated_summary.xlsx`.
2. If **every** run of a strategy is below the floor, the best available is returned with
   `thin=True` rather than `None` — a strategy silently missing from the comparison is worse
   than one shown with a flag.
3. A flagged column is orange (`_THIN_FILL`, `F8CBAD`) on its header plus the two telling rows,
   `chain_annual` and `chain_n`, with a one-line explanation written into B1. The note is
   written only when a column actually carries the colour. Note the orange is deliberately
   *not* `_BEST_FILL`'s amber, which already means "Best overall".
4. `select_best_runs(verbose=True)` prints one line per excluded run.

`chain_inv%` does **not** substitute for this: it is measured over the ACTIVE window (first to
last invested hop), so two adjacent lots read as 100%.

---

## walkforward.py — out-of-sample evaluation

Read-only harness. Writes only `app/report/walkforward_<date>.xlsx`; never touches `run*.xlsx`,
`aggregated_summary.xlsx`, `summary.csv` or `best_strategy*.xlsx`, and changes no selection
logic. Covers `DomGICS_*` only — it rebuilds picks through the dominance pipeline itself (so it
can re-score a window without re-running a report), which is why `make_dom_strategy` tags
`main.dom_col`.

Per strategy, over rolling folds:

```
train = [oldest .. T - period]     pick the best parameter-set by chain_annual here
test  = [T + 1 .. T + test_len]    score THAT set here, never re-picking
T += test_len
```

`T - period` is an **embargo, not an off-by-one**: a hop entered at daynum `d` does not realize
until `d + period`, so training up to `T` would let a hop closing inside the test window vote on
the parameter choice. Without it the whole exercise leaks.

Key columns (Summary sheet):
| column | meaning |
|---|---|
| `is_avg_gain` / `is_alpha` | selected set on its own training window — what the sweep would report |
| `oos_avg_gain` / `oos_alpha` | same set on the untouched test window |
| `gain_gap` / `alpha_gap` | `oos − is`. **The overfit measure.** Negative = the edge evaporates |
| `zeroskill_*` | mean OOS across *every* candidate — what no selection skill gets |
| `selection_skill_*` | `oos(selected) − zeroskill`. ~0 means the sweep is fitting noise |
| `is_annual` / `oos_annual` | `chain_annual`, for continuity only — unstable on a short fold (see trap above), do not rank on it |

Fold geometry is constrained by a short history: ~2.5 years ⇒ only ~30 **independent** 20d lots
in total. Defaults `--min-train 315` (~15 months) and `--test-len 63` (~3 months) give 5 folds;
per-fold figures are noisy by construction, so read the pooled rows. Lots also overlap 4× at
`step=5`/`hold=20`, so ~54 pooled OOS lots ≈ ~13 independent ones — suggestive, not conclusive.

`--wide` adds numeric axes (`WIDE_AXES`) because the live `sweep_config` grid is 2 candidates,
far too few for `selection_skill` to have power. It deliberately does **not** invent
`priority_attribute` values: their direction must come from
`run_config.PRIORITY_ATTRIBUTE_DICTIONARY` and is not the harness's to guess.

---

## PARAMS and the No_go Filter

```python
PARAMS: dict = {
    "focusset_size": 3,       # N tickers selected per hop
    "step": 1,                # daynum step between hops (sweep fixes this at 1)
    "period": 20,             # forward horizon in trading days (20 or 50)
    "No_go_GSPC_rsi": 40,     # suppress avg gains / skip chain hops when GSPC RSI (at daynum) < this
    # strategy-specific keys as needed
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

STRATEGY_NAME = "MyNewStrategy"
PARAMS = {"focusset_size": 3, "step": 1, "period": 20, "No_go_GSPC_rsi": 0,
          "some_threshold": 1.03, "from_rank": 1}
FILTERS = [
    col_filter("longi_someindicator.csv", "some_threshold", op=">="),
]
main, build_extension = make_strategy(STRATEGY_NAME, PARAMS, FILTERS)
```

**To add a strategy:** drop a ~20-line file like the above into `strategies/`, then add its
`STRATEGY_NAME` (+ any threshold override) to `sweep_config.STRATEGIES` and `STRATEGY_ORDER`.
That's it.

**Engine knobs available (no engine edit needed):**
- Comparison filter: `col_filter(csv, "param_name", op="<"/"<="/">"/">=")`.
- Ratio filter: `quotient_filter(num_csv, den_csv, "param_name")` — builds the ratio at runtime.
- Within-day relative position instead of a fixed threshold: `bin_filter(csv, "n_bins_param")`
  (top/bottom of N equal-count bins of the day's own valid set); for a TWO-indicator corner
  cell use `corner_filter(top_csv, bottom_csv, "n_bins_param")` — binned in the joint valid set.
- Custom priority ranker: `make_strategy(..., ranker=rank_by(csv, ascending=True/False))`.
- Survivor-relative trim: `make_strategy(..., trims=[trim_filter(csv, "frac_param")])` —
  applied after the FILTERS intersection, keeping a fraction ranked WITHIN the current
  survivor set.

**Rules / invariants the engine already enforces:**
- One `gains` dict per hop, for `future_gain{period}d.csv` — never both horizons.
- Selection returns `[]` when a daynum/column is absent; never raises; `str(daynum)` for all lookups.
- Empty-focusset policy: filter strategies **skip** (record a cash hop and `continue`) by default.
- `n_survivors` is recorded (→ `N_survivors` report row) automatically when a strategy has **≥2
  filters**.
- `quotient_filter` builds the ad-hoc ratio (e.g. MA10/MA20) at runtime, used like a preformed matrix.

---

## GICS Domination Strategy Family

`DomGICS_now`/`DomGICS_20d`/`DomGICS_50d` are **not** filter-chain declarations — `shared/engine.py`'s
per-ticker filters have no group-by-sector aggregation or trailing-window primitive, so this family
is built on a separate pipeline, `shared/dominance.py`. It still produces the exact same `hop_results`
shape (see below), so reporting/aggregation/comparison all work unmodified.

**Three distinct attribute roles — three different names. This distinction has been a recurring
source of confusion (a prior stranded rename broke the sweep entirely); it is now load-bearing
naming, not just documentation:**

**Selection logic, per daynum:**
1. **Step 1 — GICS elevation, "dominance" (`gics_dominance_now`)**: count tickers per `GICS`
   (from `Stamdata.csv`) that "beat" **that day's own best-decile cutoff** of
   `longi_{dominance_attribute}.csv` — below the cutoff when `dominance_attribute_direction`
   (smaller wins, e.g. rank, the default), above it otherwise (bigger wins). `dominance_threshold_decile`
   (default `0.10`) is a **fraction, not a raw value**: `shared.dominance._daily_decile_cutoff`
   computes the value at that quantile of the attribute's *cross-sectional distribution on that one
   daynum* (every ticker, that day only — computed independently day by day, not across history),
   so the same fraction means "best 10%" for any attribute regardless of its raw scale (rank
   1..~1200, rsi 0..100, beta3m usually <5, ...), on every individual day. A GICS with
   `>= dom_count_threshold` (default 10) such tickers is "dominating" **that daynum** — `dom_now`.
   `dominance_attribute` is still a **single fixed value, never swept** by `sweep_config.py` — not
   because of a scale mismatch anymore (the decile cutoff fixed that), but because each candidate
   attribute is meant to be tried as its own independent run, one at a time, with results compared
   and noted outside the system. **The day's cutoff value is itself reported**: it lands as a
   `dominance_cutoff` row at row 3 of the Operational sheet (just under the date row, above the
   ticker rows, plain-text data cells — only the row label in column A is bold) in every
   `run*.xlsx`, and its run-average as a `dominance_cutoff_avg` row in the Summary sheet
   (immediately after `dominance_attribute_direction`), which `aggregate_summary.py` then carries
   into `aggregated_summary.xlsx` automatically (yellow param-header fill, via `_PARAM_COLS`).
   `best_strategy.py`'s cross-strategy comparison sheet shows it too, as the fixed `_CHAINED_KEYS`
   row directly below `dom_count_threshold`.
2. **Persistence (`add_persistence`)**: `dom_20d`/`dom_50d` additionally require `dom_now` to have
   held on at least `persistence_frac` (default 2/3) of the trailing 20/50 daynums (inclusive of
   the current one). `DomGICS_now`/`_20d`/`_50d` each key off one of `dom_now`/`dom_20d`/`dom_50d`.
3. **Step 2 — test-set construction, ticker selection (`select_focusset`)**: each dominating GICS
   contributes its `tickers_per_gics` (default 3) **best** tickers by
   `longi_{priority_attribute}.csv` (direction-aware: smaller wins when
   `priority_attribute_direction`, bigger otherwise) — or its **worst** `tickers_per_gics` when
   `from_rank=-1`, so a bottom-pick draws from genuinely weak tickers rather than the weakest of
   an already-best-biased pool. The pooled candidates across all dominating GICS sectors are then
   re-ranked **globally** by that same value and `focusset_size`/`from_rank` applied via
   `shared.select.pick_by_rank` (`from_rank`: `1`=best n, `-1`=worst n) — same "smaller is better"
   convention `rank_by(..., ascending=False)` uses (negate a bigger-wins series before ranking).
   Unlike Step 1, it's genuinely unclear which attribute makes the best selection criterion, so
   `run_config.PRIORITY_ATTRIBUTE_DICTIONARY` (`dict[attribute, direction]`) enumerates every
   candidate worth testing; `sweep_config.py` sweeps across **all** of them, one independent
   test-set (run) per entry, deriving each run's direction from the dictionary so a name can never
   be paired with the wrong direction (see `sweep_config.py`'s "Sweeping priority_attribute").
4. **Step 3 — informational only (display)**: `informational_attributes` (default
   `["per1d", "macd_histogram"]`) never affects dominance, test-set construction, or selection —
   it only adds `<attr>_mean`/`<attr>_median` rows to `run*.xlsx`/extension sheets for insight into
   what's going on along the timeline. May be a single Longi factor short name or a list.

**`dominance_attribute`/`priority_attribute`/`informational_attributes`** are Longi factor **short
names** (the `longi_<name>.csv` part only, e.g. `"rank"`, `"per1d"`, `"rsi"`, `"beta3m"`) — set
them via `run_config.DOMINANCE_ATTRIBUTE`/`run_config.PRIORITY_ATTRIBUTE`/
`run_config.INFORMATIONAL_ATTRIBUTES`, which each `strategy_DomGICS_*.py` copies into its own
`PARAMS` the same way it does `DOMINANCE_THRESHOLD_DECILE` etc. No edit to `shared/dominance.py` is needed
to retarget any role to a different indicator — **but** swapping `dominance_attribute` or
`priority_attribute` must be paired with its matching direction flag
(`dominance_attribute_direction` / `priority_attribute_direction`, bool): `True` = smaller value
wins (e.g. rank), `False` = bigger value wins. Get the direction wrong and the "dominating"/
ticker-selection choice silently inverts — there is no way to detect the mismatch from the data
alone. `informational_attributes` has no direction flag — display only, direction is irrelevant.

**Per-strategy `dominance_attribute` override (`DOMINANCE_ATTRIBUTE_OVERRIDES`)**: the three
strategies (`DomGICS_now`/`_20d`/`_50d`) normally all share the one global
`DOMINANCE_ATTRIBUTE`/`DOMINANCE_ATTRIBUTE_DIRECTION` pair, but per-attribute testing showed the
"now" (no persistence) and persistence tiers (`_20d`/`_50d`) don't always agree on which attribute
helps — e.g. `rsi` improved `DomGICS_now` on *both* `chain_annual` (119→184) and `Worst`
(−52→−32) at once, while the persistence tiers did better staying on `rank`. Rather than force one
global value, `run_config.DOMINANCE_ATTRIBUTE_OVERRIDES` (`dict[STRATEGY_NAME, (attribute,
direction)]`) lets one strategy diverge; each `strategy_DomGICS_*.py` resolves its own pair via
`cfg.dominance_attribute_for(STRATEGY_NAME)` instead of reading `cfg.DOMINANCE_ATTRIBUTE` directly
— a strategy absent from the dict falls through to the shared global default. Like the global pair,
`DOMINANCE_ATTRIBUTE` is still never swept by `sweep_config.py` — one attribute per strategy, tried
as an independent run, results compared and noted outside the system.

`make_dom_strategy(strategy_name, params, dom_col)` (in `shared/dominance.py`) is the
`make_strategy()` analog: it returns the same `(main, build_extension)` pair, so each strategy
file is still a short declaration:

```python
from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomGICS_now"
_dom_attr, _dom_dir = cfg.dominance_attribute_for(STRATEGY_NAME)
PARAMS = {
    "focusset_size": cfg.FOCUSSET_SIZE, "step": cfg.STEP, "period": 20,
    "No_go_GSPC_rsi": cfg.NO_GO_GSPC_RSI, "from_rank": cfg.FROM_RANK,
    "dominance_threshold_decile": cfg.DOMINANCE_THRESHOLD_DECILE, "dom_count_threshold": cfg.DOM_COUNT_THRESHOLD,
    "persistence_frac": cfg.PERSISTENCE_FRAC, "tickers_per_gics": cfg.TICKERS_PER_GICS,
    "dominance_attribute": _dom_attr,
    "dominance_attribute_direction": _dom_dir,
    "priority_attribute": cfg.PRIORITY_ATTRIBUTE,
    "priority_attribute_direction": cfg.PRIORITY_ATTRIBUTE_DIRECTION,
    "informational_attributes": cfg.INFORMATIONAL_ATTRIBUTES,
}
main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_now")
```

**`run_config.py`** is the single place to see and change every default each `strategy_DomGICS_*.py`
copies into its own `PARAMS` — the "classic" backtest knobs (`FOCUSSET_SIZE`, `STEP`,
`NO_GO_GSPC_RSI`, `FROM_RANK`), the Step-1 dominance knobs (`DOMINANCE_ATTRIBUTE`,
`DOMINANCE_ATTRIBUTE_DIRECTION`, `DOMINANCE_THRESHOLD_DECILE`, `DOM_COUNT_THRESHOLD`,
`PERSISTENCE_FRAC`, `DOMINANCE_ATTRIBUTE_OVERRIDES`), the Step-2 test-set knobs
(`PRIORITY_ATTRIBUTE_DICTIONARY`, `PRIORITY_ATTRIBUTE`/`PRIORITY_ATTRIBUTE_DIRECTION` — the
resting default, derived from the dictionary's first entry — and `TICKERS_PER_GICS`), and the
Step-3 display knob (`INFORMATIONAL_ATTRIBUTES`) — kept separate from `sweep_config.py`, which
decides *what runs* (which strategies, which grid of overrides for a sweep), not these defaults.

**Data-format gotcha:** Longi columns are newest-left (highest daynum first); "N days backwards"
means *older* daynums (smaller integers), the opposite of the column reading direction.
`add_persistence` re-sorts ascending by daynum before using pandas' trailing `.rolling()` window,
then restores the original newest-left column order — see its docstring if extending this pipeline.

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
  **Ladder investment** table, row-aligned via `_CHAINED_KEYS` + `_CHAIN_TO_LADDER`.
- `StartDaynum`/`EndDaynum` rows show each strategy's **usable span** (chronological; differ by
  strategy). `N_hops`/`N_hops_active` are not shown (redundant with `chain_n`/`ladder_n`).
- `chain_inv%` (left) / `ladder_inv%` (right) are a paired row: the share of the active span each
  estimator was actually invested.
- `origin_sens%` is a **chain-only** row (absent from the ladder table — the ladder diversifies
  the sensitivity away by construction).
- Adding a strategy to the sweep makes it appear automatically as a new column.

---

## Known Data Quirks

- **Series starts at daynum 1543** — PotDat/future_gain/Longi all begin there; nothing earlier.
- **Cal.csv index is float**: `2055,00` → `2055.0`. Look up with `float(daynum)`.
- **future_gain{period}d valid from ~newest-period**: the most recent ~`period` columns are NaN
  (not yet realised). `find_start_daynum()` skips them.
- **Stamdata.csv first column header** is a timestamp string, not a meaningful label.
- **`Longi/longi_grp_*.csv`** (sector-row aggregates, never per-ticker features) were deleted
  2026-07-29; a copy may survive in `repositoryRTBI/` until the next longi upload sync.

---

## Excel Styling Conventions

| Fill | Hex | Used for |
|------|-----|----------|
| Blue | `BDD7EE` | normal headers |
| Grey-blue | `D6DCE4` | strategy column header (best_strategy) |
| Yellow | `FFFF99` | parameter headers: `focusset_size`, `step`, `period`, `No_go_GSPC_rsi`, plus any strategy-specific threshold |
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
- The chain ranking lives once in `best_strategy.select_best_runs()`; `extension.py` reuses it for
  the ranking order and each strategy's winning-run params.
