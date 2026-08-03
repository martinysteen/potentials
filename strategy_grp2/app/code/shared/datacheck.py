"""
Input-data guard: check the repositoryRTBI files a run needs, then FREEZE them into a
run-local snapshot that the run reads from instead of the live repository.

Why this exists
---------------
`repositoryRTBI/data/` is not a static input — it is rewritten all day long by three
independent cron jobs that are closely timed but not synchronised:

    :07/:37/:55 repositoryRTBI/sync_rtbi.sh   `rclone sync` from Google Drive. A *sync*,
                                              so it DELETES a local file the moment the
                                              Drive side is itself mid-regeneration.
    :15         longi/start_longi.sh          rebuilds the longi_* family
    :45         group_conformity/run_conf.sh  rebuilds the longi_conf_* / sectorbeta_* family

A run started at an unlucky minute therefore sees one of two bad states:

  (a) a file is simply GONE — pandas raises deep inside a strategy, run_sweep's blanket
      `except Exception` prints one line into a wall of sweep output, and the run vanishes.

  (b) worse: a COMPLETE set of files, from TWO different generations. Between the mirror
      tick that lands longi's output and the one that lands group_conformity's,
      `longi_rank.csv` already carries today's newest daynum while `longi_conf_GICS.csv`
      still ends a day earlier. Note this window is structural, not a race: conformity
      CONSUMES longi_per1d, so its files can never be newer than longi's. Nothing downstream raises on this, because every consumer
      treats "this daynum is not a column" as a legitimate no-pick — shared.dominance
      .select_focusset returns [], the report writers write blanks. The run sails through
      the whole sweep producing empty focussets and only detonates much later, in the
      extension step, with a traceback that points nowhere near the cause.

(b) is the reason this module exists. A louder data_loader alone would not have caught it:
nothing was missing at any single moment — the *assortment* was incoherent.

What it does
------------
1. **Preflight** every required file against the live repository: present, non-empty,
   parseable, not written seconds ago (possibly still mid-write), and — for the daynum
   matrices — all agreeing on the same newest daynum. That last rule is the one that
   catches (b), and it is a hard failure, not a warning.
2. **Snapshot**: copy the checked set into `app/data/input/`, write a `snapshot.json`
   recording the vintage, and point `shared.config` at it. Everything the run opens from
   then on is one coherent generation, immune to a sync landing mid-run.

Copies, not hardlinks: hardlinking would be instant and free, but it only isolates us if
rclone always writes a new inode and renames. `--inplace` (or a future rclone default
change) would rewrite the very bytes our link points at. The required set is ~45 MB — a
copy takes under a second and needs no assumption about rclone's write strategy.

The snapshot is deliberately NOT reused across runs when the live data is healthy: one run
= one fresh, coherent vintage. It is only fallen back on with `--stale-ok`, and then loudly.

Generic on purpose — it knows nothing about DomGICS or any strategy. The list of files a
run actually needs is assembled by `preflight.py`, which is where the project-specific
knowledge lives; this module takes that list as an argument.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from shared import config


class DataUnavailable(FileNotFoundError):
    """A required input CSV is missing, empty, unreadable, or of the wrong vintage.

    Subclasses FileNotFoundError deliberately: the two places that treat a Longi file as
    genuinely OPTIONAL (`shared/report.py::_beta_frame`, `shared/extension.py::_beta_frame`)
    catch `(FileNotFoundError, OSError)` and must keep silently degrading. Everywhere else
    this surfaces as one named, loud failure instead of a bare pandas traceback thrown from
    six frames deep inside a strategy.
    """


# A file written this recently may still be mid-write (rclone landing, longi flushing).
# 45s is comfortably longer than any single file's write in the observed logs and short
# enough that a manual run right after a cron tick is not blocked for long.
MIN_AGE_SECONDS: float = 45.0

# Row-count drop vs the previous snapshot that reads as truncation rather than as normal
# ticker churn. Warning only — a truncated file usually also fails one of the hard rules.
ROW_DROP_TOLERANCE: float = 0.02

SNAPSHOT_ROOT: Path = config.APP_ROOT / "data" / "input"
MANIFEST_NAME: str = "snapshot.json"


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

@dataclass
class FileStat:
    """One input file as the guard sees it. `newest_daynum` is None for a non-matrix
    file (Stamdata/Cal) or when the header could not be read."""
    rel: str                      # path relative to the data root, e.g. "Longi/longi_rank.csv"
    path: Path
    required: bool
    exists: bool = False
    size: int = 0
    age: float = 0.0              # seconds since last modification
    n_rows: int = 0
    newest_daynum: int | None = None
    is_matrix: bool = False
    error: str = ""               # non-empty => this file is unusable

    @property
    def ok(self) -> bool:
        return self.exists and not self.error


def _is_matrix(rel: str) -> bool:
    """True for the daynum-column matrices (Longi/* and PotDat.csv) — the files whose
    newest column must agree. Stamdata.csv (attributes) and Cal.csv (daynum->date) carry
    no daynum columns and are exempt from the vintage rule."""
    return rel.startswith("Longi/") or rel == "PotDat.csv"


def _count_rows(path: Path) -> int:
    """Line count, buffered — a cheap completeness signal that survives on 13 MB files."""
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            n += chunk.count(b"\n")
    return n


def inspect_file(root: Path, rel: str, required: bool) -> FileStat:
    """Stat + header-parse one file. Never raises: an unusable file comes back with
    `.error` set, so the caller can report every problem at once instead of dying on
    the first one (the whole point — a partial diagnosis is what made this hard to track)."""
    st = FileStat(rel=rel, path=root / rel, required=required, is_matrix=_is_matrix(rel))
    if not st.path.exists():
        st.error = "missing"
        return st
    st.exists = True
    info = st.path.stat()
    st.size = info.st_size
    st.age = max(0.0, time.time() - info.st_mtime)
    if st.size == 0:
        st.error = "empty (0 bytes)"
        return st
    try:
        header = pd.read_csv(st.path, sep=";", decimal=",", index_col=0, nrows=0)
    except Exception as exc:                      # noqa: BLE001 - report, never propagate
        st.error = f"unreadable: {type(exc).__name__}"
        return st
    st.n_rows = _count_rows(st.path)
    if st.is_matrix:
        # Columns are daynum strings, newest LEFT — so column 0 is this file's vintage.
        try:
            st.newest_daynum = int(str(header.columns[0]).strip())
        except (IndexError, ValueError):
            st.error = "no daynum columns in header"
    return st


def inspect_all(root: Path, required: list[str], optional: list[str]) -> list[FileStat]:
    return ([inspect_file(root, rel, True) for rel in required]
            + [inspect_file(root, rel, False) for rel in optional])


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    stats: list[FileStat]
    failures: list[str]           # hard problems — the run must not proceed
    warnings: list[str]           # worth printing, not worth stopping for
    daynum: int | None            # the agreed newest daynum, when there is one

    @property
    def ok(self) -> bool:
        return not self.failures


def evaluate(stats: list[FileStat], prior: dict | None = None,
             source: Path | None = None) -> Verdict:
    """Turn a list of FileStats into a go/no-go, collecting EVERY problem.

    Hard failures:
      * a required file missing / empty / unreadable
      * a required file modified within MIN_AGE_SECONDS (may still be mid-write)
      * required matrices disagreeing on their newest daynum (the vintage skew that
        silently produces empty focussets)

    Warnings: the same problems on an optional file, and a row-count drop against the
    previous snapshot large enough to look like truncation.
    """
    failures: list[str] = []
    warnings: list[str] = []

    for st in stats:
        bucket = failures if st.required else warnings
        tag = "" if st.required else " (optional)"
        if st.error:
            bucket.append(f"{st.rel}{tag}: {st.error}")
            continue
        if st.age < MIN_AGE_SECONDS:
            bucket.append(f"{st.rel}{tag}: written {st.age:.0f}s ago — may still be "
                          f"mid-write (need {MIN_AGE_SECONDS:.0f}s)")

    # --- vintage coherence: every usable required matrix on the same newest daynum ---
    vintages: dict[int, list[str]] = {}
    for st in stats:
        if st.required and st.ok and st.newest_daynum is not None:
            vintages.setdefault(st.newest_daynum, []).append(st.rel)
    daynum: int | None = None
    if len(vintages) == 1:
        daynum = next(iter(vintages))
    elif len(vintages) > 1:
        newest = max(vintages)
        behind = sorted(rel for dn, rels in vintages.items() if dn != newest for rel in rels)
        failures.append(
            f"vintage skew: newest daynum is {newest}, but "
            + ", ".join(f"{rel} ends at {dn}"
                        for dn in sorted(vintages) if dn != newest
                        for rel in vintages[dn][:2])
            + (f" (+{len(behind) - 2} more)" if len(behind) > 2 else "")
            + " — two generations of input; a run on this mix produces empty picks silently")

    # --- truncation check against the previous snapshot ---
    # Only when that snapshot came from the same source root: comparing row counts across
    # two different roots reports ordinary difference as truncation.
    if prior and (source is None or prior.get("source") == str(source)):
        prior_rows = prior.get("rows", {})
        for st in stats:
            was = prior_rows.get(st.rel)
            if was and st.n_rows and st.n_rows < was * (1 - ROW_DROP_TOLERANCE):
                warnings.append(f"{st.rel}: {st.n_rows} rows vs {was} in the previous "
                                f"snapshot ({100 * (1 - st.n_rows / was):.0f}% fewer) — "
                                f"possible truncated write")

    return Verdict(stats=stats, failures=failures, warnings=warnings, daynum=daynum)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_table(verdict: Verdict, root: Path) -> None:
    """The one-screen diagnosis. Printed on failure, and on request via preflight.py."""
    print(f"\nInput preflight — {root}")
    print(f"  {'file':<34} {'daynum':>7} {'rows':>7} {'MB':>6} {'age':>8}  status")
    print(f"  {'-' * 34} {'-' * 7} {'-' * 7} {'-' * 6} {'-' * 8}  {'-' * 24}")
    for st in verdict.stats:
        dn = str(st.newest_daynum) if st.newest_daynum is not None else "-"
        rows = str(st.n_rows) if st.n_rows else "-"
        mb = f"{st.size / 1e6:.1f}" if st.size else "-"
        age = _fmt_age(st.age) if st.exists else "-"
        if st.error:
            status = f"** {st.error.upper()}"
        elif st.age < MIN_AGE_SECONDS:
            status = "** IN FLIGHT"
        else:
            status = "ok" if st.required else "ok (optional)"
        print(f"  {st.rel:<34} {dn:>7} {rows:>7} {mb:>6} {age:>8}  {status}")

    for w in verdict.warnings:
        print(f"  WARN  {w}")
    for f in verdict.failures:
        print(f"  FAIL  {f}")
    if verdict.ok:
        print(f"  -> coherent at daynum {verdict.daynum}")


def _fmt_age(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


def _diagnosis(verdict: Verdict, root: Path) -> str:
    """The message that goes into the DataUnavailable — the thing that was missing when
    this failed for real. Names the files AND why the repository looks like this."""
    lines = [f"Input data is not usable ({len(verdict.failures)} problem(s)) in {root}:"]
    lines += [f"  - {f}" for f in verdict.failures]
    lines += [
        "",
        "repositoryRTBI is rewritten on a cron all day (rclone sync :07/:37, longi :15,",
        "conformity :30), so this is usually transient — re-run a few minutes later, or:",
        "  python preflight.py            # show this table without running anything",
        "  <entry point> --stale-ok       # run on the last good snapshot instead",
        "  <entry point> --live           # read the live repository unguarded (old behaviour)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def read_manifest(root: Path | None = None) -> dict | None:
    """The existing snapshot's snapshot.json, or None when there is no usable snapshot.

    `root=None` resolves SNAPSHOT_ROOT at CALL time, not at def time — a default argument
    would freeze the module-level value at import and quietly ignore a redirected root
    (which is how the first version of this module wrote a test snapshot over the real one).
    """
    root = SNAPSHOT_ROOT if root is None else root
    path = root / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_snapshot(stats: list[FileStat], daynum: int | None,
                   source: Path, dest: Path | None = None) -> dict:
    """Copy every usable file into `dest` and write snapshot.json. Returns the manifest.

    Built in a staging directory and swapped in, so an interrupted build can never leave
    a half-populated snapshot behind for the next run to read as if it were complete.
    `dest=None` resolves SNAPSHOT_ROOT at call time — see read_manifest for why.
    """
    dest = SNAPSHOT_ROOT if dest is None else dest
    staging, retired = dest.with_name(".input_new"), dest.with_name(".input_old")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    rows: dict[str, int] = {}
    copied = 0
    for st in stats:
        if not st.ok:
            continue                              # optional-and-absent: leave it absent
        target = staging / st.rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(st.path, target)
        rows[st.rel] = st.n_rows
        copied += 1

    manifest = {
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
        "built_epoch": time.time(),
        "daynum": daynum,
        "source": str(source),
        "files": copied,
        "rows": rows,
    }
    (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Swap: retire the old snapshot, promote the new one, then delete the old.
    if retired.exists():
        shutil.rmtree(retired)
    if dest.exists():
        os.replace(dest, retired)
    os.replace(staging, dest)
    if retired.exists():
        shutil.rmtree(retired)
    return manifest


# ---------------------------------------------------------------------------
# The entry point every runner calls
# ---------------------------------------------------------------------------

def ensure_data(required: list[str], optional: list[str] | None = None, *,
                mode: str = "snapshot", verbose: bool = True) -> Path:
    """Preflight the live repository, freeze it, and point shared.config at the frozen copy.

    mode:
      "snapshot"  (default) preflight -> build a fresh snapshot -> read from it.
      "stale-ok"  same, but if the live data is incoherent fall back to the EXISTING
                  snapshot (loudly, with its age and vintage) instead of refusing to run.
      "live"      preflight only, then read the live repository directly — the old,
                  unguarded behaviour, kept for one-off inspection.

    Returns the data root the run will actually read. Raises DataUnavailable, with the
    full table already printed, when the data cannot be trusted.
    """
    optional = optional or []
    source = config.DATA_ROOT
    stats = inspect_all(source, required, optional)
    verdict = evaluate(stats, prior=read_manifest(), source=source)

    if verdict.ok:
        if mode == "live":
            config.use_data_root(source)
            if verbose:
                print(f"[input] LIVE repository, coherent at daynum {verdict.daynum} "
                      f"— not snapshotted ({source})")
            return source
        manifest = build_snapshot(stats, verdict.daynum, source)
        config.use_data_root(SNAPSHOT_ROOT)
        if verbose:
            print(f"[input] snapshot @ daynum {manifest['daynum']} "
                  f"({manifest['files']} files, built {manifest['built']}) "
                  f"<- {source}")
            for w in verdict.warnings:
                print(f"[input] WARN {w}")
        return SNAPSHOT_ROOT

    print_table(verdict, source)

    if mode == "stale-ok":
        prior = read_manifest()
        if prior:
            age_h = (time.time() - prior.get("built_epoch", 0)) / 3600
            print("\n" + "!" * 78)
            print(f"!! --stale-ok: live data is NOT usable — running on the previous snapshot")
            print(f"!! vintage daynum {prior.get('daynum')}, built {prior.get('built')} "
                  f"({age_h:.1f}h ago). Output is NOT current.")
            print("!" * 78 + "\n")
            config.use_data_root(SNAPSHOT_ROOT)
            return SNAPSHOT_ROOT
        print("\n--stale-ok requested but there is no previous snapshot to fall back on.")

    raise DataUnavailable(_diagnosis(verdict, source))
