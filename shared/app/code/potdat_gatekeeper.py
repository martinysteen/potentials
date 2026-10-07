#!/usr/bin/env python3
"""
potdat_gatekeeper.py - the PotDat gatekeeper: every read of PotDat.csv goes through
here (SM, 2026-10-07). It decides which tickers' newest price is genuine and which is
a carried copy of the day before.

Why this exists
---------------
When the Asian markets open, PotDatC gets a new daynum column D, and every price
in it starts as a copy of D-1 ("old prices rule until new data arrives"). Until a
ticker's own market trades on D - which on an exchange holiday is never - that copy
looks exactly like a real price, so every trailing calculation reads it as a 0 % day:
per1d = 0, per10d is really per9d, rank-today = rank-yesterday. Consumers therefore
carry READINGS (indicator values) for the tickers named by carry_for(), instead of
trusting copied PRICES.

How it decides (carry_for)
--------------------------
The gatekeeper runs the survey below on the file itself - the data says which markets
are flat, no upstream declaration needed. Upstream only stamps PotDat.csv's top-left
cell with its creation date-time. As a manual override, an explicit marker in that
cell wins over the survey:

    07-10-26 02.15 (2250) carry=.L,.DE,.US,^GSPC      force exactly these groups
    07-10-26 23.10 (2250) carry=                       force nothing carried

Only `(daynum) carry=<groups>` is parsed; the timestamp in front is free text. The
daynum must equal the header's own newest column, else the override is ignored (and
the survey decides).

Groups (see group_key): a Yahoo suffix (`.L`, `.TO`, `.T`, ...); `.US` for tickers with
no suffix (Yahoo has no real `.US`); an index by its full name (`^GSPC`) - indices are
judged one by one. A plain ticker name (`ABC.TO`) carries just that ticker. Zones are
deliberately NOT used: holidays differ inside a zone (.L vs .DE, .HK vs .T) and even
between US and Canada.

The rule (survey)
--------
A suffix group is carried when a strict majority (> 50 %) of its tickers with a price
in both D and D-1 have D == D-1. An index is carried when its own D == D-1.

Supplemented data (SM, 2026-10-07): Google Finance does not cover Oslo, Tokyo or ^BTC,
and misprices ~30 US/CAN stocks; those prices are added by hand once a night (22:30).
They are open but stale in between, which the rule already handles: Oslo/Tokyo are
whole suffix groups (100 % flat until 22:30 -> carried), ^BTC is judged on its own. The
~30 single tickers are a minority inside .US/.TO, so the majority cannot see them; passed
as `singles`, each is judged on its own D == D-1 like an index. How SM supplies that
list is still open (2026-10-07) - until then `singles` is empty and those ~30 show 0 %.
Checked against 130 days of history (2026-04..10): real closures sit at 84-100 %,
normal days at <= 33 % for groups of 6+; 1-3 ticker groups are noisy (illiquid names
at exactly 50 % do not trip the strict majority).

Entry points (every PotDat read goes through one of them)
------------
  shared/app/code/repository.py fetch          admit() on PotDat; looks_intact() on the rest
  longi/app/code/longi_provisional.py          carry_for() -> carries readings
  yf3/app/code/gd_download.py                  looks_intact() on every Drive download
  {strategy_grp2,potrank,tunnel}/.../datacheck  admit() on PotDat in the preflight snapshot
  repositoryRTBI/mcp/catalog.py                admit() on PotDat; carry noted in replies
Standard library only, so any project can import it (append, not insert, the folder to
sys.path, so it cannot shadow a project's own modules).

CLI:  python3 potdat_gatekeeper.py survey <PotDat.csv> [SINGLE ...]   -> per-group counts + verdict
      python3 potdat_gatekeeper.py admit  <PotDat.csv> [SINGLE ...]   -> one-line admission, exit 1 if refused
"""

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

MARKER_RE = re.compile(r"\((\d+)\)\s*carry=([^\s;]*)")
NO_SUFFIX = ".US"
MAJORITY = 0.5


def group_key(ticker: str) -> str:
    """`^GSPC` -> `^GSPC`, `NOVO-B.CO` -> `.CO`, `NVDA` -> `.US`."""
    if ticker.startswith("^"):
        return ticker
    return "." + ticker.rsplit(".", 1)[1] if "." in ticker else NO_SUFFIX


@dataclass(frozen=True)
class CarryMarker:
    daynum: int
    groups: FrozenSet[str]
    stamp: str  # the full first cell, for logging

    def carried(self, ticker: str) -> bool:
        return bool(ticker) and (ticker in self.groups or group_key(ticker) in self.groups)


def parse_marker(first_cell: str, newest_daynum: str) -> Tuple[Optional[CarryMarker], str]:
    """(marker, message). marker is None when there is no usable marker; message says why."""
    m = MARKER_RE.search(first_cell)
    if not m:
        return None, f"no carry= marker in first cell {first_cell!r} (old format) - nothing carried"
    daynum = int(m.group(1))
    if str(daynum) != newest_daynum.strip():
        return None, (f"ERROR: marker daynum {daynum} != newest header column {newest_daynum!r} "
                      f"(stamp {first_cell!r} from another generation) - marker ignored")
    groups = frozenset(g.strip() for g in m.group(2).split(",") if g.strip())
    return CarryMarker(daynum, groups, first_cell.strip()), f"marker {first_cell.strip()!r}"


def read_carry_marker(potdat_path: Path) -> Tuple[Optional[CarryMarker], str]:
    """Parse the marker from PotDat.csv's header row (only the first line is read)."""
    with open(potdat_path, "r", encoding="utf-8") as f:
        header = f.readline().rstrip("\r\n").split(";")
    if len(header) < 2:
        return None, f"ERROR: {potdat_path.name} header has no daynum columns - marker ignored"
    return parse_marker(header[0], header[1])


def survey(potdat_path: Path, singles: FrozenSet[str] = frozenset()
           ) -> Tuple[str, List[str], Dict[str, Tuple[int, int]]]:
    """Reference rule: (newest daynum, carried groups, {group: (identical, compared)}).
    `singles` (the hand-supplemented tickers) are judged one by one, outside their suffix."""
    stats: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    with open(potdat_path, "r", encoding="utf-8") as f:
        daynum = f.readline().rstrip("\r\n").split(";")[1]
        for line in f:
            p = line.rstrip("\r\n").split(";", 3)
            if len(p) < 3 or not p[1].strip() or not p[2].strip():
                continue
            s = stats[p[0] if p[0] in singles else group_key(p[0])]
            s[0] += p[1].strip() == p[2].strip()
            s[1] += 1
    carried = sorted(g for g, (same, n) in stats.items() if same / n > MAJORITY)
    return daynum, carried, {g: (s[0], s[1]) for g, s in stats.items()}


def carry_for(potdat_path: Path, singles: FrozenSet[str] = frozenset()
              ) -> Tuple[CarryMarker, str]:
    """The gatekeeper's verdict on the newest column: an explicit carry= override in the
    first cell if valid, else the survey. Always returns a marker (possibly empty)."""
    override, msg = read_carry_marker(potdat_path)
    if override is not None:
        return override, f"explicit override {msg}"
    with open(potdat_path, "r", encoding="utf-8") as f:
        stamp = f.readline().split(";", 1)[0].strip()
    daynum, carried, _ = survey(potdat_path, singles)
    note = f" ({msg})" if msg.startswith("ERROR") else ""
    return (CarryMarker(int(daynum), frozenset(carried), stamp),
            f"survey of {daynum} (stamp {stamp!r}): carry={','.join(carried)}{note}")


def looks_intact(path: Path) -> Optional[str]:
    """Cheap structural sanity check - None if fine, else what is wrong. The ONE copy of
    the mid-write guard (2026-08-29 longi read 0 columns; 2026-09-06/07 yf3 lost two
    nights to a 1-byte `-` stub). Deliberately not a schema check, so it serves every
    European CSV in the repository, not only PotDat: repository.fetch runs it on all of a
    family's inputs, yf3 on every Drive download, the MCP server on every load."""
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            header = f.readline()
            first_data_row = f.readline()
    except OSError as exc:
        return f"cannot read {path.name}: {exc}"
    if not header.strip():
        return f"{path.name} is empty"
    if header.count(";") < 1:
        return f"{path.name} header has no ';' fields, looks truncated ({header[:60]!r})"
    if not first_data_row.strip():
        return f"{path.name} has a header but no data rows"
    return None


@dataclass(frozen=True)
class Admission:
    """The gatekeeper's answer to "may I read this PotDat.csv, and what is in it?"."""
    problem: Optional[str]          # None = admitted
    stamp: str = ""                 # top-left cell: upstream creation date-time (+ override)
    newest_daynum: Optional[int] = None
    carry: Optional[CarryMarker] = None
    carry_msg: str = ""

    @property
    def ok(self) -> bool:
        return self.problem is None

    def summary(self) -> str:
        if not self.ok:
            return f"REFUSED: {self.problem}"
        n = len(self.carry.groups) if self.carry else 0
        return (f"admitted {self.newest_daynum}, stamp {self.stamp!r}, "
                f"carry {n} group(s): {','.join(sorted(self.carry.groups)) if n else '-'}")


def admit(potdat_path: Path, singles: FrozenSet[str] = frozenset()) -> Admission:
    """The entry every PotDat read goes through: intact? -> stamp + newest daynum -> carry
    verdict. Never raises; a refused file comes back with `.problem` set. Readers that only
    need raw prices ignore `.carry`; readers that compute readings must honour it."""
    potdat_path = Path(potdat_path)
    problem = looks_intact(potdat_path)
    if problem:
        return Admission(problem)
    with open(potdat_path, "r", encoding="utf-8") as f:
        header = f.readline().rstrip("\r\n").split(";")
    try:
        newest = int(header[1].strip())
    except (IndexError, ValueError):
        return Admission(f"{potdat_path.name} header has no daynum columns ({header[:2]!r})")
    carry, msg = carry_for(potdat_path, singles)
    return Admission(None, header[0].strip(), newest, carry, msg)


def load_stamdata_columns(stamdata_path: Path, *columns: str) -> Dict[str, Tuple[str, ...]]:
    """ticker -> values of the named Stamdata columns. Uses csv (Stamdata has quoted
    fields containing ';' and newlines, so plain splitting misaligns rows)."""
    with open(stamdata_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    idx = [rows[0].index(c) for c in columns]
    return {r[0]: tuple(r[i] if i < len(r) else "" for i in idx) for r in rows[1:] if r}


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("survey", "admit"):
        sys.exit("usage: potdat_gatekeeper.py {survey|admit} <PotDat.csv> [SUPPLEMENTED_TICKER ...]")
    if sys.argv[1] == "admit":
        adm = admit(Path(sys.argv[2]), frozenset(sys.argv[3:]))
        print(adm.summary())
        sys.exit(0 if adm.ok else 1)
    daynum, carried, stats = survey(Path(sys.argv[2]), frozenset(sys.argv[3:]))
    for g in sorted(stats, key=lambda g: (g.startswith("^"), not g.startswith("."), g)):
        same, n = stats[g]
        print(f"  {g:10s} {same:4d}/{n:<4d} {'CARRY' if g in carried else ''}")
    print(f"({daynum}) carry={','.join(carried)}")
