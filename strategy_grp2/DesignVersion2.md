# Design of Strategy\_grp2 processor

## Basic thinking

Strategy\_grp2 is version 2 of Strategy\_grp. In version 2 we are shall use a lot of the calculative machinery from Strategy\_grp yet not with several changes to be described here. So Stategy\_grp is to be used during development of Strategy\_grp2 remembering that Strategy\_grp will be retired when version 2 goes into full production.

**That retirement happened on 2026-08-07:** `strategy_grp` was moved to `../_archive/strategy_grp/` and is frozen — no further work, no runs. Every "v1" reference below is a historical pointer into the archive, not a live dependency; strategy\_grp2 is now the system's only strategy consumer.

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
| 3a | `stop_loss` | Exit level, e.g. `-10`. Requires `period` in `{20, 50}` — see the 2026-08-05 refinement below |
| 4 | `wf_group` | comma-separated `label`s to compare against in the walk-forward test; blank = every other active `D` row sharing this row's `period` |

### Running it

```bash
python conductor.py --make-board   # write/refresh the board from the schema
python conductor.py --dry-run      # validate every row; reads no data, writes nothing
python conductor.py --check        # step 0 only: universe size, group count, resolved attributes
python conductor.py --production   # steps 0-2 for active P rows -> report/StrategicStocks.xlsx
python conductor.py                # steps 0-4 for active rows -> report/compare_strategies_<date>.xlsx
```

**Every one of these stops if `control_board.xlsx` is still open in Excel** (exit 2), and
each prints when the board on disk was last saved. See "the unsaved-board guard" below;
`--board-open-ok` overrides it.

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
* **`report/compare_strategies_<date>.xlsx`** — one workbook per development tick, seven sheets:
  `Runs` (every active row verbatim + status/universe/vintage), `Step1_groups` (elevated groups +
  member tickers), `Step2_picks` (the gross list, same as `StrategicStocks.xlsx`), `Step3_compare`
  (transposed metrics, one column per active `D` row, best `chain_annual` leftmost),
  `Step3a_stopout` (cost/benefit sweep across stop levels, one block per eligible `D` row — see
  the 2026-08-05 refinement below), `Step4_walkforward` (one block per *candidate set*: summary +
  per-candidate table + fold table — see the 2026-08-04 refinement below), `Charts`.
* **Not yet built**: standalone per-run/per-fold files under `report/backtesting/` and
  `report/walkforward/` (the folders exist; `outputboard.py` currently only writes the one
  combined workbook above) — see Status.

## Correction 2026-08-05 — dom_count_min restored to SM's original halving rule

The 2026-08-03 refinement below (`dom_count_frac`, size-INCREASING) was built on a wrong
assumption about what v1's "fixed absolute count" actually was. SM's real prototype rule
was never a flat 10-for-GICS/5-for-Sector2 applied uniformly — it already had a small-group
carve-out, just in the opposite direction from what got implemented:

    threshold = dom_count_min                  for a group >= 2 * dom_count_min members
    threshold = group_size / 2 (not rounded)    below that

Equivalently `min(dom_count_min, group_size / 2)` — the two branches agree exactly at the
boundary. A big sector needs a real, size-independent headcount to count as dominant; a
*small* sector needs proportionally FEWER qualifiers, not more, since it has fewer members
to draw them from in the first place.

**Concrete evidence this had gone wrong:** on live GICS data (daynum 2205, `dominance_attribute
=rank`, `decile=0.10`), Indu (227 members) had MORE qualifying tickers (34) than Tech (201
members, 31) — genuinely stronger sector-wide concentration by any absolute reading — yet
the 2026-08-03 formula excluded Indu (needed 35, size-scaled) while admitting Tech (needed
31). That inversion is exactly backwards from "domination is on Tech and Indu, primarily"
(SM). The two questions were also wrongly entangled: `dominance_decile` was feeding
`dom_count_frac` (`decile + 0.05`), so it silently decided BOTH which individual tickers
count as elite that day AND how many a group needs — they are independent decisions and
`dom_count_min` alone now carries the second one.

**Verified after the fix** (same daynum, same row): `dom_count_threshold` is a real,
monotonic lever again --

| `dom_count_min` | elevated GICS sectors |
|---|---|
| 1 | Basi, C-Di, C-St, Ener, Fina, Heal, Indu, Tech |
| 3 | Basi, C-Di, Fina, Heal, Indu, Tech |
| 10 (SM's original design value) | Basi, C-Di, Fina, Indu, Tech |
| 20 | Indu, Tech |
| 40 | (none) |

`shared.config.DOM_COUNT_FRAC_MARGIN` and the `dom_count_frac` derivation are removed —
`step1_dominance.dom_count_threshold(group_size, dom_count_min)` is the whole rule now, and
`dominance_decile` no longer feeds it. Also verified separately: today's elite population is
120 of 1199 GICS-grouped tickers (10.01%), matching `dominance_decile=0.10` almost exactly —
the decile math itself was never in question, only the group-count threshold.

**Caret-prefixed tickers excluded from the universe, same day.** 14 benchmark/index tickers
(`^GSPC`, `^VIX`, `^BTC`, ...) carried a GICS value in Stamdata and were forming their own
spurious 14-member "Index" pseudo-sector — explaining why `Index` never elevated in the
2026-08-04 Status notes (it was never a real sector). `shared/expression.py::
apply_stamdata_filters` now excludes any ticker starting with `^` unconditionally, before
any user filter runs — universe drops from 1213 to 1199 tickers, GICS group count from 13
to 12, real elevated sectors unaffected (the pseudo-sector never elevated anyway). This is
the one choke point every `group_expression` resolves through (Steps 0-4 all key off
`Step0Result.universe`/`.groups`), so the fix is system-wide, not GICS-specific. SM,
2026-08-05: *"caret-ones has nothing to do in lot simulation. They might be needed for
reference ... but this could be added later on"* — reference paths (market context rows,
benchmark returns in `shared/market.py`) read these tickers by name directly and never go
through `group_expression`, so they are untouched by this change, by design.

**Still open, deliberately not touched:** `longi_future_per<period>d.csv` (and presumably
its siblings) still carries the same 14 caret rows, and `market.market_gain_realized()`
averages over every row in that file — so Step 3's "average stock you could have picked
that day" benchmark is very slightly diluted by ~14 index/crypto rows among ~1200 (a small
weight, but the same category of issue). Not in scope for this fix; flagged for later.

## Refinements agreed during implementation (2026-08-03)

**SUPERSEDED 2026-08-05 — see the correction above.** The two `dom_count_frac` bullets below
record what was decided and why at the time; the formula itself (`max(...)`, size-increasing)
is no longer what the code does. Left in place as history, not as current behavior.

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
  backtest sampling (2026-08-03).** **SUPERSEDED 2026-08-05 — see the correction below.**
  `tickers_per_group`/`from_rank`/`focusset_size` originally capped Step 2's pooling too,
  sharing one `select_focusset()` with the backtest hop-builder — but a small dominant group
  should never lose candidates to an arbitrary per-group pre-cut, and production should always
  show the best end of the ranking, never a deliberately worst/mid research window.
  `step2_focusset.production_pick()` pooled EVERY member of every elevated group, applied
  `post_filter`, sorted best-first by `priority_attribute`, and capped only at
  `shared.config.PRODUCTION_GROSS_CAP` (20 — a code constant, not a board column: a user should
  see the whole qualifying list, not something tuned per row). `select_focusset()` is unchanged
  for Step 3/4 — `tickers_per_group`/`from_rank`/`focusset_size` remain exactly what a backtest
  hop needs: a fixed, comparable sample size across hundreds of hops.

## Correction 2026-08-05 — production_pick guarantees tickers_per_group per group

The 2026-08-03 decoupling above traded away something SM had actually specified: pooling
every elevated group's full membership and keeping only the GLOBAL top
`PRODUCTION_GROSS_CAP` by `priority_attribute` meant a genuinely dominant group could get
**zero** production picks if its tickers didn't rank well against other dominant groups'
candidates — the opposite of what calling a group "dominant" is supposed to mean. Live
evidence: with 5 elevated GICS sectors (Basi, C-Di, Fina, Indu, Tech) and
`tickers_per_group=3`, the old rule gave Tech 7, Fina 6, Indu 6, C-Di 1, and **Basi 0** — a
sector Step 1 had just certified as dominant, invisible in the output. SM: *"we have
specified in control board that we want 3 picked from each, which makes 15 in total."*

`step2_focusset.production_pick()` now takes EACH elevated group's own top
`tickers_per_group` by `priority_attribute`, unconditionally — the same per-group-cap logic
`_pool()` already used for Step 3/4, applied here too. Total is
`num_elevated_groups * tickers_per_group` (or less only when a group itself has fewer
qualifying members than that), never truncated by competition against another group's
stronger candidates. `shared.config.PRODUCTION_GROSS_CAP` is removed — nothing reads it
anymore. Verified live: 5 groups x 3 = 15 picks, every group represented exactly 3 times,
Basi included.

## Refinement 2026-08-04 — Step 4 reports per candidate set, and per candidate

**Symptom:** four active rows, four Step-4 blocks, byte-identical numbers in all four.
**Cause, not a bug in the fold maths:** a walk-forward test belongs to the *candidate set*,
not to the row that declared it. With `wf_group` blank everywhere — the documented default,
"every other active D row sharing my `period`" — all four rows resolve to the same set of
four candidates, so `walk_group` ran the same experiment four times; and since the block
reports the *selected* candidate per fold, and the same candidate won every fold, every
block relayed that one candidate's numbers under a different owner's heading. This is the
same failure mode already recorded for `#ALL` above, reached from the other direction.

Three changes:

* **One block per distinct candidate set**, headed by every owner that declared it
  (`GroupResult.owner` → `owners`). Identical sets are no longer re-run or re-printed.
* **A per-candidate table beside the summary** (`summarize_candidates()`). The Summary row
  answers *"does picking the training winner survive out of sample?"*, which is one number
  for the whole set — it never was a per-row result, and is now labelled as such on the
  sheet. The new table answers *"how did THIS strategy do out of sample?"*: every candidate's
  own IS/OOS gain, alpha, median, hit-rate and lot count over the same folds, best
  `oos_avg_gain` first. The data was already being computed per fold per candidate and
  discarded at the sheet boundary. `Charts`' IS-vs-OOS bar chart reads this too — it
  previously drew one identical bar pair per owner.
* **`wf_min_train`/`wf_test_len` from the `Settings` sheet are now actually passed** to
  `walk_group`; the call had been taking the module defaults, which happen to equal the
  shipped values (315/63), so changing them on the board did nothing.

Step 4 also **reuses Step 3's hop series** (`hops_cache`) instead of re-running `build_hops`
per candidate per owner. `build_hops` is deterministic in `row_resolved`, so the four-row
tick above was paying for 16 identical full-history simulations on top of Step 3's four.

**Beware `oos_lots` when comparing candidates.** In the 2026-08-04 four-row tick, `Middle`
and `Agressive` show the *best* `oos_avg_gain` (7.95 / 7.13 vs `A_Zone_GICS_spr100d_-1`'s
7.00) on **19 out-of-sample lots against 315** — both are level-B GICS rows with
`dom_count_min=10`, which elevates a group on very few days. Their Step-3 `chain_n` (6 and
4) is at or near `min_chain_lots`. The column is in the table so the sample size cannot be
read past.

## Refinement 2026-08-04 — the unsaved-board guard

Editing the board and forgetting to save means a tick silently runs the *previous* board —
a failure with no symptom, since every number produced is internally consistent, just
answering last version's question. VBA would test `ActiveWorkbook.Saved`; **we cannot**.
That flag lives in the Excel process on the Windows host, this code runs on the Ubuntu
server over SSH, and the unsaved edits exist only in Excel's memory — nothing on disk can
reveal them, so a truly faithful dirty-test is not available at any price here.

What IS on disk is Excel's owner file, `~$control_board.xlsx`, written beside the workbook
while it is open and deleted on close. It carries the holder's username, and it travels
over the Samba share, so the server sees it. `control_board.require_saved_board()` therefore
tests one notch stricter than VBA: **it stops when the board is OPEN, not when it is
provably dirty** — an open-but-saved board is stopped too. That trade is deliberate: the
stop costs one keystroke, the silent run costs a whole misread comparison.

* Applies to **every** `conductor.py` entry point, including `--make-board` (which would
  otherwise overwrite the copy Excel has open). Exit code **2**.
* The message names who holds it, when the board was last saved, and the `rm` for a stray
  lock file left by an Excel crash — the one false positive this design can produce.
* `--board-open-ok` proceeds with the board exactly as it sits on disk.
* Every run, guarded or not, prints `control_board.xlsx last saved: <when>` — so a forgotten
  save is visible after the fact as well as before.
* `app/run.cmd` holds the window open on any non-zero exit, so the stop is read rather than
  scrolled away by the menu redrawing under it.

## Refinement 2026-08-04 — a report must speak the board's language, and account for every active row

Three steering complaints from live output, all of them reports lying about or hiding what
the board said:

* **`dominance_direction` came back as Excel `TRUE`/`FALSE`.** The board deliberately spells
  directions `small_wins`/`big_wins` precisely because a direction cannot be "false" — but
  `parse_direction` turns that into a bool for internal use, and the Runs sheet wrote the
  resolved value straight out, undoing the whole point of the spelling.
* **`from_rank` came back as `('edge', -1)`** — the internal classifier tuple from
  `parse_from_rank`, naming a concept (`edge`/`offset`/`quantile`) the board never mentions.
* Fix for both: **`param_spec.format_value(name, value)`** — the board spelling of any
  resolved value. Every report goes through it (`Runs`, `Step3_compare`); a new display
  form belongs there, not in a writer.

**Three settings decide which end of a ranking a row picks from, and they are independent** —
`dominance_direction`, `priority_direction`, `from_rank`. `Step3_compare` now lists all
three adjacently (with `tickers_per_group` and `post_filter`), because a mismatch is
invisible in any one of them alone. The trap in the 2026-08-04 board: `priority_attribute=rank`
with `priority_direction=small_wins` correctly says "a low rank number is good", and then
`from_rank=-1` draws from the **worst** end of that correctly-sorted list. `from_rank` is not
a second direction flag — direction sorts the pool, `from_rank` chooses where in the sorted
pool to draw. `1` is the answer for any row meant to produce advice; `-1`/`mid` are research
probes (see the `fr_best`/`fr_mid`/`fr_worst` template trio).

**Active rows no longer vanish.** `conductor.cmd_develop` filtered `r.active and r.ok` and
never mentioned the difference, so a board with 4 active rows produced a 3-row workbook with
nothing to say where the fourth went. A rejected row now appears on `Runs` with
`status=REJECTED` and its parse error; board-level errors (duplicate active labels, bad
`Settings`) get a red banner above the table; and the tick prints both before it starts.
Separately, `Step1_groups`/`Step2_picks` now emit an explicit `(no group elevated at this
daynum)` / `(no pick — cash hop)` line, since an absent label was indistinguishable from a
missing result — for a strict level-B row that elevates nothing today, "nothing" is the
answer, not a failure. The 2026-08-04 counts (4 active → 3 on `Runs` → 2 on `Step1_groups`
→ 3 on `Step3_compare`) decompose exactly this way: `Middle` was rejected by validation and
dropped silently, and of the three that ran, `Agressive` elevated no group that daynum.

## Refinement 2026-08-05 — Step 3a: stop-out

Step 3 holds every picked stock for the full `period` horizon no matter what happens in
between — a hop's gain is `longi_future_per<period>d.csv[t, daynum]`, and nothing can exit
early. `longi_future_minaggr20d/50d.csv` (built in longi, dec144e) is a "foresight eye": at
signal day `d` it already holds the lowest gain the path reached before the horizon closed
(<= 0, floored at 0). That makes an exit simulable after the fact — SM: *"if a parameter
called STOP on say -10 is available, we can set the final end gain of that stock to -10"* —
and SM asked for it as a **separate operation late in Step 3, not threaded into the
simulation**, since stops have a price (a stopped stock might have recovered past `STOP` by
the horizon) and that cost has to be measured, not assumed away.

**Kept as a pure post-transform on the hop series** (`step3a_stopout.apply_stop`), for a
practical reason as much as a conceptual one: `build_hops` is the expensive part of a tick
(one Step-2 selection per daynum) and does not depend on where a stop is set, so **one
simulation can be re-scored at every stop level**, making a sweep across levels nearly free.
`step3_backtest.BacktestResult` now carries both `.hops` (what Step3_compare, the charts and
`step3_report` show — stop-applied when the row's own `stop_loss` is set, unchanged
otherwise) and `.hops_raw` (always the pre-stop timeline, what `step3a_stopout.sweep()`
re-scores at every level).

The clamp is unconditional, not `max(gain, STOP)`: a breached stock is being simulated as
**exited**, so a later recovery past `STOP` is not available to it — that forgone recovery is
exactly the "cost" side, not something to award back by taking the better of the two numbers.
Still-open hops have no `minaggr` value yet (its newest `period+1` columns are blank by
construction, the same realized/open boundary `longi_future_per*.csv` has); `shared.market.
partial_min_gains` covers them instead, reading the *elapsed* part of PotDat's price path —
realized history, not foresight.

**New board column** (step 3a): `stop_loss`, float, `<= 0`, default `0`/blank = off (today's
behaviour). Requires `period` in `{20, 50}` — the only horizons `longi_future_minaggr*.csv`
covers (`shared.config.MINAGGR_PERIODS`) — checked in `control_board.resolve_row` since it
is a cross-column constraint, not a single cell's type. **New Settings**: `stop_sweep` (the
comma-separated ladder every eligible `D` row is swept at regardless of its own `stop_loss`,
default `-5,-7.5,-10,-15,-20`; blank = no sweep) and `stop_annual_tolerance` (default `5`,
see Ranking below).

**Ranking (SM's choice, 2026-08-05): risk-first, not return-first.** A population-level pass
over all 762,348 realized (ticker, daynum) positions in history shows *why* this needed
asking rather than assuming: at `stop=-10`, 19.7% of positions are stopped, avoiding 630,698
points of loss against 508,772 forgone — mean gain improves (+1.71 -> +1.87) but the median
collapses (+0.87 -> +0.53) and hit-rate drops (54.6% -> 52.6%). Mean and risk point opposite
ways, so `step3a_stopout.best_level()` ranks candidate levels by `Worst` (least negative
first) then `N_loss` (fewest first), and flags the best-ranked level whose `chain_annual`
gives up no more than `stop_annual_tolerance` percent of the unstopped baseline — return is
shown beside risk on the sheet, but risk is what picks the flagged row.

**Reporting**: `Step3a_stopout` (new sheet) — one block per eligible active `D` row (period in
`{20, 50}` and something to sweep at: the row's own `stop_loss`, the board's `stop_sweep`, or
both), the sweep table (`n_positions`/`n_stopped`/`benefit`/`cost`/`net`/`net_per_position`
beside the full Step-3 metric set per level), with the flagged row highlighted. `stop_loss`,
`n_stopped` and `stop_net_per_position` also ride on `Step3_compare` beside the row's other
parameters. `Charts` gained a fourth block, `chain_annual`/`Worst` vs. stop level per eligible
row. `step3_report`'s per-run Operational sheet gained an `n_stopped` row and marks an exited
ticker's cell in dark red, so the timeline shows *where* a stop bit, not just the count.

**Prior to keep in view**: `strategy_grp` v1 found *all* price-stop variants lost money —
a different mechanism (an intraday price stop in the sandbox, pre-cutover same-day-entry
convention). This one reads the exact realized path under the current entry-is-signal+1
convention, so it is a cleaner measurement, but if the sweep comes back negative across the
live board's rows that is a real answer, not a bug — the feature ships with `stop_loss=0` as
the default precisely so a negative verdict changes nothing by default.

**Not in scope**: no stop on the production path (`StrategicStocks.xlsx` stays the entry-time
gross list — a stop is an exit rule, not a selection rule) and no trailing / peak-to-trough
stop (`minaggr` is drawdown *from entry*; that would need a different longi measurement).

### Fold stability (same day, 2026-08-05)

SM, on Step 4: *"the only thing on step 4 I really understand is the folds ... that could
be done on stop-corrected lots as well as on intact lots."* Right, and simpler than the
walk-forward candidate-selection test first proposed for this: no training window, no
in-sample winner, no selection-skill scoring — those exist in Step 4 to answer "would
picking the in-sample winner among several *different strategies* have survived", and stop
levels are not that: they're the same picks, same days, different clamps, so a
training-window pick between them would mostly measure noise. What's wanted instead is
plainer — for each of Step 4's own fold windows, score every level (not select one) and
read the row of numbers across folds directly for stability.

`step3a_stopout.levels_hops()` now applies each level to a row's `hops_raw` exactly once,
shared by both the full-span sweep table and this one; `fold_metrics()` reruns
`bt.compute_metrics` restricted to each fold's *test* window only, for every level. The
fold boundaries are not recomputed — `outputboard._compute_stopout` reuses the row's own
`GroupResult.folds` from the walk-forward step already run for Step 4, so the windows are
identical to what `Step4_walkforward` already shows. `Step3a_stopout` gained a second
sub-table per eligible row, `fold` x `stop`, with `avg_gain`/`median_gain`/`hit_rate%`/
`chain_annual`/`chain_n`/`Worst`/`N_loss` per cell.

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

**Step 3a (stop-out) built and verified against live data, 2026-08-05.** In place:
`step3a_stopout.py` (`levels_hops`, `metrics_rows`, `sweep`, `fold_metrics`, `best_level`);
the `stop_loss` board column and `stop_sweep`/`stop_annual_tolerance` Settings;
`step3_backtest.run_backtest` applying a row's own stop after `build_hops`; `preflight.py`
requiring `longi_future_minaggr<period>d.csv` when a row's `stop_loss` or the board's
`stop_sweep` calls for it; the `Step3a_stopout` sheet (full-history sweep table + per-fold
stability table, both per eligible row), `Step3_compare` additions and `Charts`' fourth
block; `step3_report`'s `n_stopped` row and stopped-ticker fill. See the two 2026-08-05
refinements above for the design, the risk-first ranking rule, and the fold-stability table.

**Verified against live data (daynum 2205, 2026-08-05):** board regenerated cleanly (no
columns dropped); `--dry-run` clean on all 13 rows; a synthetic unit pass confirmed
`apply_stop`'s benefit/cost decomposition and the unconditional clamp (not
`max(gain, stop)`) on constructed hops; `run_backtest(stop_loss=-10)` and
`sweep(...)[-10]` agreed on every headline metric on the live `A_GICS_rank` row (no forked
path) — `chain_annual`/`chain_n`/`Worst`/`N_loss`/`avg_gain`/`median_gain`/`hit_rate%`/
`n_stopped` all matched exactly; `step3_report`'s Operational sheet rendered the
`n_stopped` row and dark-red stopped-ticker fill correctly. A full development tick with
both live active rows (`A_GICS_rank`, `A_Sector2_rank`, both `stop_loss` off) produced
`chain_annual`=45.54/71.91, matching the pre-change baseline exactly — the off-path is a
provable no-op (`apply_stop` is never called when `stop_loss` is falsy). The fold-stability
table immediately surfaced a real finding: `A_GICS_rank`'s full-history-flagged `-5` level
*underperforms* the unstopped baseline in fold 3 (51.6 vs 56.5) and barely breaks even in
fold 4, despite winning comfortably on the full-history sweep and in the other three
folds — direct, concrete evidence that a full-history "best" stop level is not
automatically fold-stable, which is exactly the question this table exists to answer.






