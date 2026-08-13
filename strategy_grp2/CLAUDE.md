# Strategy_grp2 — Context for Claude Code

Version 2 of `strategy_grp`, and now the system's only strategy consumer — **v1 was retired on
2026-08-07 to `_archive/`, frozen, no further work.**
The "strategy_grp v1" mentions through this project's code and docs are **provenance notes, not
pointers** — `_archive/` may be deleted at any time, so nothing here reads from it, and no comment
requires it to still exist to be understood (see the root CLAUDE.md hard rule). **The spec is [`DesignVersion2.md`](DesignVersion2.md)
— read it before working on this project.** It is the one living design document; this file is
only the entry card Claude Code auto-loads and does not duplicate anything DesignVersion2.md
already says.

## Hard rules — non-negotiable

- **Every `python` call goes through SSH, no exceptions:** `ssh -p 2222 sm@innovia.dk`, then
  `conda activate potsystem_env`. Never invoke python directly on the Windows host — it is
  not installed there.
- **Never pip / requirements.txt.** Use the `potsystem_env` conda env as-is.
- **`repositoryRTBI/` is read-only.** Strategy code never writes to it; `app/data/` is scratch.
- **A run reads the frozen snapshot in `app/data/input/`, not the mirror.** Only files
  `preflight.required_files_for_rows()` asked for are in it, so a file that exists in
  `repositoryRTBI/data/` can still be missing from a run. It is requested by being *named on the
  board* — `dominance_attribute`, `priority_attribute`, `informational_attributes`, `post_filter`,
  or implied by `period`. `python preflight.py --manifest` prints what this tick will snapshot.
- **European CSV format:** `sep=';', decimal=','`. No hardcoded paths — use `shared/config.py`.
- **The control board (`app/control/control_board.xlsx`) is never written by the processor**
  while a tick runs — see DesignVersion2.md's input/output separation principle.
- **Every entry point stops (exit 2) if the board is open in Excel**, detected via Excel's
  `~$control_board.xlsx` owner file — the closest thing to VBA's `Saved` flag that is
  visible from the server. `--board-open-ok` overrides.

## Directory map

```
strategy_grp2/
├── CLAUDE.md            # this file
├── DesignVersion2.md    # THE spec
└── app/
    ├── control/         # control_board.xlsx (input)
    ├── code/            # conductor.py + step0-4 + shared/
    └── report/          # output boards, per-run detail, StrategicStocks_<daynum>.xlsx/.csv
```

`StrategicStocks_<daynum>.csv` is published to `GoogleDrive:PotSystem/repositoryRTBI/Strategy`
immediately after being written, via the shared repositoryRTBI publish contract
(`~/potentials/shared/app/code/repository.py`'s `OWNERS["strategy_grp2"]`) — the local mirror
(`~/potentials/repositoryRTBI/data/Strategy/`) picks it up on its own cron, no strategy_grp2 code
involved in that half.

## Running

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env
cd ~/potentials/strategy_grp2/app/code

python conductor.py --make-board   # write/refresh the control board from the schema
python conductor.py --dry-run      # validate every board row; touches no data
python conductor.py                # development tick (steps 0-4) for every row marked `D` -> compare_strategies_<date>.xlsx ONLY
python conductor.py --production   # fast path (steps 0-2 only) for every row marked `P` -> StrategicStocks_<daynum>.xlsx/.csv
```

**`D` and `P` are two independent board columns** (2026-08-13, replacing one `active`
column) — a row marked `D` for development work never appears in a `--production` run,
cron-fired or otherwise, unless `P` is marked on it too. And **StrategicStocks is written and
Drive-published by `--production` only**, never by a bare development tick — that file is what
real users read as the day's advice, and a development tick is exactly where wild trial rows
live. Both are 2026-08-13 corrections, reversing the 2026-08-12 "every active row ships in one
invocation" decision in two steps. See DesignVersion2.md's 2026-08-13 corrections.

## Status

Full pipeline (steps 0-4) built and verified end-to-end, including the output board with
charts — see DesignVersion2.md's "Status" section for what is built vs. pending.
