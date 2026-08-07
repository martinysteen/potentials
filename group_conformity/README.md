# Group Conformity Project

Grades how closely each ticker tracks its own GICS/Sector2 group, and tests whether
low-conformity members are where extreme forward gains come from — motivated by
`strategy_grp`'s GICS-domination strategy family (v1, archived 2026-08-07 to
`../_archive/strategy_grp/`; its successor is `../strategy_grp2`).

Split out of `../correlation` on 2026-07-29 into its own project: a different question, a
different (smaller) input subset, and worth a proper git-tracked home rather than sharing space
with `../correlation`'s older, now-archived/gitignored task 1–3 scripts.

## Project Structure
- **`code/`**: Python scripts for the conformity grade and the gain-dispersion verdict.
- **`input/`**: Raw CSV data files (European format: `;` separator, `,` decimal), fetched by
  `fetch_input.sh`.
- **`output/`**: Generated CSV grades, controls, rankings, and verdict tables.
- **`docs/`**: Detailed documentation and walkthrough.

## Analysis

### Group Conformity Grader
Grades each ticker's conformity to its GICS/Sector2 group, then tests whether low-conformity
members carry more dispersion in forward gain.
- **Scripts**: `code/analyze_conformity.py`, `code/analyze_conformity_gains.py`
- **Outputs**: `longi_conf_{GICS,Sector2}.csv`, `longi_sectorbeta_{GICS,Sector2}.csv`,
  `conformity_controls.csv`, `conformity_ranking_{GICS,Sector2}.csv`, `conformity_vs_gain.csv`,
  `conformity_vs_gain_hop_secondary.csv`
- **Central storage**: `code/conformity_upload.py` pushes the four Longi-shaped matrices to
  `GoogleDrive:PotSystem/repositoryRTBI/Longi` via the shared registry
  (`~/potentials/shared/app/code/repository.py`), scoped to this family's own namespace so it
  cannot touch longi's files in the same folder (see `docs/1_group_conformity.md`).
- **Documentation**: [docs/1_group_conformity.md](docs/1_group_conformity.md)

## Usage
```bash
ssh -p 2222 sm@innovia.dk
conda activate potsystem_env

# Full pipeline (fetch -> produce -> publish), this is what's cron'ed (:45, see docs):
bash ~/potentials/group_conformity/run_conf.sh

# Or step by step:
bash ~/potentials/group_conformity/fetch_input.sh
cd ~/potentials/group_conformity/app/code
python analyze_conformity.py
python analyze_conformity_gains.py
python conformity_upload.py   # push the grade matrices centrally
```

## Requirements
- Python 3.x, `potsystem_env` conda environment (Pandas, NumPy — never pip/requirements.txt)
