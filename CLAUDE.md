# Potentials — system root

This is the root of the whole **Potentials** system: several projects that form one daily data
chain, in one git repository. Work that spans projects belongs here; anything project-internal
belongs in that project's own `CLAUDE.md`, which is always the authority for its details.

## Hard rules — non-negotiable, everywhere in this tree

- **Every `python` call goes through SSH.** `ssh -p 2222 sm@innovia.dk`, then
  `conda activate potsystem_env` (`source ~/miniconda3/etc/profile.d/conda.sh` first if the
  shell has no conda). **Python is not installed on the Windows host** — this holds for quick
  one-line checks too.
- **Never pip, never `requirements.txt`.** `potsystem_env` is used as-is.
- **`repositoryRTBI/data/` is read-only to everyone except a producer's own publish.** Producers
  publish their own namespace to Drive *and* directly into the local mirror in one call
  (`repository.py::publish(..., target="both")`, the default) — consumers still only ever read
  the local mirror, never Google Drive directly, and a producer still never touches anyone
  else's files. A producer must never call `sync_rtbi.sh` itself — writing its own namespace
  into `data/` is a publish, not a sync. See [repositoryRTBI/CLAUDE.md](repositoryRTBI/CLAUDE.md).
- **All CSV is European:** `sep=';'`, `decimal=','`. No hardcoded paths — each project has a
  `shared/config.py`.
- **`_archive/` is frozen, and the dependency arrow only ever points out of it.** Files there are
  kept for reference; do not edit them, and **nothing outside `_archive/` may read, import, glob
  or otherwise consume anything inside it** — not code, not config, not a data file, not a report.
  Deleting any folder under `_archive/` must break and stop exactly nothing. A prose mention of a
  retired project is fine; a path into it is not.

## The projects

| Project | Role | Authority |
|---|---|---|
| [repositoryRTBI/](repositoryRTBI/) | **Mirror + API.** Pulls Drive → `data/`, serves it over REST | its `CLAUDE.md` |
| [longi/](longi/) | **Producer.** Per-ticker factor matrices `longi_*.csv`, sector aggregates, forward-gain targets | its `CLAUDE.md` |
| [group_conformity/](group_conformity/) | **Producer.** Conformity/sector-beta grades | its `README.md` |
| [yf3/](yf3/) | **Producer.** yFinance fundamentals | its `CLAUDE.md` |
| [strategy_grp2/](strategy_grp2/) | **The consumer — current work.** One Excel control board drives steps 0-4 | [DesignVersion2.md](strategy_grp2/DesignVersion2.md) |
| [shared/](shared/) | `app/code/repository.py` — the one publish/fetch registry every family uses | the module docstring |
| [_archive/](_archive/) | Retired projects (`strategy/`, `strategy_grp/`), frozen | — |

## The daily chain

Producers publish their **own namespace** to Drive and directly into the local mirror in the
same call, so a consumer sees the output within about a second of publish — not on
`sync_rtbi.sh`'s own next cron tick. Cron on the server (`crontab -l`), hours 0-22:

```
longi :15  →  publish ~:17 (Drive + mirror)  →  group_conformity :45  →  publish ~:47 (Drive + mirror)
```

`sync_rtbi.sh` still runs at `:07/:37/:55`, now for a narrower job: pulling content that
actually originates on Drive (`PotDat.csv` from the G Sheet, `yf3`'s `Yfinance/`, a manual Drive
edit) rather than gating when a registered producer's output becomes visible.

**`strategy_grp2`'s production tick is also cron'd**, separately from the hourly chain above:
`run_production.sh` at 01:00/11:00/19:00 runs `conductor.py --production` — `P`-marked board
rows only, never `D` rows (see `strategy_grp2/DesignVersion2.md`'s 2026-08-13 corrections).
It stops itself if `control_board.xlsx` is open in Excel, exactly as a run fired by hand does.

`~/git_pot.sh` at **03:40** commits and pushes anything left uncommitted in this repo, on the
branch currently checked out — so uncommitted work does not survive the night as a working tree.

**The input repository is a moving target.** Because three unsynchronised jobs rewrite
`repositoryRTBI/data/` all day, a consumer can see a complete set of files from *two different
generations* — which raises nothing and silently produces empty picks. Consumers therefore
preflight and freeze a snapshot before reading (`preflight.py` + `shared/datacheck.py` in
`strategy_grp2`). Do not add a consumer that reads the live directory unguarded.

## Where the lists live

**A new data file has to be declared twice — once by its producer, once by each consumer.** The
two lists are in different projects and neither knows about the other, so a file can be perfectly
published and still be invisible to a run. This has cost real debugging time; check both.

| # | The list | Lives in | Says |
|---|---|---|---|
| 1 | **Ownership / publish namespace** | [shared/app/code/repository.py](shared/app/code/repository.py) → `OWNERS[<family>].owns` | which filename patterns this family is authoritative for. Scopes its `rclone sync`. **Includes only, never excludes** |
| 2 | **Consumer required-files** | each consumer's `app/code/preflight.py` | which files this run needs. Only these are checked for a common vintage and copied into the frozen snapshot the run actually reads |

```bash
python3 shared/app/code/repository.py check          # list 1: both guards, every family
python3 <consumer>/app/code/preflight.py --manifest  # list 2: what this tick will snapshot
```

List 1 is self-enforcing: publishing an output that no pattern covers **fails loudly**. List 2 is
not, and cannot be — a consumer legitimately reads a subset. So the failure mode to expect is
**"the file is in `repositoryRTBI/data/` but the run says it does not exist"**: it was never
requested, so it was never snapshotted. In `strategy_grp2` the request comes from the control
board, not from code — a factor named in `dominance_attribute`, `priority_attribute`,
`informational_attributes`, `post_filter`, or implied by `period`. Anything else needs the step
that consumes it to ask for it.

Adding a *producer* output is a four-list job on the producer side; the checklist is in
[longi/CLAUDE.md](longi/CLAUDE.md), "Adding New Modules to Pipeline" step 4.

## System-wide conventions

- **Matrix files:** rows = tickers, columns = daynums as **strings**, **newest left**. Look up
  with `df[str(daynum)]`, never a bare int. `Cal.csv` maps daynum → date (index is float).
- **The "seven-pack" horizons:** 1 / 5 / 10 / 20 / 50 / 100 / 200 trading days, for both
  trailing (`longi_per*`) and forward (`longi_future_per*`) families. 20 is the primary.
- **Entry is signal+1.** The signal day's close is what the decision is made on, so it is not
  tradeable. Everything measured before the 2026-07-31 cutover assumed same-day entry and is
  **not comparable** to anything after it.
- **Returns are additive**, not compounded — a chain's return is the sum of its lot gains, and
  the "annual" figures are that sum ÷ span-years, not a CAGR.
- **`longi_grp_*` and `longi_future_*` are not per-ticker features.** The former are sector
  rows; the latter are the answer. The prefix skip-guards that keep them out of joined feature
  sets are load-bearing — removing one leaks look-ahead.

## Naming discipline

Three *attribute* roles run through the strategy projects — **dominance** (which groups get
elevated), **priority** (how survivors are ranked) and **informational** (reported only) — plus
`group_column`/`group_expression`, which is a **Stamdata column, not an attribute**. Conflating
them has broken this system before. Confirm the exact name against the project's config before
editing it.
