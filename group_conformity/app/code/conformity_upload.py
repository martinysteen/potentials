#!/usr/bin/env python3
"""
conformity_upload.py - publish the group-conformity factor files to repositoryRTBI.

Thin on purpose: the ownership declaration (longi_conf_*, longi_sectorbeta_*),
the two guards and the scoped rclone sync live in
~/potentials/shared/app/code/repository.py.

This script used to run `rclone copy --update` rather than `sync`, on the grounds
that the destination is shared data this project does not own outright - true,
but the cost was that a retired output could never be cleaned up. Scoping the
sync to this family's own patterns gets both: authoritative over these four
files, blind to every other file in the folder.

The analysis byproducts (conformity_ranking_*.csv, conformity_controls.csv,
conformity_vs_gain*.csv) stay local, declared as local_only in the registry -
wrong shape for a folder whose every consumer expects ticker x daynum, and
cheaply reproducible by rerunning analyze_conformity*.py.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "app" / "code"))
import repository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish group_conformity factor files to repositoryRTBI")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what rclone would transfer and delete, change nothing")
    parser.add_argument("--target", choices=("drive", "mirror"), default="drive")
    args = parser.parse_args()

    return repository.publish(repository.OWNERS["group_conformity"],
                              target=args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
