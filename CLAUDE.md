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
- **`repositoryRTBI/data/` is read-only to everyone except the mirror.** Producers publish to
  Drive and stop; consumers read the local mirror and never Google Drive directly. A producer
  must never call `sync_rtbi.sh`. See [repositoryRTBI/CLAUDE.md](repositoryRTBI/CLAUDE.md).
- **All CSV is European:** `sep=';'`, `decimal=','`. No hardcoded paths — each project has a
  `shared/config.py`.
- **`_archive/` is frozen.** Files there are kept for reference; do not edit them.

## The projects

| Project | Role | Authority |
|---|---|---|
| [repositoryRTBI/](repositoryRTBI/) | **Mirror + API.** Pulls Drive → `data/`, serves it over REST | its `CLAUDE.md` |
| [longi/](longi/) | **Producer.** Per-ticker factor matrices `longi_*.csv`, sector aggregates, forward-gain targets | its `CLAUDE.md` |
| [group_conformity/](group_conformity/) | **Producer.** Conformity/sector-beta grades | its `README.md` |
| [yf3/](yf3/) | **Producer.** yFinance fundamentals | its `CLAUDE.md` |
| [strategy_grp/](strategy_grp/) | **Consumer, v1.** `Dom*` strategy families, sweep + walk-forward. Live until v2 takes over | its `CLAUDE.md` |
| [strategy_grp2/](strategy_grp2/) | **Consumer, v2 — current work.** One Excel control board drives steps 0-4 | [DesignVersion2.md](strategy_grp2/DesignVersion2.md) |
| [shared/](shared/) | `app/code/repository.py` — the one publish/fetch registry every family uses | the module docstring |
| [_archive/](_archive/) | Retired projects, frozen | — |

## The daily chain

Producers publish their **own namespace** to Drive; the mirror pulls on its own schedule;
consumers read the mirror. Cron on the server (`crontab -l`), hours 0-22:

```
longi :15  →  publish ~:17  →  mirror :37  →  group_conformity :45  →  publish ~:47  →  mirror :55
                                  ↑ also :07
```

`~/git_pot.sh` at **03:40** commits and pushes anything left uncommitted in this repo, on the
branch currently checked out — so uncommitted work does not survive the night as a working tree.

**The input repository is a moving target.** Because three unsynchronised jobs rewrite
`repositoryRTBI/data/` all day, a consumer can see a complete set of files from *two different
generations* — which raises nothing and silently produces empty picks. Consumers therefore
preflight and freeze a snapshot before reading (`preflight.py` + `shared/datacheck.py` in both
strategy projects). Do not add a consumer that reads the live directory unguarded.

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
