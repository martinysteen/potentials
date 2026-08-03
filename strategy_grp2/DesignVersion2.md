# Design of Strategy\_grp2 processor

## Basic thinking

Strategy\_grp2 is version 2 of Strategy\_grp. In version 2 we are shall use a lot of the calculative machinery from Strategy\_grp yet not with several changes to be described here. So Stategy\_grp is to be used during development of Strategy\_grp2 remembering that Strategy\_grp will be retired when version 2 goes into full production.

### Core principles for version 2

* Processor runs are to be managed by a control board which holds a number of active (a tick) runs to be performed one by one and results collected in compare.xlsx (resembling best\_strategies.xlsx in ver 1)
* I control board all input parameters for all processer steps are specified. That means that strategies with any combination of parameters can be compared.
* Fundamental group definition (either GICS or Sector2) is a parameter like any other.  Any logical expression which is able to unambigous picking out a subset of tickers can be group criteria.  That means e.g. US-based GiCS can be investigated by either \[Stamdata.Homeland='US'] or if all homelands are to be compared just \[Stamdata.Homeland].  If GICS-categories separated on a not too long list of groups one could select \[Stamdata.Zone .and. Stamdata.GICS]  or restricted to Americal stocks it would be \[Stamdata.Zone='NY' .and. Stamdata.GICS].  We might start with only allowing logic expressions based on Stamdata data, but it could later on be extend to selecting any logic expression across repositoryRTBI's tables.  Note: Since group definition is so freely set we cannot expect Longi to hold all necessary tables and if Longi cannot provide some, it must be created ad hoc.
* The purpose of the processor will be two: Production run for daily advice which will be a "gross list strategic stocks".  That may e.g. hold the agressive, the gentle and the middle-road strategy's gross list of stocks (sorted according to priority). 10-20 tickers per strategy, I presume. Development run - later on quality assurance run - prolongs production runs' steps with backtest and forward-walk steps and sums up it all key figures, timeline (run\*\_date.xlsx combined with tabs from best\_strategy.xls) and hopefully some graphics (which has be regrettably absent in version 1). The number of strategies tested in development runs must be larger than the 3 in production runs so both purposes shall be marked in control board.
* In version 1 Excels sheets and various tables has created a confusing mix of input, processing and output measures.  I propose a separation of these:  All simulation parameters shall side by side be place in control board.  All process outputs - assurance and final ones - shall be clearly devided by process step and all go to output board (a separate file or separate tabs in a file shared with control board). 
* Both control board and the output board shall be in Excel - not py files (especially new regarding input) since this will allow a broad set of hugely varying strategies to be fired simultaneously.



### Proces steps

##### Step 0: Group definition and data procurement

Group definition drawn from control board plus other data demands from steps below are translated into table requirements (take all stocks if no group definition or say #ALL is given). Their availability in repositoryRTBI is tested and when unmet they are created locally. Assurence of this is given to control board or - if problems - process terminated and reasons given same place.

##### Step 1: Group dominance level A, B, and C

Using parameters from control board today-dominance (relabeled level A) as well as 20d-persistent dominance (now level B) and level C for the 50 day persistent dominance can be established using a process identical to the one in version 1.  The A, B and C level should assist in shorter naming of strategies and their results.

Pick number per group (typically 3 in version 1) for step 3 and 4 shall be individual to level. I guess level A will maintain 3, but B get 4 and C thus compensation for the dimishing number of ticker-promotions to each dominance level.  The numbers are of course drawn from control board.

The full list of stocks contained in each strategy shall be messaged to output board for this step.

#### Step 2: Filtering and sorting

As new a final logical filter like Per\_1d>0 allowing only a subset of step1-picks to survive is a new thing. Especially in long tail strategies it should be possible to weed out born loosers as contrart to temporary downs (how to do that is outside the processor).  Sorting is prioritisation like in version 1.

Besides being a process output going to output board the list of stocks are also sent to the gross list of strategi stocks (StrategicStocks.xlsx).  

This list targets ordinary users with no interest in the mechanics of calculation.
Production runs stop here and use marked 3 marked strategies to guide output.  Development runs may do for all, or omitted (to be decided).  Also accompagnying data  can be included.

##### Step 3: Backtesting

Backtestings new features are already described in preamble above trying to give condensed as well as longitudinal insight in in-sample performance and risk.  Note the fusion of extension and full-period backtests.
I believe that 1 day hops only shall be used - longer hops and overlapping ones only obscures the fundamental characteristics of the strategy: Chained ones becones a lottory about which hills you jump on, and overlapping amplifies this, so I will stop. Maybe users will demand it, but the it shall added for communication reasons. But for now omit.

##### Step 4: Forward-walk

Some out-of-sample testing should also be included. Especially I like the fold-results

##### Final output

As described in preamble, in development step 0-4 are looped for all strategies marked in control board for comparison and go to comparison\_date.xlsx.  In production only step 0-2 are looped for 3 strategies preselected (StrategicStocks.xlsx).

We can archive all produced but a database for their storage would be nice. Storing would open for long-term evaluation of outputs.

## Technicalities

* Separation of calculations in py files should follow these steps. So looking in the code folder should immidiately envisage the step calculations. Full pipeline is assingned to a separate conductor (like in longi.py).  

## Directions of use

Every `python` call goes through `ssh -p 2222 sm@innovia.dk` then `conda activate potsystem_env`,
from `~/potentials/strategy_grp2/app/code` — never on the Windows host (see `CLAUDE.md`'s hard
rules; this section only covers what to type once there).

### The control board

`app/control/control_board.xlsx`, three sheets:

* **`Runs`** — one row per run. `active` (any of `x`/`X`/`yes`/`true`/`1`) is the tick; blank means
  idle. A blank cell elsewhere falls back to the schema default in `param_spec.py` — a row can be
  as few as `active` + `group_expression`. `label` names the row everywhere downstream (Step
  sheets, Step3/4 columns, charts); leave it blank and one is derived from
  level/group/priority_attribute — give rows their own `label` when several would otherwise derive
  the same one (e.g. a `from_rank` comparison at the same grouping).
* **`Settings`** — global knobs, not per run: `min_chain_lots`, `wf_min_train`, `wf_test_len`,
  `archive_on_run`, `production_strategy_count`.
* **`Legend`** — generated from `param_spec.py`, never hand-edited: every column's type, default
  and legal values, one row each. This is the reference for every parameter below.

`python conductor.py --make-board` (re)writes `Runs`/`Settings`/`Legend` from the current schema,
**preserving every existing row** — safe to run any time the schema has grown a column; a column
the schema no longer has is reported, not silently dropped.

### Setting up a row

| step | columns | notes |
|---|---|---|
| — | `active`, `purpose`, `label`, `note` | `purpose`: `P` (production, steps 0-2) or `D` (development, steps 0-4) |
| 0 | `group_expression` | e.g. `Stamdata.GICS`, `#ALL`, `Stamdata.Zone .and. Stamdata.GICS`, `Stamdata.Homeland='US'` |
| 1 | `level`, `persistence_window`, `persistence_frac`, `dominance_attribute`, `dominance_direction`, `dominance_decile`, `dom_count_min`, `tickers_per_group` | `dominance_direction` is spelled `small_wins`/`big_wins`, not a bare boolean. `dom_count_frac` is NOT a board column — see Refinements below |
| 2 | `post_filter`, `priority_attribute`, `priority_direction`, `from_rank`, `focusset_size` | `from_rank`: `1` = best n, `-1` = worst n, `"mid"` or a fraction `0<f<1` = pool-relative window (`mid` avoids both ends), an integer `k>=2` = fixed offset |
| 3 | `period`, `no_go_gspc_rsi`, `informational_attributes` | `period` must be one of the seven-pack: 1/5/10/20/50/100/200 |
| 4 | `wf_group` | comma-separated `label`s to compare against in the walk-forward test; blank = every other active `D` row sharing this row's `period` |

### Running it

```bash
python conductor.py --make-board   # write/refresh the board from the schema
python conductor.py --dry-run      # validate every row; reads no data, writes nothing
python conductor.py --check        # step 0 only: universe size, group count, resolved attributes
python conductor.py --production   # steps 0-2 for active P rows -> report/StrategicStocks.xlsx
python conductor.py                # steps 0-4 for active rows -> report/compare_strategies_<date>.xlsx
```

Run them in that order when trying a new row for the first time: `--dry-run` catches a typo
before anything touches data; `--check` confirms the grouping resolves to something sane; then
`--production` or the bare development tick. Every entry point preflights the live repository
first and freezes a coherent snapshot before reading anything else; if that fails (the
repository mid-update, a required file missing or stale), run `python preflight.py` directly for
a one-screen table of every required file's daynum, age and status.

### Where output lands

* **`report/StrategicStocks.xlsx`** — one sheet per active `P` row: today's gross list,
  rank-ordered, with the priority attribute's value. The daily-advice artifact for users with no
  interest in the mechanics.
* **`report/compare_strategies_<date>.xlsx`** — one workbook per development tick, six sheets:
  `Runs` (every active row verbatim + status/universe/vintage), `Step1_groups` (elevated groups +
  member tickers), `Step2_picks` (the gross list, same as `StrategicStocks.xlsx`), `Step3_compare`
  (transposed metrics, one column per active `D` row, best `chain_annual` leftmost),
  `Step4_walkforward` (one summary block + fold table per row), `Charts`.
* **Not yet built**: standalone per-run/per-fold files under `report/backtesting/` and
  `report/walkforward/` (the folders exist; `outputboard.py` currently only writes the one
  combined workbook above) — see Status.

## Refinements agreed during implementation (2026-08-03)

* **The Step-1 qualifying-ticker count becomes relative, not absolute.** v1 fixed an absolute
  count per group criterion (10 for GICS, 5 for Sector2) and it does not transfer: 10 asks a
  93-member GICS sector for 11% of itself but a 24-member Sector2 sector for 42%. Since group
  size is not known in advance once the group definition is a free expression, the threshold is
  now `max(dom_count_min, ceil(dom_count_frac * group_size))`.
* **`dom_count_frac` is not a board column (2026-08-03) — it is derived, always.** A group only
  counts as dominant when it is *over-represented* among today's qualifiers relative to the
  population base rate; `dominance_decile` IS that base rate, so `dom_count_frac` must always
  sit above it to mean anything (equal to it just reproduces the average; below it is close to
  guaranteed for large groups and pure noise for small ones — see `#ALL`'s structural
  non-elevation in Status below, the live proof this matters). There is no meaningful per-row
  value for it independent of `dominance_decile`, so `step1_dominance.py` always computes
  `dom_count_frac = dominance_decile + shared.config.DOM_COUNT_FRAC_MARGIN` (`0.05`) and the
  board column was removed (`dom_count_min` stays board-driven — it protects small groups from
  a single-ticker fluke, an independent concern). The v1-parity escape hatch this replaced
  (`dom_count_frac=0`, reproducing v1's fixed absolute count exactly) was a one-time
  verification, already done and recorded below — not an ongoing board capability.
* **`from_rank` gains a pool-relative middle window**, alongside v1's best-n (`1`) / worst-n
  (`-1`): `"mid"` or a quantile `0<f<1` centres the picked window in that day's candidate pool
  (avoiding both the top supers and the bottom losers), and an integer `k>=2` is a fixed offset
  ("skip the top k-1"), kept for parity with v1's absolute-offset behaviour. The pool size
  varies day to day, which is why a fixed rank cannot mean "the middle" on its own — see
  `param_spec.parse_from_rank`.
* **Documentation split**: this file is the one living design document (present tense, updated
  in place as phases land); `CLAUDE.md` is only the short entry card Claude Code auto-loads.
* **Step 2's production output is now a full, uncapped gross list, decoupled from Step 3/4's
  backtest sampling (2026-08-03).** `tickers_per_group`/`from_rank`/`focusset_size` originally
  capped Step 2's pooling too, sharing one `select_focusset()` with the backtest hop-builder —
  but a small dominant group should never lose candidates to an arbitrary per-group pre-cut, and
  production should always show the best end of the ranking, never a deliberately worst/mid
  research window. `step2_focusset.production_pick()` now pools EVERY member of every elevated
  group, applies `post_filter`, sorts best-first by `priority_attribute`, and caps only at
  `shared.config.PRODUCTION_GROSS_CAP` (20 — a code constant, not a board column: a user should
  see the whole qualifying list, not something tuned per row). `select_focusset()` is unchanged
  for Step 3/4 — `tickers_per_group`/`from_rank`/`focusset_size` remain exactly what a backtest
  hop needs: a fixed, comparable sample size across hundreds of hops.

## Status

**Phase 1 (skeleton) done, 2026-08-03.** In place: directory layout under `app/`; `shared/`
carried over from strategy_grp verbatim (`chain.py`, `datacheck.py`, `data_loader.py`,
`select.py`) plus a `config.py` adapted for this project's paths; `param_spec.py` (the full
parameter schema — every control-board column, its type, default and legal values, across
steps 0-4); `control_board.py` (reads/validates/generates `control_board.xlsx` — three sheets,
Runs/Settings/Legend); `conductor.py` with working `--make-board` and `--dry-run`.

**Phase 2 (production path, steps 0-2) done, 2026-08-03.** In place: `shared/expression.py`
(the Stamdata/Longi expression parser — `#ALL`, bare-column grouping dimensions, `.and.`-joined
universe filters, `Longi.<factor><op><value>` post-filter terms); `shared/select.py::pick_by_rank`
extended for the `from_rank` window forms (`edge`/`offset`/`quantile`); `step0_data.py` (universe
+ group resolution, the GICS/Sector2-only twin binding for `conf`/`sectorbeta`, and a first
ad-hoc builder — cached group-level Longi aggregates for an arbitrary grouping); `step1_dominance.py`
(levels A/B/C on the relative `dom_count_min`/`dom_count_frac` threshold); `step2_focusset.py`
(pooling, `post_filter`, the `from_rank` window); `preflight.py` (board-driven required-files
guard, same `shared/datacheck.py` underneath as v1); `conductor.py --check` (Step-0 diagnostics)
and `--production` (steps 0-2 → `report/StrategicStocks.xlsx`, one sheet per row).

**Verified against live data (daynum 2203, 2026-08-03):**
- **v1 parity, ticker-for-ticker.** A GICS row (`dominance_attribute=rsi`/big_wins,
  `dom_count_min=10`, `dom_count_frac=0`, `priority_attribute=spr100d`/big_wins, `from_rank=1`)
  and a Sector2 row (`dom_count_min=5`) reproduce `strategy_grp` v1's live `DomGICS_now`/
  `DomSector2_now` picks exactly, both groupings, read-only (no v1 report files touched).
- **New capability.** `Stamdata.Zone .and. Stamdata.GICS` resolved to 39 groups, `#ALL` to one
  group of 1209 — both parse and run with no code change. `#ALL` is retired from the board
  (2026-08-03), though: a group can never be over-represented relative to itself, so it
  structurally never elevates (0 of 661 hops, ever) — it only produced pointless formalities
  downstream, including a walk-forward section that silently relayed another row's result under
  its own name (its `wf_group` defaults to "every other active D row", and since `#ALL` never has
  a usable `chain_annual` it never wins its own comparison — SM: "produce no usable advice to
  anyone"). `#ALL` the *expression* still parses fine; it just is not a useful `group_expression`
  choice given how Step 1's dominance threshold works.
- **The `from_rank` middle window does what it says.** Three otherwise-identical rows
  (`from_rank` = `1` / `"mid"` / `-1`) on the same daynum produced three disjoint focussets,
  strictly ordered on `spr100d` (best ~270-1283, mid ~101-153, worst 0) — direct confirmation
  that `mid` avoids both the top supers and the bottom losers rather than landing on either end.
- Board validation was stress-tested with a deliberately bad row (blank `group_expression`,
  `from_rank=0`, `period=13`, an unknown direction spelling) — all four errors caught with the
  row number; a duplicate-label collision (two rows differing only in `from_rank`) was also
  caught, which led to fixing the label deriver to fold a non-default `from_rank` into the label.

The board now carries these seven rows as **inactive, documented templates** (`note` says
"template, verified 2026-08-03 — flip active to run") — nothing runs until SM activates one.

**Phases 3-4 (backtest, walk-forward, output board) done, 2026-08-03.** In place:
`shared/market.py` (gain/benchmark helpers consolidated from v1's engine.py/report.py/extension.py);
`step3_backtest.py` — `build_hops()` walks the whole history once per row producing a FUSED
timeline (older hops read realized `longi_future_per<period>d.csv`; the trailing ~`period` hops
read partial PotDat price return, flagged `realized=False`, excluded from the chain — v1's
"extension" folded into the main backtest, per the design note's "fusion of extension and
full-period backtests"); `compute_metrics()` reproduces v1's `avg_gain`/`avg_alpha`/`avg_beta`/
`chain_ret`/`chain_annual`/`chain_n`/`Worst`/`N_loss`/`origin_sens%`/`MIN_CHAIN_LOTS` eligibility
exactly (same `shared/chain.py`), **plus `median_gain`/`hit_rate%` beside every mean, in Step 3
as well as Step 4** — over an optional `[floor_daynum, cap_daynum]` span, so Step 4 re-aggregates
the *same* hop series per fold instead of re-simulating. `step4_walkforward.py` ports v1's
`walkforward.py` fold geometry (`T - period` embargo) verbatim; the "candidate grid" of
parameter-sets there becomes one row's `wf_group` here — a comma-separated list of other rows'
labels (blank = every other active D row sharing `period`); one `GroupResult`/Summary is produced
per row that declares the test, scored against its own candidate set. `outputboard.py` assembles
`report/compare_strategies_<date>.xlsx`: `Runs` (every active row + status/universe/vintage),
`Step1_groups` (elevated groups + members at the current daynum), `Step2_picks` (the gross list,
same as `StrategicStocks.xlsx`), `Step3_compare` (transposed, one column per active D row, sorted
by `chain_annual`, thin columns tinted), `Step4_walkforward` (one summary block + fold table per
row), `Charts` (three native openpyxl charts: cumulative single-origin chain by lot index,
IS-vs-OOS `avg_gain`, `avg_gain` vs `median_gain`).

**Verified end-to-end (daynum 2203, 2026-08-03):** the `from_rank` trio (`fr_best`/`fr_mid`/
`fr_worst`, `wf_group` set to compare all three) ran a full development tick in ~23s — Step1/Step2
sheets reproduced the exact same tickers the Phase-2 parity check found; Step3 gave `fr_best`
`chain_annual`=131.2 over 27 chain lots (661 hops, span daynum 1642-2182) against `fr_mid`'s 25.6
and `fr_worst`'s 36.8 — consistent with `fr_best` drawing from far stronger `spr100d` values;
Step4 correctly selected `fr_best` in every fold (its training `chain_annual` dominates); all
three chart objects confirmed embedded and fed by their data tables. Board reset to idle
afterward — `wf_group="fr_best,fr_mid,fr_worst"` kept on the three template rows as a documented
default, since it demonstrates exactly the comparison the middle-window design was for.

**Per-run detail workbook + progress output done, 2026-08-03.** `step3_report.py` writes
`report/backtesting/run<N>_<date>.xlsx` — one file per active D-purpose row, N = tick order,
an "Operational" sheet adapted from strategy_grp v1's (same ticker/avg_gain/mkt_gain/alpha/beta
row shape) to v2's fused `Hop` timeline: row 1 is the row's `label` (not v1's `No_go_GSPC_rsi`),
row 2's `A2` is blank (v1's editable-threshold formula dropped — not read by anything), row 3 is
NEW (`n_candidates` — the Step-3/4 pool size *before* the `from_rank`/`focusset_size` window,
i.e. how many were available before picking the tested N), row 4 is `dominance_cutoff`, and the
`informational_attributes` rows are read from the row's own board column (`Hop` gained
`n_candidates`/`dom_cutoff` fields to carry this without recomputing the pool twice). Called from
`outputboard.assemble()` right after Step 3's backtests are built. Pre-existing stale files in
`report/backtesting/` (leftover `strategy_grp` v1 output from before this project's first commit,
sitting in a folder set up in advance) are archived on each write. `report/walkforward/`'s
per-fold file remains deferred — not asked for yet.

Every step now prints progress as it runs (`outputboard.py`/`step3_backtest.py`/
`step4_walkforward.py`): per-row headers, a heartbeat every ~10% of a `build_hops` simulation,
and per-fold lines in Step 4 — the development tick used to print nothing until the final "Wrote
...". `run.cmd` (a PC-user launcher, `app/run.cmd`, alongside a `control_board.lnk` shortcut) uses
`ssh -t` + `python -u` so this actually streams live rather than block-buffering to the end; it
loops back to its menu after each run instead of exiting.

**Not yet built**: a result database (`app/data/runs.db`, deferred/hook-only per the plan);
`shared/expression.py` support for `Longi.*` terms inside `group_expression` itself (currently
`Stamdata`-only, as the design note allows starting with); `report/walkforward/`'s standalone
per-fold file (the folder exists, but `outputboard.py` only writes the one combined
`compare_strategies_<date>.xlsx` today).






