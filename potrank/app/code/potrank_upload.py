#!/usr/bin/env python3
"""
potrank_upload.py - publish potrank2.csv to repositoryRTBI.

Thin on purpose: the ownership declaration (`/potrank2.csv`, subdir="" — repository root,
beside Stamdata.csv/Cal.csv/PotDat.csv), the two guards, and the scoped rclone sync live in
~/potentials/shared/app/code/repository.py. Modelled on
group_conformity/app/code/conformity_upload.py.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "app" / "code"))
import repository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish potrank2.csv to repositoryRTBI")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what rclone would transfer and delete, change nothing")
    parser.add_argument("--target", choices=("drive", "mirror", "both"), default="both")
    args = parser.parse_args()

    return repository.publish(repository.OWNERS["potrank"],
                              target=args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
