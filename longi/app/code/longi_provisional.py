"""
Provisional-Column Module - carry readings, not prices

When PotDat.csv's newest column D is provisional (prices copied from D-1 for markets
that have not traded on D yet, or are closed), every trailing calculation reads the copy
as a 0 % day. shared/app/code/potdat_gatekeeper.py decides which tickers are carried;
this module repairs the already-written outputs IN PLACE for those tickers:

  CARRY  (D value := D-1 value) - every per-ticker trailing table: per*, rsi, macd*,
         ma*, PdivMA*, quot*, spr*, vola*, sh*, regr*, trump, iran, and anything new
         that is not excluded below. Exact, not an approximation: a trailing reading
         at D-1 uses only data up to D-1, so it equals "computed without the copy".
           - coreindex, coreindexRSI: keyed on whether the ticker's CoreIndex is carried
           - beta*: carried if the ticker OR its CoreIndex is carried
  BLANK  longi_future_{per,minaggr}{N}d: the one column whose window reaches D (the
         first non-blank one, index N+1) - that outcome is not known yet.
  LEAVE  longi_price (the raw input snapshot), and the cross-sectional tables
         rank / median_* / stepup* / grp_* - those run AFTER this module (longi.py
         DAG) and are recomputed from the carried inputs instead.

Nothing carried (survey finds no flat group, or an explicit empty carry=) -> nothing touched.

Depends on: every module except rank/medians/stepup/grp_performance/across (longi.py)
Outputs: none of its own - rewrites existing longi_*.csv files.
Output goes to stdout - start_longi.sh handles logging redirection.
"""

import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Set

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "app" / "code"))
import potdat_gatekeeper as gatekeeper  # noqa: E402

INPUT_DIR = Path(__file__).parent.parent / "input"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"
STAMDATA_FILE = INPUT_DIR / "Stamdata.csv"

# Recomputed downstream of this module, or the raw snapshot - never carried
NOT_CARRIED_PREFIXES = ("longi_price.csv", "longi_rank.csv", "longi_median_", "longi_stepup",
                        "longi_grp_", "longi_future_")
INDEX_KEYED = {"longi_coreindex.csv", "longi_coreindexRSI.csv"}
FUTURE_RE = re.compile(r"^longi_future_(?:per|minaggr)(\d+)d\.csv$")


def rewrite(path: Path, daynum: int, tickers: Set[str], fn) -> int:
    """Apply fn(parts) to each row whose ticker is in `tickers`; atomic replace.
    Returns rows changed, or -1 if the file's newest column is not `daynum`."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    if not lines:
        return -1
    if lines[0].rstrip("\r\n").split(";")[1:2] != [str(daynum)]:
        return -1
    changed = 0
    for i in range(1, len(lines)):
        body = lines[i].rstrip("\r\n")
        eol = lines[i][len(body):]
        parts = body.split(";")
        if parts[0] in tickers and fn(parts):
            lines[i] = ";".join(parts) + eol
            changed += 1
    if changed:
        tmp = path.with_suffix(".csv.provisional_tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
        os.replace(tmp, path)
    return changed


def carry(parts) -> bool:
    if len(parts) < 3 or parts[1] == parts[2]:
        return False
    parts[1] = parts[2]
    return True


def blank_at(idx: int):
    def fn(parts) -> bool:
        # Only the first value after the legitimate blank lead - anything else means
        # the file is not shaped as expected, so leave the row alone.
        if idx >= len(parts) or not parts[idx].strip() or any(p.strip() for p in parts[1:idx]):
            return False
        parts[idx] = ""
        return True
    return fn


def main() -> int:
    print("Provisional newest column: carry readings for markets still carried")

    marker, msg = gatekeeper.carry_for(POTDAT_FILE)
    print(f"1. {msg}")
    if not marker.groups:
        print("SUCCESS: nothing provisional - outputs left untouched")
        return 0

    core = {t: v[0] for t, v in gatekeeper.load_stamdata_columns(STAMDATA_FILE, "CoreIndex").items()}
    with open(POTDAT_FILE, "r", encoding="utf-8") as f:
        f.readline()
        potdat_tickers = [line.split(";", 1)[0] for line in f if line.strip()]

    own_off = {t for t in potdat_tickers if marker.carried(t)}
    idx_off = {t for t in potdat_tickers if marker.carried(core.get(t, ""))}
    print(f"2. Carried: {len(own_off)}/{len(potdat_tickers)} tickers "
          f"({dict(Counter(gatekeeper.group_key(t) for t in own_off))}); "
          f"CoreIndex carried: {len(idx_off)}")

    print(f"3. Rewriting outputs for daynum {marker.daynum}")
    n_files, skipped = 0, []
    for path in sorted(OUTPUT_DIR.glob("longi_*.csv")):
        name = path.name
        fut = FUTURE_RE.match(name)
        if fut:
            tickers, fn, how = own_off, blank_at(int(fut.group(1)) + 2), "blank"
        elif name.startswith(NOT_CARRIED_PREFIXES):
            continue
        elif name in INDEX_KEYED:
            tickers, fn, how = idx_off, carry, "carry(index)"
        elif name.startswith("longi_beta"):
            tickers, fn, how = own_off | idx_off, carry, "carry(own|index)"
        else:
            tickers, fn, how = own_off, carry, "carry"
        changed = rewrite(path, marker.daynum, tickers, fn)
        if changed < 0:
            skipped.append(name)
            continue
        n_files += 1
        print(f"   {name}: {how} {changed} rows")

    if skipped:
        print(f"WARNING: newest column != {marker.daynum}, left untouched: {', '.join(skipped)}")
    print(f"SUCCESS: {n_files} files processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
