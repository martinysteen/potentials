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

Pick number per group (typically 3 in version 1) shall be individual to level. I guess level A will maintain 3, but B get 4 and C thus compensation for the dimishing number of ticker-promotions to each dominance level.  The numbers are of course drawn from control board.

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

## Refinements agreed during implementation (2026-08-03)

* **The Step-1 qualifying-ticker count becomes relative, not absolute.** v1 fixed an absolute
  count per group criterion (10 for GICS, 5 for Sector2) and it does not transfer: 10 asks a
  93-member GICS sector for 11% of itself but a 24-member Sector2 sector for 42%. Since group
  size is not known in advance once the group definition is a free expression, the threshold is
  now `max(dom_count_min, ceil(dom_count_frac * group_size))`. `dom_count_frac=0` reproduces
  v1's fixed-count behaviour exactly (used for the parity runs against strategy_grp).
* **`from_rank` gains a pool-relative middle window**, alongside v1's best-n (`1`) / worst-n
  (`-1`): `"mid"` or a quantile `0<f<1` centres the picked window in that day's candidate pool
  (avoiding both the top supers and the bottom losers), and an integer `k>=2` is a fixed offset
  ("skip the top k-1"), kept for parity with v1's absolute-offset behaviour. The pool size
  varies day to day, which is why a fixed rank cannot mean "the middle" on its own — see
  `param_spec.parse_from_rank`.
* **Documentation split**: this file is the one living design document (present tense, updated
  in place as phases land); `CLAUDE.md` is only the short entry card Claude Code auto-loads.

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
  group of 1209 — both produce sane picks with no code change.
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

**Not yet built**: a result database (`app/data/runs.db`, deferred/hook-only per the plan) and
`shared/expression.py` support for `Longi.*` terms inside `group_expression` itself (currently
`Stamdata`-only, as the design note allows starting with).






