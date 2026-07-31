#!/usr/bin/env python3
"""
longi_upload.py - publish the longi family's outputs to repositoryRTBI.

Thin on purpose. The ownership declaration, the two guards and the scoped rclone
sync all live in ~/potentials/shared/app/code/repository.py, because "which files
are mine" is a fact about the shared repository, not a fact about longi. See that
module for why a namespace is declared as what this family OWNS rather than as
excludes of everybody else's files - the exclude list this script used to carry
named longi_conf_*.csv but never longi_sectorbeta_*.csv, so those two files were
deleted from Drive on every run for weeks, silently.

Output goes to stdout - start_longi.sh handles logging redirection.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "app" / "code"))
import repository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish longi outputs to repositoryRTBI")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what rclone would transfer and delete, change nothing")
    parser.add_argument("--target", choices=("drive", "mirror"), default="drive")
    args = parser.parse_args()

    return repository.publish(repository.OWNERS["longi"],
                              target=args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
