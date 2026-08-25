# potrank — the PotRank wide snapshot

`PotRank` used to be a Google Sheet that pulled many `longi_*.csv` matrices plus Stamdata and
Yfinance straight in, renamed and reshaped them, reached back 1-2 trading days for RSI/MACD,
and counted top-100-ranked stocks per GICS/Sector2 group — all inside the Sheet's own formulas.
Users read it during the day for trading decisions.

This project rebuilds that content as a produced file, `potrank2.csv`, so the Sheet becomes a
pure importer instead of a calculation engine. The old manual export,
`repositoryRTBI/data/PotRank.csv`, is stopped (SM, 2026-08-25) — do not resurrect it as this
family's output name; the new name is deliberately different (see below).

## Column spec — `app/code/columns.py` is authoritative

68 columns, in schema order. `COLUMNS` there is the single source of truth: both `potrank.py`
(the builder) and `preflight.py` (the input-file guard, via `required_files()`) import it, so
the required-files list can never drift from what the builder actually reads.

Design authority is `schema.xlsx` in this folder, **not** the old manual `PotRank.csv` export —
the two disagreed when this was built (2026-08-25): the old export additionally had `PerfPoint`,
`Either`, `RSI-3d`/`RSI-4d`, `MACD-3d`/`MACD-4d` (dropped here) and was missing `P/MA20`/`P/MA200`
(added here).

Three rules that are easy to get wrong when adding or checking a column:

- **Column 1** (the ticker/row key) is not in `COLUMNS` — its header is the build timestamp plus
  daynum (`dd-mm-yy HH.MM (<daynum>)`), computed at write time, not a fixed label.
- **`offset` on a `longi` column is a plain positional read**, not daynum arithmetic: longi
  matrices are newest-left, so `offset=1`/`2` are literally "one/two columns to the right of
  today's", i.e. one/two trading days back. `RSI-1d`/`RSI-2d`, `MACD-1d`/`MACD-2d`, `Z-1d`, and
  `RankYd` all work this way.
- **`Close` appears twice** (columns 4 and 63) — intentional, matches `schema.xlsx`. Building via
  a list of `(header, series)` pairs and assigning `df.columns` at the end (rather than a
  dict-keyed build) is what lets pandas tolerate the duplicate label; do not "fix" it into a dict.

**The two calc columns** (`GICS i top100`, `Sector2 i top100`): take `longi_rank.csv`'s newest
column; a ticker is top-100 if `rank <= 100` (`columns.TOP100_RANK`, inclusive — SM's call,
2026-08-25). Group the top-100 set by the ticker's Stamdata `GICS` (resp. `Sector2`); every
ticker then carries its own group's count, so all members of one group show the same number. A
group with zero top-100 members gets `0`, not blank — confirmed against the live PotRank.csv
sample's own formatting (`;Basi;35,000;...`, 3-decimal, not a bare int).

**Row set and order**: every Stamdata ticker, deduplicated (`keep="first"`), minus `^`-prefixed
index tickers, sorted ascending by `RankNow` (unranked/NaN last). This exactly reproduces the old
`PotRank.csv` export's row set — verified empirically during planning (1206 rows = Stamdata's
1220 minus its 14 `^` tickers).

**Number formatting**: `f"{v:.3f}".replace(".", ",")`, NaN → `""`. Text columns pass through
as-is, NaN → `""`. European throughout: `sep=";"`, `decimal=","`.

**Exception — `Z-today`/`Z-1d`**: `longi_macd_Z.csv` legitimately carries the non-numeric
markers `ZOP`/`ZNED` instead of a score for some ticker/daynum cells (confirmed with SM,
2026-08-25 — not a data error to fix upstream). `_fmt_num` in `potrank.py` passes anything
that fails `float()` through as-is rather than blanking it, so these two columns are the
only "num"-kind columns that can legitimately hold text in the output.

## The two registration lists

A new column whose source file isn't already in `columns.COLUMNS` needs nothing extra
registered — `required_files()` derives the list from `COLUMNS` automatically. But **potrank
itself**, as a family, is registered in two places that don't know about each other (root
`CLAUDE.md`'s "Where the lists live" section):

1. **Ownership** — `shared/app/code/repository.py`, `OWNERS["potrank"]`: `subdir=""` (repository
   root, beside `Stamdata.csv`/`Cal.csv`/`PotDat.csv`), `owns=("/potrank2.csv",)`, `needs=()`
   deliberately — same as `strategy_grp2`, because the real input list lives here in
   `preflight.py`/`columns.py`, where it drives the vintage-coherence check, not just a file copy.
2. **Required inputs** — `app/code/columns.py`'s `required_files()`.

## Output filename: `potrank2.csv`, not `PotRank.csv`

Chosen deliberately over reusing the old name: the old `PotRank.csv` arrived via
`sync_rtbi.sh` from a Drive file the Sheet itself wrote. Publishing under the same name before
SM had stopped that Sheet export would have made two writers race on one Drive file. The old
export is now stopped, but the new name stays — it lets old and new be compared side by side
during changeover, and avoids any risk of a stale Sheet trigger reviving the old writer. SM
intends to repoint the Sheet's PotRank import at `potrank2.csv` once satisfied
(`GET /files/potrank2.csv` on the REST API, or the Drive file directly), then this file can be
renamed if wanted — that is a deliberate future decision, not an oversight.

## Refresh: cron + on-demand, same script

Cron (`crontab -l`, server): `25 0-22 * * * /home/sm/potentials/potrank/run_potrank.sh`. Timed
8 minutes after longi's ~:17 publish; potrank reads no `group_conformity` output, so it does not
need to wait for that family's :45/:47 tick.

**Also user-triggerable** (SM, 2026-08-25): `potrank.cmd` on the Windows side runs the *same*
`run_potrank.sh` an "urgent refresh" would need, over SSH — never a separate code path, so a
manual and a scheduled run can't drift apart. Because a manual trigger can now land close to the
cron tick, `run_potrank.sh` takes a non-blocking `flock` on `/tmp/potrank.lock`; a second run
finds it held, prints one line, and exits 0 — this is an expected outcome of the two overlapping,
not a failure. An urgent run still goes through the same preflight vintage check as a scheduled
one: a hurried human refusing a skewed snapshot is exactly when that guard matters most.

## The REST API needs nothing

`repositoryRTBI/api/main.py`'s `GET /files` and `GET /files/{path}` are driven by a plain
`rglob("*.csv")` over `data/`. The moment `potrank2.csv` is published it is downloadable at
`innovia.dk/rtbi-api/files/potrank2.csv` (header `X-API-Key`) with no registration. The richer
`GET /data/{path}` endpoint (ticker/daynum querying) does **not** support it by design — it
requires `int(df.columns[1])`, and potrank2.csv's second column is `RankNow`, not a daynum; it
returns a 400 pointing at `/files/` instead. Correct, not a bug — per-ticker querying of
potrank2.csv would need a small separate change to `main.py`, out of scope here.

## Why not another longi module

`longi_across.py` builds a very similar-shaped file (`across_<daynum>.csv`) but auto-discovers
one column per `longi_*.csv` at a single daynum with the metric's own name as the header.
potrank needs a **fixed, renamed, hand-ordered** column list, three different daynum offsets per
metric, and two computed group-strength columns none of which fit that auto-discovery model —
hence its own family rather than a 30th `longi_across` column.
