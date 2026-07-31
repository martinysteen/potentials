#!/usr/bin/env python3
"""
aux_qc_repo.py - Quality control checks on longi_*.csv output files

Four checks per file:
  1. Front daynum (col 2 header) matches PotDat.csv front daynum
  2. No blank column headers between col 2 and last non-blank header
  3. First DENSITY_CHECK_COLS daynum columns each have at least one non-blank value
Plus one global check:
  4. Actual longi_*.csv file set matches EXPECTED_FILES

Usage:
  python3 aux_qc_repo.py           # full per-file report
  python3 aux_qc_repo.py --quiet   # summary only

API / pipeline usage:
  from aux_qc_repo import run_qc
  results = run_qc()               # returns dict; results["overall"] is True/False
"""

import sys
from pathlib import Path
from typing import Optional

CODE_DIR = Path(__file__).parent
OUTPUT_DIR = CODE_DIR.parent / "output"
INPUT_DIR = CODE_DIR.parent / "input"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"

DENSITY_CHECK_COLS = 10  # Number of most-recent daynum columns to test for data

# The forward-looking longi_future_per*.csv files are blank in their newest columns by
# construction — the signal day's future has not happened yet. Check 3 therefore starts
# AFTER that lead rather than reporting it as a defect; the check still verifies real
# density, just at the first columns where data is legitimately expected.
# Value = period_days + 1 (entry is signal+1), matching longi_future_performance.PERIODS.
BLANK_LEAD_COLS: dict[str, int] = {
    "longi_future_per1d.csv": 2,
    "longi_future_per1w.csv": 6,
    "longi_future_per1m.csv": 23,
    "longi_future_per3m.csv": 67,
    "longi_future_per6m.csv": 133,
    "longi_future_per1y.csv": 265,
}

# Canonical file set — update here when modules are added or removed
EXPECTED_FILES: set[str] = {
    "longi_beta1yr.csv",
    "longi_beta3m.csv",
    "longi_beta6m.csv",
    "longi_coreindex.csv",
    "longi_coreindexRSI.csv",
    "longi_future_per1d.csv",
    "longi_future_per1m.csv",
    "longi_future_per1w.csv",
    "longi_future_per1y.csv",
    "longi_future_per3m.csv",
    "longi_future_per6m.csv",
    "longi_grp_GICS_per1d.csv",
    "longi_grp_GICS_per1m.csv",
    "longi_grp_GICS_per1w.csv",
    "longi_grp_GICS_per1y.csv",
    "longi_grp_GICS_per3m.csv",
    "longi_grp_GICS_per6m.csv",
    "longi_grp_Sector2_per1d.csv",
    "longi_grp_Sector2_per1m.csv",
    "longi_grp_Sector2_per1w.csv",
    "longi_grp_Sector2_per1y.csv",
    "longi_grp_Sector2_per3m.csv",
    "longi_grp_Sector2_per6m.csv",
    "longi_iran.csv",
    "longi_ma10.csv",
    "longi_ma20.csv",
    "longi_ma50.csv",
    "longi_ma200.csv",
    "longi_macd_histogram.csv",
    "longi_macd_line.csv",
    "longi_macd_signal.csv",
    "longi_macd_Z.csv",
    "longi_median_10d.csv",
    "longi_median_20d.csv",
    "longi_median_30d.csv",
    "longi_median_40d.csv",
    "longi_median_50d.csv",
    "longi_median_100d.csv",
    "longi_PdivMA20.csv",
    "longi_PdivMA50.csv",
    "longi_PdivMA200.csv",
    "longi_per1d.csv",
    "longi_per1m.csv",
    "longi_per1w.csv",
    "longi_per1y.csv",
    "longi_per3m.csv",
    "longi_per6m.csv",
    "longi_price.csv",
    "longi_quot1020.csv",
    "longi_quot2050.csv",
    "longi_rank.csv",
    "longi_rsi.csv",
    "longi_sh1yr.csv",
    "longi_sh3m.csv",
    "longi_sh6m.csv",
    "longi_spr100d.csv",
    "longi_spr250d.csv",
    "longi_stepup40.csv",
    "longi_stepup100.csv",
    "longi_trump.csv",
    "longi_vola100d.csv",
    "longi_vola20d.csv",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_header(filepath: Path) -> Optional[list[str]]:
    """Return semicolon-split first line, or None on I/O error."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.readline().rstrip("\n").split(";")
    except OSError:
        return None


def get_potdat_front_daynum(potdat_file: Path = POTDAT_FILE) -> Optional[int]:
    """Return column-2 header of PotDat.csv as int, or None on failure."""
    cols = _read_header(potdat_file)
    if not cols or len(cols) < 2:
        return None
    try:
        return int(cols[1].strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Individual checks — each returns (ok: bool, message: str)
# ---------------------------------------------------------------------------

def check_front_daynum(filepath: Path, expected: int) -> tuple[bool, str]:
    """Check 1: col-2 header equals PotDat front daynum."""
    cols = _read_header(filepath)
    if not cols or len(cols) < 2:
        return False, "cannot read header"
    cell = cols[1].strip()
    if not cell:
        return False, "col-2 header blank"
    try:
        actual = int(cell)
    except ValueError:
        return False, f"col-2 not integer: {cell!r}"
    if actual == expected:
        return True, str(actual)
    lag = expected - actual
    sign = "+" if lag >= 0 else ""
    return False, f"{actual} (lag {sign}{lag})"


def check_header_continuity(filepath: Path) -> tuple[bool, str]:
    """Check 2: no blank headers between col-2 and last non-blank header."""
    cols = _read_header(filepath)
    if not cols:
        return False, "cannot read header"
    headers = cols[1:]  # skip ticker-placeholder at col 1
    last = max((i for i, h in enumerate(headers) if h.strip()), default=-1)
    if last < 0:
        return False, "no daynum headers"
    blanks = [i for i in range(last + 1) if not headers[i].strip()]
    if blanks:
        cols_1based = [str(i + 2) for i in blanks[:3]]
        tail = f" (+{len(blanks) - 3} more)" if len(blanks) > 3 else ""
        return False, f"{len(blanks)} blank(s) at col(s) {', '.join(cols_1based)}{tail}"
    return True, f"{last + 1} hdrs OK"


def check_data_density(
    filepath: Path, n_cols: int = DENSITY_CHECK_COLS, lead: int = 0
) -> tuple[bool, str]:
    """Check 3: n_cols daynum columns, starting after `lead` legitimately-blank ones,
    each have at least one non-blank cell.

    `lead` is 0 for every ordinary file. It is non-zero only for the forward-looking
    longi_future_per*.csv, whose newest columns are empty by construction — see
    BLANK_LEAD_COLS.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        return False, f"read error: {e}"

    if len(lines) < 2:
        return False, "no data rows"

    header = lines[0].rstrip("\n").split(";")
    cols_to_check = min(n_cols, len(header) - 1 - lead)
    if cols_to_check <= 0:
        return False, f"fewer than {lead + 1} daynum columns (lead {lead})"

    # Count non-blank values per daynum column; parse only what we look at
    counts = [0] * cols_to_check
    for line in lines[1:]:
        parts = line.rstrip("\n").split(";", lead + cols_to_check + 1)
        for c in range(cols_to_check):
            idx = lead + c + 1
            if idx < len(parts) and parts[idx].strip():
                counts[c] += 1

    empty_col_names = [
        header[lead + c + 1] if (lead + c + 1) < len(header) else f"col{lead + c + 2}"
        for c, cnt in enumerate(counts)
        if cnt == 0
    ]
    if empty_col_names:
        return False, f"all-blank: {', '.join(empty_col_names)}"

    total = len(lines) - 1
    min_fill = min(counts) if counts else 0
    skipped = f" after {lead}" if lead else ""
    return True, f"min {min_fill}/{total} ({cols_to_check} cols{skipped})"


def check_file_set(output_dir: Path = OUTPUT_DIR) -> tuple[bool, str, list[str], list[str]]:
    """Check 4: actual longi_*.csv files match EXPECTED_FILES."""
    actual = {f.name for f in output_dir.glob("longi_*.csv")}
    missing = sorted(EXPECTED_FILES - actual)
    extra = sorted(actual - EXPECTED_FILES)
    ok = not missing and not extra
    parts: list[str] = []
    if missing:
        parts.append(f"MISSING ({len(missing)}): {', '.join(missing)}")
    if extra:
        parts.append(f"EXTRA ({len(extra)}): {', '.join(extra)}")
    msg = "; ".join(parts) if parts else f"{len(actual)} files match spec"
    return ok, msg, missing, extra


# ---------------------------------------------------------------------------
# Main QC runner
# ---------------------------------------------------------------------------

def run_qc(
    output_dir: Path = OUTPUT_DIR,
    potdat_file: Path = POTDAT_FILE,
    quiet: bool = False,
) -> dict:
    """
    Run all QC checks and return a results dict:
      {
        "potdat_front_daynum": int | None,
        "files": { filename: {"check1": {ok, msg}, "check2": ..., "check3": ...} },
        "check4": {"ok": bool, "msg": str, "missing": list, "extra": list},
        "overall": bool,
        "n_pass": int,   # files where all 3 per-file checks passed
        "n_fail": int,
      }
    """
    front_daynum = get_potdat_front_daynum(potdat_file)

    if not quiet:
        print(f"=== QC: longi_*.csv  output={output_dir} ===")
        if front_daynum is not None:
            print(f"PotDat front daynum : {front_daynum}")
        else:
            print(f"WARNING: cannot read front daynum from {potdat_file}")
        print()
        print(f"{'File':<36} {'C1 daynum':<20} {'C2 headers':<22} C3 density")
        print("-" * 104)

    file_results: dict[str, dict] = {}
    n_pass = n_fail = 0

    for filepath in sorted(output_dir.glob("longi_*.csv")):
        name = filepath.name

        if front_daynum is not None:
            c1_ok, c1_msg = check_front_daynum(filepath, front_daynum)
        else:
            c1_ok, c1_msg = True, "skip (no PotDat)"

        c2_ok, c2_msg = check_header_continuity(filepath)
        c3_ok, c3_msg = check_data_density(filepath, lead=BLANK_LEAD_COLS.get(name, 0))

        file_results[name] = {
            "check1": {"ok": c1_ok, "msg": c1_msg},
            "check2": {"ok": c2_ok, "msg": c2_msg},
            "check3": {"ok": c3_ok, "msg": c3_msg},
        }

        file_ok = c1_ok and c2_ok and c3_ok
        if file_ok:
            n_pass += 1
        else:
            n_fail += 1

        if not quiet:
            def _fmt(ok: bool, msg: str, width: int = 0) -> str:
                tag = "OK  " if ok else "FAIL"
                text = f"{tag} {msg}"
                return text[:width].ljust(width) if width > 0 else text

            c1 = _fmt(c1_ok, c1_msg, 20)
            c2 = _fmt(c2_ok, c2_msg, 22)
            c3 = _fmt(c3_ok, c3_msg, 0)
            print(f"{name:<36} {c1} {c2} {c3}")

    # Check 4 — counts as one entry in overall pass/fail
    c4_ok, c4_msg, c4_missing, c4_extra = check_file_set(output_dir)
    if c4_ok:
        n_pass += 1
    else:
        n_fail += 1

    if not quiet:
        print()
        tag = "OK  " if c4_ok else "FAIL"
        print(f"Check 4 (file set)  : {tag} {c4_msg}")
        print()
        verdict = "ALL PASS" if n_fail == 0 else f"{n_fail} FAILED"
        print(f"=== SUMMARY: {n_pass} pass, {n_fail} fail — {verdict} ===")

    return {
        "potdat_front_daynum": front_daynum,
        "files": file_results,
        "check4": {"ok": c4_ok, "msg": c4_msg, "missing": c4_missing, "extra": c4_extra},
        "overall": n_fail == 0,
        "n_pass": n_pass,
        "n_fail": n_fail,
    }


def main() -> int:
    quiet = "--quiet" in sys.argv
    results = run_qc(quiet=quiet)
    return 0 if results["overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
