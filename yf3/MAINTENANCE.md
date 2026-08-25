# yf3 Maintenance Notes

## 2026-08-24 — Evening fetch window (22:xx) trialed alongside the night one (02:xx)

**Why:** the 02:25 fetch sits right on top of several exchange opens (ASX opens exactly
00:00 Danish winter / 02:00 summer; HK/SS open ~02:30 Danish winter) -- a few minutes'
timing drift can flip a ticker between "market open (day D)" and "market still closed
(day D-1)" run to run. This is the mixed-trading-day symptom visible in
`makeYfinanceSnapshot.py`'s output. 02:25 was originally picked because pre-midnight
yFinance traffic used to be unstable; SM believes that's since improved and wants to
verify with a real trial rather than assume.

**What changed:**
- `stackYfinanceData.py`'s `add_daynum_date()` now branches on `FetchedDate`'s local hour
  (`EVENING_HOUR = 12`): night-window fetches (hour < 12) keep the existing per-suffix/
  seasonal D vs D-1 table; evening-window fetches (hour >= 12) use basis = D for every
  suffix, since by ~22:25 Danish every exchange in scope (US, EU, and all the Asia/Pacific
  suffixes) has already closed for the day -- no per-suffix or seasonal split needed.
  Verified with a synthetic dry run across `.AX`/`.HK`/`.SI`(both seasons)/no-suffix before
  deploying.
- `yf3_wrapper.sh`: `TARGET_HOURS=(02 22)` -- reusing the same array mechanism previously
  used to trial `(02 08 15)` before settling on `(02)`.
- Crontab: `25 0-15 * * *` widened to `25 0-15,22 * * *` (same script, same minute --
  fires Danish ~22:25, inside SM's stated 22:30-23:30 acceptable window).

**Does 02:25 cover for a failed 22:25 run?** Yes for the bulk of tickers (US no-suffix, EU,
`.HK`, `.SS`, `.JO`) -- both windows resolve to the same Daynum for these, and `yf3.py`
always does a full re-fetch, so a failed evening run is transparently backfilled by the
next night run. Not for `.AX`/`.T`/`.KS` (and `.SI` in Danish winter) -- these target
genuinely different sessions (evening = day D, night = day D+1), so a failed evening run
just means that day's extra data point is missing, not a regression vs. today's
single-run baseline.

**Known consequence during the trial:** for tickers where both windows converge on the
same Daynum, `dedupe()`'s latest-FetchedDate-wins rule means the following night's run
supersedes the evening run's row in the *merged* stacked file before the two can be
compared there. Compare via the untouched per-run files in `app/output/`
(`StockData2-<date>-2225.csv` vs `StockData2-<date>-0225.csv`) and their
`Failed_stocks_*.txt` companions instead.

**PENDING:** this is a trial, not a decision. Once SM has watched the evening run for a
while, one window will be dropped (remove its hour from `TARGET_HOURS` and narrow the
crontab range back down) -- nothing here automates that call.

## 2026-08-24 — Wrapper script relocated/renamed to match other Potentials families

yf3 is the oldest family and had drifted from the layout the newer families (longi,
strategy_grp2, group_conformity, ...) settled on: its cron wrapper lived loose in
`/home/sm/` instead of under `~/potentials/<family>/`, and its logs wrote to `/home/sm/`
instead of `~/logs/`. Straightened out before making cron-timing changes, so a later
timing bug can't be conflated with this relocation.

- `/home/sm/time_wrapper.sh` → `~/potentials/yf3/yf3_wrapper.sh` (moved into the repo,
  git-tracked from now on). All internal self-references (`echo` messages) renamed
  to match.
- Logs moved from `/home/sm/` to `~/logs/`, history preserved via `mv`:
  `time_wrapper.log` → `yf3_wrapper.log`, `updgd_yf3.log` → `updgd_yf3.log`,
  `yf3_timing_results.log` → `yf3_timing_results.log`. `start_yf3.log` was already
  correctly under `~/logs/` (its `LOGFILE` var predates this cleanup); `updgd_yf3.sh`'s
  `LOGFILE` was corrected to point at `~/logs/updgd_yf3.log`.
- Crontab line updated: `25 0-15 * * * /bin/bash /home/sm/time_wrapper.sh` →
  `25 0-15 * * * /bin/bash /home/sm/potentials/yf3/yf3_wrapper.sh`. Timing itself
  (`TARGET_HOURS=(02)`, `0-15` cron range) untouched in this pass.
- No crontab-level `>> log 2>&1` redirect was added (unlike e.g. `run_production_cron.log`)
  — the wrapper already self-redirects everything internally via `exec`/`{ } >> $LOGFILE`,
  so a second redirect would just duplicate the same content under a different name.

## 2026-07-01 — Trading-day index on the stacked file + PotDatML snapshot

**Nightly chain (`start_yf3.sh`):** fetch (`yf3.py`) → stack (`stackYfinanceData.py`) →
snapshot (`makeYfinanceSnapshot.py`). `updgd_yf3.sh` then uploads `app/output_stacked/`
to Drive `PotSystem/repositoryRTBI/Yfinance/` (excludes `.stack_ledger.json`). The daily
`StockData2-*.csv` files are no longer uploaded to Drive — the whole `~/potentials` tree
is backed up to Asustor.

**`stackYfinanceData.py` — Daynum/Date index + dedup.** Each row gets `Daynum` and `Date`
(from `input/Cal.csv`) inserted after `Symbol`; the raw `FetchedDate` is kept. Downstream
index is `(Symbol, Daynum)`; duplicates on that key are collapsed keeping the most recent
FetchedDate.
- Both FetchedDate formats are parsed (`DD-MM-YYYY HH:MM` and ISO).
- **Exchange day-shift** (only valid for the 02:15–02:35 Danish fetch window): whether a
  fetch reflects date D depends on whether the ticker's market has opened by ~02:35.
  `.AX .T .KS` → D (open both seasons); `.HK .SS` and everything else (US no-suffix, EU,
  `.JO`) → D−1; `.SI` → D in Danish winter, D−1 in summer (EU DST via
  `zoneinfo("Europe/Copenhagen")`). The basis date is then backfilled to the most recent
  Cal.csv trading day ≤ basis (also folds weekend/holiday fetches).
- **Idempotent** via a filename ledger `output_stacked/.stack_ledger.json` (not the raw
  FetchedDate, which dedup discards). Re-running with no new source files is a no-op. A
  legacy stacked file without Daynum/Date is migrated on the next run.

**`makeYfinanceSnapshot.py` — `Yfinance.csv`.** One row per ticker at its most-recent
Daynum (robust to fetch gaps), columns `Ticker;Daynum;Target_*;Recommendation_*;
NumberOfAnalysts`. Imported by the **PotDatML** Google Sheet, then `importRange`'d onward.
The `COLUMNS` constant is the single place to route additional fields the same way.
Note: yFinance is a weak source for long-term history — this snapshot is a "today's
picture" companion to PotRank, not a longterm store.

## 2026-06-08 — Improved logging for failed tickers

**Problem:** HTTP 404 errors and failed-ticker messages were buried mid-run among 1000+ `Processing N/N:` lines. The end-of-run summary only said `Failed: N stocks` without naming them (gated on `VERBOSE = True`, which was `False`).

**Changes in `app/code/yf3.py`:**
- Suppressed yfinance's raw `HTTP Error 404: {JSON}` noise via `logging.getLogger('yfinance').setLevel(logging.CRITICAL)`
- Always print failed tickers at end of run (removed `VERBOSE` gate)
- Tickers failing with "Insufficient data" / "No valid data" (i.e. 404 — ticker not found on Yahoo) are now flagged `*** POSSIBLY OBSOLETE / DELISTED ***`
- Failed stocks log file (`Failed_stocks_YYYYMMDD-HHMM.txt`) is now always written to `output/`, not only when `VERBOSE = True`

**Background:** GBRK and similar tickers were causing repeated 404 errors every run. The log gave no clear signal that these needed to be reviewed and removed from the ticker list.
