# Strategy_grp2 — Context for Claude Code

Version 2 of `../strategy_grp/` (v1, still live during development — see there for its own
CLAUDE.md). **The spec is [`DesignVersion2.md`](DesignVersion2.md) — read it before working
on this project.** It is the one living design document; this file is only the entry card
Claude Code auto-loads and does not duplicate anything DesignVersion2.md already says.

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
    └── report/          # output boards, per-run detail, StrategicStocks.xlsx
```

## Running

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env
cd ~/potentials/strategy_grp2/app/code

python conductor.py --make-board   # write/refresh the control board from the schema
python conductor.py --dry-run      # validate every board row; touches no data
python conductor.py                # development tick (steps 0-4)
python conductor.py --production   # production tick (steps 0-2) -> StrategicStocks.xlsx
```

## Status

Full pipeline (steps 0-4) built and verified end-to-end, including the output board with
charts — see DesignVersion2.md's "Status" section for what is built vs. pending.
