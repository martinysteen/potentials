
# Strategy_grp Backtesting — Context for Claude Code

## Purpose

Framework for backtesting **named stock-selection strategies** against historical Potentials data.
Each strategy defines a *focusset selector* (picks N tickers for a given trading day) and the
framework measures how those picks performed over a single forward horizon — the **`period`**
parameter, in trading days. It must be one of the `longi_future_per*` "seven-pack" ladder
(1 / 5 / 10 / **20** / 50 / 100 / 200); `run_config.PERIOD` holds the default, 20.

A hop at daynum `d` **enters at `d+1`**, not at `d` — the signal day's close is what the pick is
made on, so it is not tradeable. See longi's `longi_future_performance.py`.

Output is Excel reports — not new data files — stored under `app/report/`.

**This project began as a standalone sibling of `../_archive/strategy/`** (archived 2026-07-31 —
frozen, no further work). It shares the same generic backtest engine and reporting machinery
(copied in verbatim at the time — see below), and reads the same underlying data in
`../repositoryRTBI/`, but defines and tests its **own** named strategies, selected by principles
distinct from `strategy`'s. **No strategy, config entry, or report from `strategy` was ever
reused as data here** — `strategy`'s strategies (Ranknow, Cross1020/2050, Tally_Rank/RSI/2050) and
its report history only ever served as a *structural template* for how this pipeline is shaped, and
have been stripped back out. This project's own named strategies, once defined, are tested one by
one via the sweep, with results assembled into this project's own `best_strategy.xlsx` —
independent of `strategy`'s roster and history.

**Current status: two group-domination families, one pipeline** — `DomGICS_now/_20d/_50d` and
`DomSector2_now/_20d/_50d`, all six registered in `sweep_config.py` and competing as six columns
in one `best_strategy.xlsx`. They differ in exactly one parameter, `group_column` (the Stamdata
column tickers are bucketed by): GICS's 13 sectors or Sector2's 50. See "Group Domination
Strategy Family" below for the selection logic and `shared/dominance.py` for the implementation.
Add further strategies (filter-based or otherwise) the same way: drop a file in `strategies/`,
register it in `sweep_config.py`, and it shows up everywhere automatically.

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
    │   │   ├── datacheck.py              # INPUT GUARD: preflight + snapshot (see "Input Data Guard")
    │   │   └── dominance.py              # group-domination pipeline for both Dom* families (below)
    │   ├── preflight.py                  # WHICH files a run needs + ensure_data() — the guard's front door
    │   ├── run_config.py                 # tunables for both Dom* families + dom_params() — the one
    │   │                                 #   copy of the shared 15-key PARAMS dict
    │   └── strategies/
    │       ├── strategy_DomGICS_now.py      # dominating GICS THIS daynum
    │       ├── strategy_DomGICS_20d.py      # + persistence over trailing 20 daynums
    │       ├── strategy_DomGICS_50d.py      # + persistence over trailing 50 daynums
    │       ├── strategy_DomSector2_now.py   # the same three tiers on Sector2's 50 groups —
    │       ├── strategy_DomSector2_20d.py   #   group_column is the ONLY intended difference
    │       └── strategy_DomSector2_50d.py   #   (dom_count_threshold follows from it)
    ├── data/
    │   └── input/                        # the frozen input SNAPSHOT a run reads (rebuilt per
    │                                     #   run, gitignored) + snapshot.json (its vintage)
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

# Input guard — every entry point preflights and snapshots first (see "Input Data Guard"):
python preflight.py                        # is the repository usable right now? run nothing
python run_sweep.py --stale-ok             # mid-update: run on the previous snapshot, loudly
python run_sweep.py --live                 # read the live repository unguarded

# Standalone pieces (run_sweep already calls these at the end):
python aggregate_summary.py ["Strategy"]   # re-aggregate one or all strategies
python extension.py                         # build the combined best_strategy_<date>.xlsx
python best_strategy.py                     # same combined file (delegates to extension.run())

# Out-of-sample check (read-only; touches none of the files above):
python walkforward.py                       # walk-forward score of the sweep_config grid
python walkforward.py --wide                # add numeric axes for a real selection test
python walkforward.py --dry-run             # fold layout + grid size only
```

To analyse a different horizon: set `run_config.PERIOD` (or override `period` in
`sweep_config.py` / a strategy's PARAMS) to another member of `shared.config.FUTURE_PERIODS` —
the "seven-pack" (1/5/10/20/50/100/200 trading days) — then re-run. Everything stays
one-horizon-at-a-time; the report is identical in shape. Mixing horizons in one comparison is
rejected by best_strategy.py.

**Re-sweep after changing it.** `aggregated_summary.xlsx` retains runs at the old horizon, and
`extension.py`/`best_strategy.py` read `period` back out of those rows — so the daily tool will
pick up a stale horizon until `run_sweep.py` archives them aside.

Note the longer horizons buy fewer independent lots: over the ~660-daynum history, 20 days gives
~33 non-overlapping lots, 50 gives ~13, 100 gives ~7 (borderline above `MIN_CHAIN_LOTS`), and
200 gives ~3 — below `MIN_CHAIN_LOTS`. The 100d and 200d files exist for completeness; 200d in
particular will not sustain a backtest.

---

## Input Data Guard — preflight + snapshot

**The input repository is a moving target, and the failure it caused was invisible.** Three
unsynchronised cron jobs rewrite `repositoryRTBI/data/` all day:

| when | what | effect |
|---|---|---|
| `:07` / `:37` | `repositoryRTBI/sync_rtbi.sh` | `rclone sync` from Google Drive — a *sync*, so it **deletes** a local file the moment the Drive side is itself mid-regeneration |
| `:15` | `longi/start_longi.sh` | rebuilds the `longi_*` family |
| `:30` | `group_conformity/run_conf.sh` | rebuilds the `longi_conf_*` / `longi_sectorbeta_*` family |

A run now needs files from **both** families (`INFORMATIONAL_ATTRIBUTES` includes `conf_GICS` and
`conf_Sector2`), and between `:15` and `:30` they are never the same generation. Seen live on
2026-07-30: the `:30` conformity job took 7m50s to upload 89 MB, the `:37` sync landed mid-upload
and pulled `longi_conf_Sector2.csv` only — so `longi_conf_GICS.csv` was **deleted** locally (a sync
mirrors deletions) and preflight failed correctly until the job's own trailing sync restored it at
`:41`. Transient, and exactly what the guard is for. Two bad states
follow, and **the second is the dangerous one**:

* **A file is gone.** pandas raised deep inside a strategy, `run_sweep.run_strategy`'s blanket
  `except Exception` printed it as one line in a wall of sweep output, and the run vanished.
* **A complete set from TWO generations.** `longi_rank.csv` already at today's newest daynum
  while `longi_conf_GICS.csv` still ends a day earlier. **Nothing raises on this** — every
  consumer treats "this daynum is not a column" as a legitimate no-pick
  (`dominance.select_focusset` returns `[]`, the writers write blanks). The run sailed through
  the entire sweep producing empty focussets and only detonated in the **extension** step,
  with a traceback pointing nowhere near the cause. A louder loader would not have caught it:
  nothing was missing at any single moment — the *assortment* was incoherent.

### What runs now

`preflight.ensure_data()` is the **first** call in every entry point, before anything opens a
CSV (`run_sweep.main`, `extension.run`, `walkforward.main`, and each strategy's `main()` via
`make_dom_strategy` — idempotent, so a sweep preflights once, not per run). It:

1. **Checks** every file the configured strategies could read: present, non-empty, parseable,
   not written within `MIN_AGE_SECONDS` (45s — may still be mid-write), and — for the daynum
   matrices — **all agreeing on the same newest daynum**. That last rule is the one that
   catches the silent case, and it is a hard failure. Row counts are also compared against the
   previous snapshot; a >2% drop warns about a truncated write.
2. **Freezes** the checked set into `app/data/input/` and points `shared/config`'s active root
   there, so everything the run opens afterwards is one coherent generation, immune to a sync
   landing mid-run. `snapshot.json` records the vintage.

On failure it raises `DataUnavailable` **after printing a one-screen table** of every file with
its daynum, rows, size, age and status — the diagnosis that did not exist before. Since this is
usually transient, the message says so and names the two escape hatches.

```bash
python preflight.py                # print the table for the live repository; run nothing
python preflight.py --manifest     # just list the files a run requires
python run_sweep.py --stale-ok     # live data is mid-update: run on the previous snapshot
                                   #   (loud banner; the output is NOT current)
python run_sweep.py --live         # read the live repository unguarded (old behaviour)
```

### Division of labour (do not merge these two)
* `shared/datacheck.py` — **generic** mechanics: inspect, evaluate, snapshot, print. Knows
  nothing about DomGICS or any strategy; takes the file list as an argument, which was
  designed to make it copyable verbatim to `../strategy/` — moot now that project is archived
  (see "Not yet done" below).
* `preflight.py` — **project-specific**: assembles that list from `run_config`, `sweep_config`
  and the strategy modules (every `PRIORITY_ATTRIBUTE_DICTIONARY` entry, every
  `DOMINANCE_ATTRIBUTE_OVERRIDES` entry, every informational attribute, each strategy's
  horizon, any filter-chain CSV). Deliberately a **superset** of what one entry point touches
  — a superset only makes the guard stricter, and per-entry-point lists are exactly the kind
  of drift that lets a file go unchecked until it is missing.

### Consequences elsewhere
* `shared/config.py` exposes `active_root()`/`active_longi()`/… **functions**, not constants.
  `from shared.config import DATA_LONGI` binds a value at import and could never be
  redirected — which is why the indirection exists. `DATA_ROOT` still names the **live**
  repository; `use_data_root()` switches the active one and clears the loader caches.
* `shared/data_loader.py` raises `DataUnavailable` naming the file, the root, and the
  preflight command — never a bare pandas traceback. `DataUnavailable` subclasses
  `FileNotFoundError` **on purpose**, so the two places that treat a Longi file as genuinely
  optional (`report.py`/`extension.py`'s `_beta_frame`, catching `(FileNotFoundError, OSError)`)
  keep degrading silently as designed.
* `run_sweep.run_strategy` **re-raises** `DataUnavailable` instead of swallowing it. That
  except-block exists to survive one bad *parameter-set*; a vanished input file is not that —
  every remaining run would fail identically, and burying it is how this stayed invisible.
* `dominance.main()` warns when >90% of hops picked nothing — the second net behind preflight,
  since that is the exact signature of an input problem that no longer raises.
* Copies, not hardlinks: hardlinking is free but only isolates the run if rclone always writes
  a new inode and renames; `--inplace` would rewrite the bytes underneath. The required set is
  ~45 MB, so a copy costs under a second and needs no assumption about rclone.

### Not yet done — now moot
`../_archive/strategy/` shared the same verbatim `shared/` modules and read the same repository,
so it had identical exposure and none of this guard. Mirroring would have been a copy of
`datacheck.py` + `preflight.py` + the `config.py`/`data_loader.py` edits, with
`preflight.required_files()` rewritten for its filter-chain strategies — but `strategy/` was
archived 2026-07-31 with no further work planned, so this is no longer worth doing.

---

## Data Sources

All input is read from `DATA_ROOT = /home/sm/potentials/repositoryRTBI/data/` (defined in
`shared/config.py`) — the same data source the now-archived `../_archive/strategy/` used to
read. Never hardcode paths.
**A run reads a frozen snapshot of it, not the live directory** — see "Input Data Guard" above.

### Matrix format (all Longi files)
- **Rows:** ticker symbols (index column, no header label)
- **Columns:** daynum integers as **strings** — newest left, oldest right
- **CSV:** European — semicolon separator `;`, comma decimal `,`
- Load with: `pd.read_csv(path, sep=';', decimal=',', index_col=0)`
- Column lookup: always `df[str(daynum)]` — never bare int

### Key files

| File | Content |
|------|---------|
| `Longi/longi_future_per20d.csv` | Realised forward gain over a 20-trading-day hold (%) — `period=20`, the primary horizon |
| `Longi/longi_future_per{1d,5d,10d,50d,100d,200d}.csv` | The rest of the "seven-pack" forward ladder: 1/5/10/50/100/200 days. Available, none currently used |
| `Longi/longi_rank.csv` | Average rank across all performance periods (1 = best) |
| `Longi/longi_rsi.csv` | RSI14 (Wilder's method) |
| `Longi/longi_ma*.csv` | Simple moving averages |
| `Longi/longi_beta3m.csv`, `longi_median_30d.csv`, `longi_vola100d.csv` | Beta / momentum / volatility factors |
| `data/PotDat.csv` | Raw stock prices (incl. `^VIX`) |
| `data/Stamdata.csv` | Ticker metadata: Name, Sector, GICS, Sector2, Zone, … |
| `data/Cal.csv` | daynum → date (index is float, e.g. 2055.0 — use `float(daynum)`) |

Full factor set (all in `Longi/`, see `../repositoryRTBI/data/Longi/`): trailing returns
(`longi_per1d/5d/10d/20d/50d/100d/200d`, the "seven-pack"), moving averages & ratios (`longi_ma10/20/50/200`,
`longi_PdivMA*`), momentum (`longi_macd_*`), beta (`longi_beta3m/6m/1yr`), volatility/spread
(`longi_vola20d/100d`, `longi_spr100d/250d`), medians (`longi_median_10..100d`), MA-cross
quotients (`longi_quot1020`, `longi_quot2050`), composite rank (`longi_rank`), plus normalized
prices (`PotNdx.csv`), a rich ranking snapshot (`PotRank.csv`), and historical fundamentals
(`Yfinance/StockData2_stacked.csv` — P/E, margins, growth, analyst targets) not yet tapped by
any strategy here.

**Do not use** `Longi/longi_grp_*.csv` as per-ticker features — they are sector-row aggregates
(rows are sector names, not tickers, so an inner join on ticker yields nothing). The current
families are `longi_grp_GICS_per{1d,1w,1m,3m,6m,1y}.csv` (13 rows) and
`longi_grp_Sector2_per*.csv` (50 rows), added 2026-07-29: the mean of each sector's tickers, same
shape as the matching `longi_per*.csv`. **Not** what the `DomSector2_*` family uses — that groups
by the `Sector2` column of `Stamdata.csv` and aggregates per-ticker factors itself. These files are
still untapped; their natural use is the **market rotation rate** the turnover diagnostics want to
be compared against (see "Turnover" in the family section).

---

## Shared Modules

(`config.py`/`data_loader.py`/`select.py`/`engine.py`/`chain.py`/`report.py`/`extension.py` were
copied verbatim from `../_archive/strategy/shared/` at the time. `strategy/` was archived
2026-07-31 with no further work planned, so there is no longer a second copy to keep in sync.
`dominance.py` is new to this project — see below.)

### `shared/config.py`
Constants: `DATA_ROOT`, `DATA_LONGI`, `POTDAT_PATH`, `STAMDATA_PATH`, `CAL_PATH`, `APP_ROOT`, `REPORT_ROOT`, `SUMMARY_CSV`.

Also `FUTURE_PERIODS` + **`future_gain_file(period)`** — the one place a `period` becomes a
forward-gain filename. Since the 2026-07-31 "seven-pack" rename, the label is always literally
`f"{period}d"`, so this is a validated lookup, not a translation table. **`period` stays an INT
everywhere**, deliberately: it is not merely a filename infix but also the hold length
`chain.py` spaces lots by, the amount `walkforward` embargoes the training window by, and the
size of the extension's still-open window. Only the
filename is looked up, so none of that arithmetic had to change when the files were renamed.
`future_gain_file` **raises** on a period outside the ladder rather than defaulting — a wrong
horizon file does not crash anything downstream, it produces a complete and entirely plausible
report measured against the wrong future. (It fired for real during the 2026-07-31 cutover, on
archived `period=20` runs still sitting in `aggregated_summary.xlsx`; the fix is a re-sweep,
which archives the old horizon out.)

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
is read from `params["period"]` (loads the matching `longi_future_per*.csv`, so the window is ~`period`
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
because the realized `longi_future_per*` matrix by definition does not exist yet for these entries — that is the
whole reason the extension exists. In a flat tape these rows mostly restate `avg_partial_gain`;
they earn their place in an index selloff, where an open position's loss belongs to the market
rather than to the picks. Row offsets advance through `next_row`, so inserting the block could
not desync the informational/ref rows the way it did on the main sheet.

### `shared/dominance.py` — group-domination pipeline (new, not from `../_archive/strategy/`)
The preprocessing stage behind both Dom* families — see "Group Domination Strategy Family" below
for the full write-up. `make_dom_strategy(strategy_name, params, dom_col)` is this module's
`make_strategy()` analog: it returns the same `(main, build_extension)` pair, so a Dom* strategy
file is still a short declaration, just built on this pipeline instead of the filter chain. Also
holds `turnover_stats` (the flicker diagnostics).

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
    "dom_cutoff":      float,             # OPTIONAL — Dom* families only: that daynum's Step-1
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
| 3 *(optional)* | `dominance_cutoff` per hop — only when hops carry `"dom_cutoff"` (Dom* families); label (A) bold, data cells plain text | Pale green |
| next N rows | Ticker names, rank 1→N | — |
| *(optional)* | `N_survivors` per hop — only when hops carry `"n_survivors"` | Pale blue |
| next | `avg_gain` (single row; top-N avg over `period`) | Green/red/grey |
| next 2 | `mkt_gain` (benchmark for that daynum) and `alpha` (`avg_gain − mkt_gain`) | Green/red/grey |
| *(optional)* | `beta` — mean `beta3m` of the focusset; only when `longi_beta3m.csv` loads | Pale grey |
| next 2 per informational attribute | `<attr>_mean` / `<attr>_median` | — |
| next 4 | `^GSPC_rsi`, `^STOXX_rsi`, `^HSI_rsi`, `^VIX` | Yellow |
| … | GICS / Sector2 / Zone occurrence counts — **both** breakdowns are written for every strategy regardless of `group_column`, which is what lets a Sector2 run be read against its GICS twin | Purple / peach / teal |

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
| `dominance_cutoff_avg` | Dom* families only — run-average of the per-daynum Step-1 dominance cutoff; inserted right after `dominance_attribute_direction` here and in `aggregated_summary.xlsx`; shown in `best_strategy.py`'s comparison sheet as the row directly below `dom_count_threshold` |
| `avg_gain` | grand average per-hop top-N gain over `period` (No_go-filtered) |
| `avg_alpha` | same hops, measured against the benchmark instead of against zero — **active return, not Jensen's alpha** (see below) |
| `avg_beta` | mean `beta3m` of the picks; omitted when `longi_beta3m.csv` is absent. Not a performance metric — the number you discount `avg_alpha` by |
| `chain_ret`, `chain_annual`, `chain_n` | realizable chain (additive, phase-averaged; see below) |
| `origin_sens%` | spread of `chain_annual` across start origins `(max−min)/avg %` — **lower = more robust** to when you start hopping (diagnostic; never ranks) |
| `N_loss` | most negative lots in any one origin's realized chain (of `chain_n`) — worst-case count |
| `Worst` | worst single chain lot (gain%): the lowest lot over all start origins |
| `pick_turnover`, `group_turnover` | Dom_* only — flicker diagnostics passed in via `save_report(extra_summary=…)`; see "Turnover" under the family section. **Never rank on them** |

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
  `dominance_threshold_decile=0.05, tickers_per_group=2` config scored 445 on one lot — and
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
logic. Covers the `Dom*` families only (both of them — the gate is the presence of
`main.dom_col`, which `make_dom_strategy` tags) — it rebuilds picks through the dominance pipeline
itself, so it can re-score a window without re-running a report.

**`group_column` is in `_PICK_KEYS` and in `_dom_table`'s cache key, and must stay there.**
`DomGICS_now` and `DomSector2_now` are identical in every other parameter, so without it they
collide in `_series_cache` and the second family silently scores the first family's picks — a
result that looks entirely plausible in the report. `_dom_table`'s key is splatted into
`dominance_tables(*key)`, so its **order** must match that signature (group_column last).

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
    "period": 20,             # forward horizon in trading days; a member of the
                              # "seven-pack" shared.config.FUTURE_PERIODS (1/5/10/20/50/100/200)
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
- One `gains` dict per hop, for the `period` horizon file — never both horizons.
- Selection returns `[]` when a daynum/column is absent; never raises; `str(daynum)` for all lookups.
- Empty-focusset policy: filter strategies **skip** (record a cash hop and `continue`) by default.
- `n_survivors` is recorded (→ `N_survivors` report row) automatically when a strategy has **≥2
  filters**.
- `quotient_filter` builds the ad-hoc ratio (e.g. MA10/MA20) at runtime, used like a preformed matrix.

---

## Group Domination Strategy Family (GICS / Sector2)

`DomGICS_now`/`_20d`/`_50d` and `DomSector2_now`/`_20d`/`_50d` are **not** filter-chain
declarations — `shared/engine.py`'s per-ticker filters have no group-by-sector aggregation or
trailing-window primitive, so these families are built on a separate pipeline,
`shared/dominance.py`. It still produces the exact same `hop_results` shape (see below), so
reporting/aggregation/comparison all work unmodified.

### `group_column` — a FOURTH role, deliberately not called an "attribute"

The two families run the **same pipeline** and differ in one parameter: `group_column`, the name of
a **`Stamdata.csv` column** whose values tickers are bucketed by before Step 1 counts anything.
The three *attribute* roles below are all Longi factor short names (`longi_<name>.csv`) — a
different kind of thing entirely, and this project has already been broken once by conflating
roles, so the grouping knob is pointedly not a fourth "attribute".

| `group_column` | values | avg tickers/group | `dom_count_threshold` |
|---|---|---|---|
| `"GICS"` | 13 | ~93 (Indu 225 … Index 14) | 10 |
| `"Sector2"` | 50 | ~24 (75 … 2) | **5** |

**`dom_count_threshold` is per group criterion and cannot be shared.** It is an absolute count of
qualifying tickers, and the market-wide best decile is only ~120 of ~1200 tickers: "10 qualifying"
asks a 93-member GICS for 11% of itself but a 24-member Sector2 for 42% — at 10 the Sector2 family
produces almost nothing but cash hops. `run_config.DOM_COUNT_THRESHOLD` holds the pair and derives
Sector2's as half of GICS's so the two cannot drift apart. `run_config.dom_count_threshold_for()`
raises on an unknown column rather than defaulting.

`group_column` is **never swept** — it defines the family, and sweeping it would put two group
criteria in one report directory. It is in `sweep_config.NON_SWEEPABLE`, which `build_plan()` hard-
fails on, and it is deliberately absent from `extension._INT_PARAMS`/`_FLOAT_PARAMS` so
`_params_from_row` leaves the module's own value alone (reading it back from an aggregated row is
how a Sector2 strategy would get rebuilt on GICS). To test another grouping, add a strategy.

**Sector2 is a sub-partition of GICS, not a rival taxonomy.** 48 of its 50 values sit inside
exactly one GICS, so the family is a *sharpening of which groups get promoted*. The sharpening is
very uneven — Indu splits 10 ways, C-Di 8, Fina 7, Tech 6, while **Tele and Index have a single
child each and cannot be sharpened at all** — so read any Sector2-vs-GICS difference against that.
Two values leak across a GICS boundary by one or two tickers and look like upstream
misclassifications: `Holiday` (C-Di 18 / C-St 1) and `Other[Indu]` (Indu 33 / Tech 2).

**First measured verdict (2026-07-30) — the sharpening does not pay, on current evidence.** The
family works and is a legitimate alternative, but nothing yet says it is better:

* **In-sample `chain_annual`** (the primary decision metric, full history): GICS wins at every
  tier — 68.2 / 74.0 / 60.5 against 60.5 / 60.7 / 57.0.
* **The clean causal test** — take the hops where the two families disagree (113 of 128) with
  `dominance_attribute` held constant, and compare the realized 20d gain of the picks Sector2
  *adds* against the ones it *drops*: **−3.67 pp on `rank`**, −0.35 pp on `rsi`. It drops better
  tickers than it adds. Focusset overlap is 0.67 mean, so the divergence is real, not marginal.
* **Out-of-sample** (`walkforward.py`, 5 folds) is mixed and noise-dominated: `DomSector2_now`
  edges `DomGICS_now` on `oos_avg_gain` (7.61 vs 6.41) while `DomGICS_50d` edges
  `DomSector2_50d` (7.66 vs 6.86). With ~13 independent lots this settles nothing; `grid=1` also
  makes `selection_skill` identically 0, so those runs measure OOS level, not selection.
* Over the full history Sector2 elevates **8.0** groups per daynum against GICS's **4.2** (pools
  of ~24 vs ~13 candidates) — the "6 vs 5" seen on one day was not typical.
* `tickers_per_group=3` binds everywhere: the smallest group that ever dominates has 10 members,
  so the small-sector worry is empirically a non-issue. 11 of 50 never dominate, including
  `Other[C-Di]` (2 members) and `Other[C-St]` (5), which cannot reach the threshold of 5 at all.

The diagnostic that produced the middle two bullets is `~/tmp/sector2_diag.py` (outside the repo,
read-only, takes the dominance attribute as an argument). **Hold `dominance_attribute` constant when
comparing families** — only `DomGICS_now` carries the `rsi` override, and taking each strategy's own
pair measures `rsi` vs `rank` as much as the grouping.

**Three distinct attribute roles — three different names. This distinction has been a recurring
source of confusion (a prior stranded rename broke the sweep entirely); it is now load-bearing
naming, not just documentation:**

**Selection logic, per daynum:**
1. **Step 1 — group elevation, "dominance" (`group_dominance_now`)**: count tickers per
   `group_column` value (from `Stamdata.csv`) that "beat" **that day's own best-decile cutoff** of
   `longi_{dominance_attribute}.csv` — below the cutoff when `dominance_attribute_direction`
   (smaller wins, e.g. rank, the default), above it otherwise (bigger wins). `dominance_threshold_decile`
   (default `0.10`) is a **fraction, not a raw value**: `shared.dominance._daily_decile_cutoff`
   computes the value at that quantile of the attribute's *cross-sectional distribution on that one
   daynum* (every ticker, that day only — computed independently day by day, not across history),
   so the same fraction means "best 10%" for any attribute regardless of its raw scale (rank
   1..~1200, rsi 0..100, beta3m usually <5, ...), on every individual day. A group with
   `>= dom_count_threshold` (10 for GICS, 5 for Sector2 — see the table above; the count is
   absolute and does **not** transfer between criteria) such tickers is "dominating" **that
   daynum** — `dom_now`.
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
   the current one). The `_now`/`_20d`/`_50d` tiers of each family key off one of
   `dom_now`/`dom_20d`/`dom_50d`. This is the **flicker-damping** axis — see "Turnover" below.
   **Naming note (not a code collision, just a reading trap):** since the 2026-07-31
   "seven-pack" rename, `20d`/`50d` are ALSO literal Longi filename suffixes
   (`longi_future_per20d.csv`, `longi_per50d.csv`, …) meaning the **forward-horizon length in
   `period`** — a completely different axis from this persistence window. `DomGICS_20d`'s `20d`
   is a trailing-daynum count for Step 1; `period=20` is the hold length for the whole backtest.
   The two happen to share a number by design (both read as "20 trading days"), but nothing in
   code conflates them — read `strategy_Dom*.py`'s `STRATEGY_NAME` suffix and `PARAMS["period"]`
   as answering two unrelated questions.
3. **Step 2 — test-set construction, ticker selection (`select_focusset`)**: each dominating group
   contributes its `tickers_per_group` (default 3, shared by both criteria) **best** tickers by
   `longi_{priority_attribute}.csv` (direction-aware: smaller wins when
   `priority_attribute_direction`, bigger otherwise) — or its **worst** `tickers_per_group` when
   `from_rank=-1`, so a bottom-pick draws from genuinely weak tickers rather than the weakest of
   an already-best-biased pool. The pooled candidates across all dominating groups are then
   re-ranked **globally** by that same value and `focusset_size`/`from_rank` applied via
   `shared.select.pick_by_rank` (`from_rank`: `1`=best n, `-1`=worst n) — same "smaller is better"
   convention `rank_by(..., ascending=False)` uses (negate a bigger-wins series before ranking).
   Unlike Step 1, it's genuinely unclear which attribute makes the best selection criterion, so
   `run_config.PRIORITY_ATTRIBUTE_DICTIONARY` (`dict[attribute, direction]`) enumerates every
   candidate worth testing; `sweep_config.py` sweeps across **all** of them, one independent
   test-set (run) per entry, deriving each run's direction from the dictionary so a name can never
   be paired with the wrong direction (see `sweep_config.py`'s "Sweeping priority_attribute").
4. **Step 3 — informational only (display)**: `informational_attributes` never affects dominance,
   test-set construction, or selection — it only adds `<attr>_mean`/`<attr>_median` rows to
   `run*.xlsx`/extension sheets for insight into what's going on along the timeline. May be a
   single Longi factor short name or a list. **Keyed by `group_column`** in
   `run_config.INFORMATIONAL_ATTRIBUTES`, so each family displays its own conformity factor
   (`conf_GICS` vs `conf_Sector2`) rather than the other one's; `informational_attributes_for()`
   resolves it. `preflight.required_files()` unions **all** criteria's lists, so both conformity
   files are always guarded whichever families are configured.

**`dominance_attribute`/`priority_attribute`/`informational_attributes`** are Longi factor **short
names** (the `longi_<name>.csv` part only, e.g. `"rank"`, `"per1d"`, `"rsi"`, `"beta3m"`) — set
them via `run_config.DOMINANCE_ATTRIBUTE`/`run_config.PRIORITY_ATTRIBUTE`/
`run_config.INFORMATIONAL_ATTRIBUTES`, which `run_config.dom_params()` copies into each strategy's
`PARAMS` the same way it does `DOMINANCE_THRESHOLD_DECILE` etc. No edit to `shared/dominance.py` is needed
to retarget any role to a different indicator — **but** swapping `dominance_attribute` or
`priority_attribute` must be paired with its matching direction flag
(`dominance_attribute_direction` / `priority_attribute_direction`, bool): `True` = smaller value
wins (e.g. rank), `False` = bigger value wins. Get the direction wrong and the "dominating"/
ticker-selection choice silently inverts — there is no way to detect the mismatch from the data
alone. `informational_attributes` has no direction flag — display only, direction is irrelevant.

A `priority_attribute` name is swept for **every** strategy, so a group-specific factor there
(`conf_GICS`) would have the Sector2 family ranking candidates on GICS conformity — silent
cross-wiring with nothing visibly wrong in the output. Test one family at a time via a `STRATEGIES`
override if a conformity factor is ever tried in that role.

**Per-strategy `dominance_attribute` override (`DOMINANCE_ATTRIBUTE_OVERRIDES`)**: the
strategies of a family normally all share the one global
`DOMINANCE_ATTRIBUTE`/`DOMINANCE_ATTRIBUTE_DIRECTION` pair, but per-attribute testing showed the
"now" (no persistence) and persistence tiers (`_20d`/`_50d`) don't always agree on which attribute
helps — e.g. `rsi` improved `DomGICS_now` on *both* `chain_annual` (119→184) and `Worst`
(−52→−32) at once, while the persistence tiers did better staying on `rank`. Rather than force one
global value, `run_config.DOMINANCE_ATTRIBUTE_OVERRIDES` (`dict[STRATEGY_NAME, (attribute,
direction)]`) lets one strategy diverge; `cfg.dom_params()` resolves each strategy's pair via
`cfg.dominance_attribute_for(STRATEGY_NAME)` instead of reading `cfg.DOMINANCE_ATTRIBUTE` directly
— a strategy absent from the dict falls through to the shared global default. Like the global pair,
`DOMINANCE_ATTRIBUTE` is still never swept by `sweep_config.py` — one attribute per strategy, tried
as an independent run, results compared and noted outside the system.

**Careful when comparing the two families:** only `DomGICS_now` currently carries an override
(`rsi`), so a naive GICS-vs-Sector2 comparison at the `_now` tier measures `rsi` vs `rank` as much
as it measures the grouping. Hold `dominance_attribute` constant when the question is about the
group criterion itself.

`make_dom_strategy(strategy_name, params, dom_col)` (in `shared/dominance.py`) is the
`make_strategy()` analog: it returns the same `(main, build_extension)` pair, so each strategy
file is still a short declaration:

The 15-key `PARAMS` dict is built once, by `run_config.dom_params()`, so all six strategy files are
four lines of declaration. Six hand-written copies of one parameter list is how a rename ends up
half-applied — which has happened here:

```python
from shared.dominance import make_dom_strategy
import run_config as cfg

STRATEGY_NAME = "DomSector2_now"
GROUP_COLUMN  = "Sector2"        # the only intended difference from the GICS twin
PARAMS: dict = cfg.dom_params(STRATEGY_NAME, GROUP_COLUMN, period=20)
main, build_extension = make_dom_strategy(STRATEGY_NAME, PARAMS, "dom_now")
```

`dom_params()` returns a **fresh dict every call** — `run_sweep.run_strategy` mutates
`module.PARAMS` in place (`clear()` + `update()`), so two modules must never share one object.

**`run_config.py`** is the single place to see and change every default `dom_params()` copies into a
strategy's `PARAMS` — the "classic" backtest knobs (`FOCUSSET_SIZE`, `STEP`, `NO_GO_GSPC_RSI`,
`FROM_RANK`), the grouping knob (`GROUP_COLUMNS`, `DOM_COUNT_THRESHOLD` +
`dom_count_threshold_for()`), the Step-1 dominance knobs (`DOMINANCE_ATTRIBUTE`,
`DOMINANCE_ATTRIBUTE_DIRECTION`, `DOMINANCE_THRESHOLD_DECILE`,
`PERSISTENCE_FRAC`, `DOMINANCE_ATTRIBUTE_OVERRIDES`), the Step-2 test-set knobs
(`PRIORITY_ATTRIBUTE_DICTIONARY`, `PRIORITY_ATTRIBUTE`/`PRIORITY_ATTRIBUTE_DIRECTION` — the
resting default, derived from the dictionary's first entry — and `TICKERS_PER_GROUP`), and the
Step-3 display knob (`INFORMATIONAL_ATTRIBUTES` + `informational_attributes_for()`) — kept separate
from `sweep_config.py`, which decides *what runs* (which strategies, which grid of overrides for a
sweep), not these defaults.

### Turnover — the flicker diagnostics (`pick_turnover` / `group_turnover`)

`shared.dominance.turnover_stats` measures how much changes between consecutive hops: the Jaccard
distance of the focussets (`pick_turnover`) and of the dominating-group sets (`group_turnover`),
averaged over pairs where **both** hops are invested (cash gaps are the persistence gate doing its
job and are already reported by `chain_inv%`). They reach the Summary sheet, `summary.csv`,
`aggregated_summary.xlsx` and the comparison sheet via `save_report(..., extra_summary=...)`.

**Diagnostic only — never rank on them**, same status as `origin_sens%`. The chain takes
non-overlapping lots ≥ `period` apart, so every lot is a fresh purchase however much the picks
churned in between: turnover costs `chain_annual` exactly nothing and there is no transaction-cost
argument to make. What flicker actually costs is **followability** — a daily recommendation that
changes under the user — which is a reason to prefer a persistence tier, not a return penalty.
Both are measured per `step`, so they only compare across runs sharing `step`.

What the first six-strategy run showed (2026-07-30, `step=5`):

| | GICS now/20d/50d | Sector2 now/20d/50d |
|---|---|---|
| `group_turnover` | 0.35 / 0.09 / 0.03 | 0.61 / 0.25 / 0.12 |
| `pick_turnover` | 0.93 / 0.92 / 0.93 | 0.94 / 0.92 / 0.90 |

The finer grouping churns its **sector** set ~2–4× faster at every tier, and persistence damps it
as designed. But `pick_turnover` is pinned near 0.93 in all six: **the persistence tiers stabilize
which sectors are held, not which tickers.** Ticker-level churn is driven by the Step-2
`priority_attribute` re-rank, not by the grouping — so a stability complaint about the daily
recommendation is not addressable by changing `group_column` or the tier.

Still unanswered: whether that churn is *in fair agreement with the market's own* rotation rate.
The reference would be the tape's leadership churn — rank groups by trailing
`longi_grp_{GICS,Sector2}_per*.csv`, take the top *k* with *k* = the run's mean dominating count,
and measure how fast that set turns over; the ratio `group_turnover / market_group_turnover` reads
≈1 as fair agreement, ≫1 as chasing noise, ≪1 as lagging real rotation. Not built: it needs a
defended choice of window and *k*, plus half-split validation the way `group_conformity` was done.

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
  the sensitivity away by construction). `pick_turnover`/`group_turnover` are chain-only for a
  different reason: turnover is a property of the *picks*, identical for both estimators, so
  repeating it under "Overlap investment" would read as a second, independent measurement.
- `group_column` is a row, so which criterion produced a column is visible without decoding the
  strategy name.
- Adding a strategy to the sweep makes it appear automatically as a new column.

---

## Known Data Quirks

- **Series starts at daynum 1543** — PotDat/longi_future_per*/Longi all begin there; nothing earlier.
- **Cal.csv index is float**: `2055,00` → `2055.0`. Look up with `float(daynum)`.
- **`longi_future_per*` valid from ~newest-(period+1)**: the most recent ~`period`+1 columns are NaN
  (not yet realised). `find_start_daynum()` skips them.
- **Stamdata.csv first column header** is a timestamp string, not a meaningful label.
- **`Longi/longi_grp_*.csv`** are sector-row aggregates — never per-ticker features.

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
