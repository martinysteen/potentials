# Design note — replacing cron timing with a conductor (PROPOSAL, nothing built)

Status: proposal, 2026-10-21. **No action decided.** SM wants to wait until the Sheet side is
simpler (importRange criss-crossing and triggered Apps Script exports are to be removed
gradually, Sheets becoming display-only). This note is written so that migration does not
invalidate it: the conductor depends on one small input contract, not on how the file is made.

## 1. Why — what 2026-10-21 showed

The daily chain is coordinated by **clock minutes**: each job assumes the previous one is done
"by now". Three failures in one afternoon were all that same assumption breaking:

| Time | What happened | Which assumption broke |
|---|---|---|
| 16:11 | Apps Script `FetchAndExportPotDat` died (Google `INTERNAL`) | "a new PotDat arrives every hour" |
| 16:15 / 17:15 | longi ran on the 15:11 file (stamp before the US open → US tickers *carried*, RSI = yesterday) | "the sync at :07/:37 has caught the newest file" |
| 17:17 → 18:24 | Drive upload stalled 6 min on one file; the mirror leg waits on the Drive leg | "publish takes seconds" |
| 18:14 | the `:14` sync added that day missed an upstream file that finished at ~18:34 | "upstream finishes by :13" |

Every patch so far moves a contact by a minute. A late or failed step cannot be *seen* by its
dependents; they run on stale data instead of waiting or stopping.

## 2. Principle

**Events and done-markers instead of clock minutes.** A step runs when its input *generation*
exists and its predecessors are *done for that generation*; it never guesses. Late upstream means
a late chain, not a wrong one. Failure means a stopped branch plus one mail, not a silent stale run.

Unchanged hard rules: consumers read only the local mirror; a producer publishes only its own
namespace (`repository.py::publish`); producers still never trigger each other — the conductor
does it from outside. `datacheck`/`preflight` and the PotDat gatekeeper stay exactly as they are.

## 3. The input contract (what survives the Sheet migration)

A **generation** = one complete `PotDat.csv` identified by the creation stamp in cell A1
(`DD-MM-YYYY HH-MM`, already used by the gatekeeper). Contract: *complete file (passes
`looks_intact`), stamp strictly newer than the last generation processed.* Who produces it —
today the Sheet's Apps Script, later possibly a server job — is irrelevant to the conductor.
Only the **trigger source** changes (Drive poll today; local file watch if the server one day
writes it itself).

## 4. Shape

One script, `shared/app/code/conductor.py`, started by cron **every minute** under `flock`
(cron stays only as the heartbeat that starts the conductor — it is a poll, not a schedule).

```
poll Drive metadata of PotDat.csv  (one cheap call; modtime/size changed?)
  └─ changed → sync that file to the mirror → read A1 → new generation g?
        └─ yes → run the DAG for g
```

DAG for one generation (edges = "needs done-marker of"):

```
fetch(g) → longi(g) ─┬→ group_conformity(g)
                     ├→ potrank(g)
                     └→ strategy_grp2 production(g)  (also needs potrank, conformity per its board)
yf3 (daily 22:25) and tunnel (00:00) stay clock jobs: they are time-of-day by nature.
```

Markers: `~/.local/state/potentials/conductor/<g>/<step>.{running,done,failed}` (JSON: start, end,
exit code, log path). Every step has a **timeout** (the 6-minute stall becomes a killed step and a
retry), a bounded **retry** count, and on final failure its dependents are marked `skipped`
and **one mail** is sent. Steps are the existing scripts run as today (`start_longi.sh`, …), so
they remain runnable by hand; the conductor only decides *when*.

Gaps: if no new generation appears for N minutes inside market hours, the conductor mails
(the watchdog already does this on the clock — see §6).

## 5. Migration — gradual, each phase reversible

0. **Shadow mode.** Conductor runs alongside cron, only *logs* what it would trigger and compares
   with what cron actually did. Zero risk; shows how often the two disagree (that count is the
   case for going further).
1. **Take over longi only.** Remove cron `:15`, drop the `:07/:14/:37/:55` syncs' role for PotDat.
2. **Take over the downstream chain** (conformity, potrank, production), one at a time.
3. Remove the obsolete cron lines; keep `yf3`, `tunnel`, `git_pot.sh`, backups on cron.

Rollback at any phase: restore the saved crontab (`crontab ~/crontab.bak.<date>`); the markers
are inert files. Nothing in the data model changes.

## 6. Relation to the watchdog (built 2026-10-21)

`watchdog.py` stays **clock-based and independent** — an observer must not depend on the thing
it observes, and the conductor itself needs watching (a dead conductor looks like "no new
generation"). Once the conductor exists, the watchdog's `longi_stamp` check can tighten from
"100 min behind" to "behind the last generation by more than one step's timeout".

## 7. Risks

- **Single coordinator.** Mitigated by §6 plus `flock`, plus phase 0–1 keeping cron as fallback.
- **Drive API quota.** Rate limits are already real (`rateLimitExceeded` at 18:45 today, 71
  historical lines in `longi_cron.log`). A once-a-minute metadata poll is ~1,400 calls/day;
  fine, but must back off on a 403/429 and never fall back to a full listing.
- **Upstream stamps a new minute on an unchanged file** (the file is rewritten hourly even if
  nothing changed). A generation is therefore "new stamp", not "new content".
- **Provisional newest column.** Not affected: carry logic is per generation and stays in the
  gatekeeper; but hourly generations still mean US rows are carried until the first post-open file.

## 8. Open points (decide when the Sheet side settles)

1. Which Sheet→Drive exports and importRange links remain, and which other server outputs the
   Sheets still read — an inventory is the prerequisite for retiring any cron line.
2. Does `potrank` stay hourly-on-generation, or also run when only Stamdata/yf3 changes?
3. Should `strategy_grp2`'s 8–23 production tick (twice an hour) become per-generation, or keep a
   half-hour clock for its non-PotDat inputs?
