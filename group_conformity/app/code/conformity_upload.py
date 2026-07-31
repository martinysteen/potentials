#!/usr/bin/env python3
"""
conformity_upload.py - Upload the group-conformity Longi factor files to the
central repositoryRTBI/Longi store on Google Drive, so ../strategy_grp can
read them via the normal load_longi() path if/when it wires longi_conf_* in
as a filter. (../strategy was archived 2026-07-31, no further work planned.)

Deliberately narrow: only the four Longi-shaped matrices (longi_conf_*,
longi_sectorbeta_*) go here. conformity_ranking_*.csv, conformity_controls.csv
and conformity_vs_gain*.csv are analysis/report byproducts, not factor data —
wrong shape for this folder's contract (every consumer expects ticker x daynum)
and cheaply reproducible by rerunning analyze_conformity*.py, so they stay local.

Uses 'rclone copy --update' on purpose, not 'sync': the destination
(GoogleDrive:PotSystem/repositoryRTBI/Longi) is shared production data this
project does not own outright — 'sync' deletes anything at the destination
that isn't in the (filtered) source, the wrong failure mode here. 'copy
--update' only ever adds or refreshes the four named files.
"""
import subprocess
import sys
from pathlib import Path

SOURCE = Path("/home/sm/potentials/group_conformity/app/output")
DESTINATION = "GoogleDrive:PotSystem/repositoryRTBI/Longi"
FILES = [
    "longi_conf_GICS.csv",
    "longi_conf_Sector2.csv",
    "longi_sectorbeta_GICS.csv",
    "longi_sectorbeta_Sector2.csv",
]


def main() -> int:
    missing = [f for f in FILES if not (SOURCE / f).exists()]
    if missing:
        print(f"ERROR: missing source file(s), run analyze_conformity.py first: {missing}")
        return 1

    include_flags = []
    for f in FILES:
        include_flags += ["--include", f]

    cmd = [
        "rclone", "copy", str(SOURCE), DESTINATION,
        "--update", "--drive-skip-gdocs", "--verbose",
    ] + include_flags

    print(f"Uploading {len(FILES)} file(s) from {SOURCE} to {DESTINATION}")
    print(f"  Files: {FILES}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        print("ERROR: rclone command not found. Is rclone installed?")
        return 127

    if result.stdout:
        print(result.stdout, end="")

    if result.returncode == 0:
        print("SUCCESS: conformity factor files uploaded")
    else:
        print(f"ERROR: rclone failed with exit code {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
