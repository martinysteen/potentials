#!/usr/bin/env python3
"""
repository.py - the repositoryRTBI contract: who owns which files, where a family
publishes, and where a family reads its input from.

Three layers, and nothing crosses
---------------------------------
  PRODUCERS   (longi, group_conformity, ...) compute, then publish THEIR OWN
              namespace and nothing else. They never pull, and they never trigger
              anything downstream.
  MIRROR      repositoryRTBI/sync_rtbi.sh pulls Google Drive -> data/ on its own
              schedule, for its own reasons. If it wants fresher data it changes
              its own cron; that is not a producer's business.
  CONSUMERS   read the local mirror. Never Google Drive. The mirror is the single
              authoritative copy on this machine, so "complete" and "up to date"
              are properties it has to certify - see mirror_status().

A family is both: it fetches from the mirror (consumer) and publishes its own
outputs (producer). It is never allowed to be the mirror.

Why ownership is declared, and declared as INCLUDES
---------------------------------------------------
Several families publish into the SAME flat destination (repositoryRTBI/Longi).
`rclone sync` makes a destination identical to its source, so two producers
syncing the same folder delete each other's files. The historical fix was an
exclude list in each uploader - which requires every family to know every other
family's filenames. That is n^2 edits, and each forgotten one fails silently:
longi's uploader excluded `longi_conf_*.csv` but nobody added
`longi_sectorbeta_*.csv` when that pair was born, so those two files were deleted
at :20 and restored at :31, every hour, for weeks. Nothing raised.

So the polarity is inverted here. Each owner declares only what it OWNS, and the
sync is scoped to those patterns with an rclone filter. Scoped that way, sync is
authoritative INSIDE the namespace - it still deletes the owner's own retired
outputs, which is what stops dead debris accumulating - and completely blind
outside it. Adding a family means adding one entry below and editing nobody
else's code.

Two guards keep the declaration honest, because a namespace nobody checks is just
a comment:

  * every file a family produces must match its own patterns, or be listed in
    `local_only`. A new output that no pattern covers fails the publish loudly
    instead of silently never appearing. This is the guard that would have caught
    longi_sectorbeta_* on the day it was born.
  * no file may be claimed by two owners. Checked against real files, not by
    reasoning about glob overlap, so it catches the collision the moment a new
    family produces its first output.

Deliberately out of scope: yf3
------------------------------
`yf3/updgd_yf3.sh` also drops files into this repository (`Yfinance/`) with `rclone
copy`, but yf3 is otherwise an isolated pipeline that publishes its real output to a
Google Sheet by a route of its own. It is the sole owner of that subfolder and `copy`
never deletes, so it cannot collide with anything here. Left unregistered on purpose -
not an oversight. The collision guard only compares owners sharing a `subdir`, so its
absence costs nothing.

Pattern language
----------------
Deliberately tiny - two forms only, both anchored at the top of the source dir,
because these are handed straight to rclone as `--filter` rules and must mean the
same thing here as they do there:

    /name-glob      a file at the top level, e.g. "/longi_per*.csv"
    /dirname/**     that subtree entire,      e.g. "/QA/**"

Unanchored patterns are rejected: rclone matches a bare `longi_x.csv` at ANY
depth, which would quietly pull subfolder files into a namespace.

CLI
---
    python3 repository.py check                 registry self-check, all owners
    python3 repository.py publish <owner> [--dry-run] [--target drive|mirror]
    python3 repository.py fetch   <owner> [--stale-ok] [--max-age-min N]

`--target mirror` publishes into the local mirror instead of Drive. Nothing uses
it yet; it exists so that reversing the dataflow later (family -> Gandalf repos
-> Drive, rather than family -> Drive -> Gandalf repos) is a flag, not a rewrite.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

POTENTIALS = Path("/home/sm/potentials")
DRIVE_ROOT = "GoogleDrive:PotSystem/repositoryRTBI"
MIRROR_ROOT = POTENTIALS / "repositoryRTBI" / "data"

# Written by sync_rtbi.sh AFTER a sync completes. Deliberately outside data/:
# anything inside data/ that Drive does not have is deleted by the next sync.
MIRROR_STATUS = POTENTIALS / "repositoryRTBI" / "mirror_status.json"

# The mirror refreshes twice an hour (:07/:37). 90 minutes tolerates one missed
# tick without tolerating a mirror that has actually stopped.
DEFAULT_MAX_AGE_MIN = 90


@dataclass(frozen=True)
class Owner:
    """One family's half of the contract: what it reads, what it owns."""

    name: str
    source: Path                       # where its outputs land
    input_dir: Path                    # where fetch() puts its inputs
    subdir: str                        # destination subfolder ("" = repository root)
    owns: tuple[str, ...]              # patterns this family is authoritative for
    needs: tuple[str, ...] = ()        # repository-relative paths it reads
    local_only: tuple[str, ...] = ()   # produced on purpose, published on purpose not


OWNERS: dict[str, Owner] = {
    "longi": Owner(
        name="longi",
        source=POTENTIALS / "longi" / "app" / "output",
        input_dir=POTENTIALS / "longi" / "app" / "input",
        subdir="Longi",
        owns=(
            "/across_*.csv",
            "/longi_PdivMA*.csv",
            "/longi_beta*.csv",
            "/longi_coreindex*.csv",
            "/longi_future_minaggr*.csv",
            "/longi_future_per*.csv",
            "/longi_grp_*.csv",
            "/longi_iran.csv",
            "/longi_ma*.csv",          # also covers longi_macd_*
            "/longi_median_*.csv",
            "/longi_per*.csv",
            "/longi_price.csv",
            "/longi_quot*.csv",
            "/longi_rank.csv",
            "/longi_rsi.csv",
            "/longi_sh*.csv",
            "/longi_spr*.csv",
            "/longi_stepup*.csv",
            "/longi_trump.csv",
            "/longi_vola*.csv",
            "/QA/**",
            "/exp/**",
        ),
        needs=("PotDat.csv", "Stamdata.csv", "Cal.csv"),
        local_only=("*.txt",),
    ),
    "group_conformity": Owner(
        name="group_conformity",
        source=POTENTIALS / "group_conformity" / "app" / "output",
        input_dir=POTENTIALS / "group_conformity" / "app" / "input",
        subdir="Longi",
        owns=(
            "/longi_conf_*.csv",
            "/longi_sectorbeta_*.csv",
        ),
        needs=(
            "Stamdata.csv",
            "Longi/longi_per1d.csv",
            "Longi/longi_grp_GICS_per1d.csv",
            "Longi/longi_grp_Sector2_per1d.csv",
            "Longi/longi_vola100d.csv",
            "Longi/longi_future_per20d.csv",
            "Longi/longi_future_per50d.csv",
        ),
        # Analysis byproducts: wrong shape for a folder whose every consumer
        # expects ticker x daynum, and cheaply reproducible by rerunning the
        # analyzer. They stay local on purpose.
        local_only=("conformity_*.csv", "conformity_*.xlsx", "*.xlsx.csv"),
    ),
    "strategy_grp2": Owner(
        name="strategy_grp2",
        source=POTENTIALS / "strategy_grp2" / "app" / "report",
        input_dir=POTENTIALS / "strategy_grp2" / "app" / "data" / "input",
        subdir="Strategy",
        # Only the daily gross-list CSV is published -- the rest of app/report/ is
        # human-facing Excel workbooks, per-run detail, and local archives, none of
        # which belong outside this machine.
        owns=(
            "/StrategicStocks_*.csv",
        ),
        local_only=(
            "*.xlsx",           # StrategicStocks_*.xlsx, compare_strategies_*.xlsx, Excel's own ~$ lock file
            "*.cmd",            # strategy_grp2.cmd (renamed from run.cmd, 2026-08-13)
            "*.lnk",            # control_board.lnk
            "picks_*.csv",      # dev-tick only (DesignVersion2.md), never Drive-published
            "backtesting/**",
            "walkforward/**",
            "_archive/**",
        ),
    ),
}


# --------------------------------------------------------------------------- #
# pattern matching                                                            #
# --------------------------------------------------------------------------- #

def _check_pattern(pattern: str) -> None:
    if not pattern.startswith("/"):
        raise ValueError(
            f"pattern {pattern!r} is not anchored: rclone matches an unanchored "
            f"name at any depth, so write '/{pattern}' or '/dir/**'")


def matches(pattern: str, rel: str) -> bool:
    """Does repository-relative path `rel` fall inside `pattern`?

    Mirrors the two forms documented in the module docstring, and nothing more -
    if this ever needs to grow, grow rclone's side in step or the guards start
    disagreeing with the transfer they are guarding.
    """
    _check_pattern(pattern)
    body = pattern[1:]
    if body.endswith("/**"):
        return rel.startswith(body[:-2])
    return "/" not in rel and fnmatch.fnmatch(rel, body)


def _relative_files(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file())


def claims(owner: Owner, rel: str) -> bool:
    return any(matches(p, rel) for p in owner.owns)


# --------------------------------------------------------------------------- #
# guards                                                                      #
# --------------------------------------------------------------------------- #

def check_owner(owner: Owner) -> list[str]:
    """Both guards for one owner. Returns a list of problems, empty when clean."""
    problems: list[str] = []

    for pattern in owner.owns:
        try:
            _check_pattern(pattern)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        return problems

    if not owner.source.is_dir():
        return [f"source directory does not exist: {owner.source}"]

    files = _relative_files(owner.source)

    # Guard 1 - nothing produced falls outside the declaration.
    for rel in files:
        if claims(owner, rel):
            continue
        if any(matches(f"/{p}", rel) for p in owner.local_only):
            continue
        problems.append(
            f"unclaimed output {rel!r}: add a pattern to owns=, or to local_only= "
            f"if it is deliberately not published")

    # Guard 2 - nothing produced is claimed by somebody else, in either direction.
    for other in OWNERS.values():
        if other.name == owner.name or other.subdir != owner.subdir:
            continue
        for rel in files:
            if claims(owner, rel) and claims(other, rel):
                problems.append(
                    f"ownership collision on {rel!r}: claimed by both "
                    f"{owner.name!r} and {other.name!r}")

    return problems


def check_needs(owner: Owner) -> list[str]:
    """Completeness of the mirror from this family's point of view."""
    return [f"required input missing from the mirror: {rel}"
            for rel in owner.needs if not (MIRROR_ROOT / rel).is_file()]


# --------------------------------------------------------------------------- #
# mirror freshness                                                            #
# --------------------------------------------------------------------------- #

def mirror_status() -> dict:
    """The mirror's own report on itself. Missing file is a hard fault, not a
    warning: an unverifiable mirror is exactly the state we refuse to compute on."""
    if not MIRROR_STATUS.is_file():
        raise FileNotFoundError(
            f"no mirror status at {MIRROR_STATUS} - sync_rtbi.sh has not run "
            f"since the status stamp was introduced, or is failing before it writes")
    return json.loads(MIRROR_STATUS.read_text())


def mirror_age_minutes(status: dict) -> float:
    finished = datetime.fromisoformat(status["finished"])
    if finished.tzinfo is None:
        finished = finished.astimezone()
    return (datetime.now(timezone.utc) - finished).total_seconds() / 60.0


def require_fresh_mirror(max_age_min: int = DEFAULT_MAX_AGE_MIN,
                         stale_ok: bool = False) -> dict:
    status = mirror_status()
    age = mirror_age_minutes(status)
    exit_code = status.get("exit_code")
    faults = []
    if exit_code != 0:
        faults.append(f"last sync exited {exit_code}")
    if age > max_age_min:
        faults.append(f"last sync finished {age:.0f} min ago (limit {max_age_min})")
    if faults:
        message = "mirror not usable: " + "; ".join(faults)
        if not stale_ok:
            raise RuntimeError(message + " - rerun sync_rtbi.sh, or pass --stale-ok")
        print(f"WARNING: {message} - continuing because --stale-ok was given")
    else:
        print(f"Mirror OK: synced {age:.0f} min ago, {status.get('files', '?')} files")
    return status


# --------------------------------------------------------------------------- #
# fetch (mirror -> family input)                                              #
# --------------------------------------------------------------------------- #

def fetch(owner: Owner, max_age_min: int = DEFAULT_MAX_AGE_MIN,
          stale_ok: bool = False) -> int:
    """Copy this family's declared inputs out of the local mirror.

    A plain local copy - no rclone, no network, no Drive credentials. Inputs are
    flattened into input_dir (Longi/longi_per1d.csv -> longi_per1d.csv), which is
    what every family's reader already expects.
    """
    require_fresh_mirror(max_age_min, stale_ok)

    missing = check_needs(owner)
    if missing:
        for m in missing:
            print(f"ERROR: {m}")
        return 1

    owner.input_dir.mkdir(parents=True, exist_ok=True)
    for existing in owner.input_dir.iterdir():
        if existing.is_file():
            existing.unlink()

    for rel in owner.needs:
        src = MIRROR_ROOT / rel
        dst = owner.input_dir / Path(rel).name
        shutil.copy2(src, dst)
        print(f"  {rel} -> {dst.name}")

    print(f"Fetched {len(owner.needs)} file(s) from {MIRROR_ROOT} to {owner.input_dir}")
    return 0


# --------------------------------------------------------------------------- #
# publish (family output -> repository)                                       #
# --------------------------------------------------------------------------- #

def destination(owner: Owner, target: str = "drive") -> str:
    root = DRIVE_ROOT if target == "drive" else str(MIRROR_ROOT)
    return f"{root}/{owner.subdir}" if owner.subdir else root


def publish(owner: Owner, target: str = "drive", dry_run: bool = False) -> int:
    """rclone sync, scoped to this owner's namespace.

    `sync` and not `copy`, so retired outputs are cleaned up; scoped by filter, so
    the cleanup can only ever reach this owner's own files. The trailing `- **`
    is what makes every other family's files invisible to the transfer, including
    for deletion.
    """
    problems = check_owner(owner)
    if problems:
        for p in problems:
            print(f"ERROR: {p}")
        return 1

    dest = destination(owner, target)
    cmd = ["rclone", "sync", str(owner.source), dest, "--verbose", "--drive-skip-gdocs"]
    for pattern in owner.owns:
        cmd += ["--filter", f"+ {pattern}"]
    cmd += ["--filter", "- **"]
    if dry_run:
        cmd.append("--dry-run")

    print(f"Publishing {owner.name}: {owner.source} -> {dest}")
    print(f"  namespace: {', '.join(owner.owns)}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        print("ERROR: rclone command not found. Is rclone installed?")
        return 127

    if result.stdout:
        print(result.stdout, end="")
    if result.returncode == 0:
        print(f"SUCCESS: {owner.name} published")
    else:
        print(f"ERROR: rclone failed with exit code {result.returncode}")
    return result.returncode


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def cmd_check() -> int:
    failed = False
    for owner in OWNERS.values():
        print(f"--- {owner.name} ---")
        problems = check_owner(owner) + check_needs(owner)
        if problems:
            failed = True
            for p in problems:
                print(f"  ERROR: {p}")
        else:
            n = len([r for r in _relative_files(owner.source) if claims(owner, r)])
            print(f"  OK: {n} owned file(s), {len(owner.needs)} input(s) present")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="registry self-check for every owner")

    p_pub = sub.add_parser("publish", help="sync one owner's namespace to the repository")
    p_pub.add_argument("owner", choices=sorted(OWNERS))
    p_pub.add_argument("--target", choices=("drive", "mirror"), default="drive")
    p_pub.add_argument("--dry-run", action="store_true")

    p_fetch = sub.add_parser("fetch", help="copy one owner's inputs out of the mirror")
    p_fetch.add_argument("owner", choices=sorted(OWNERS))
    p_fetch.add_argument("--max-age-min", type=int, default=DEFAULT_MAX_AGE_MIN)
    p_fetch.add_argument("--stale-ok", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "check":
            return cmd_check()
        if args.command == "publish":
            return publish(OWNERS[args.owner], args.target, args.dry_run)
        return fetch(OWNERS[args.owner], args.max_age_min, args.stale_ok)
    except (RuntimeError, FileNotFoundError) as exc:
        # A refused mirror is an expected outcome, not a crash: these end up in a
        # cron log, where a traceback buries the one line that matters.
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
