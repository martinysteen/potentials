"""
stackYfinanceData.py

Stacks all daily StockData2*.csv files from ../output/ into a single
long-form CSV at ../output_stacked/StockData2_stacked.csv.

On top of stacking, each row is given a trading-day index derived from Cal.csv:

  * FetchedDate (the raw fetch timestamp, kept for provenance) is converted into
    two new columns inserted after Symbol:
        Daynum : integer trading-day number from Cal.csv
        Date   : the matching trading date (YYYY-MM-DD) from Cal.csv
  * (Symbol, Daynum) is the intended downstream index. Duplicate rows on that key
    are collapsed, keeping the row with the most recent FetchedDate.

Exchange day-shift (valid only for the 02:15-02:35 Danish-time fetch window):
whether a fetch reflects date D or the previous session depends on whether the
ticker's home market has opened by ~02:35 Danish time.

    Suffix              Market                       Basis
    .AX .T .KS          Sydney, Tokyo, Korea         D        (open both seasons)
    .HK .SS             Hong Kong, Shanghai          D-1      (not open either season)
    .SI                 Singapore                    winter -> D, summer -> D-1
    everything else     US (no suffix), .L, .JO, EU  D-1

The chosen basis date is then resolved to a trading day via a backfill lookup in
Cal.csv (most recent trading date <= basis), which also folds weekend/holiday
fetches onto the correct trading day.

Incremental & idempotent: a ledger (../output_stacked/.stack_ledger.json) records
which source files have already been folded in, so each run only reads genuinely new
StockData2*.csv files and re-running with no new files leaves the stacked file
untouched. Because the ledger is keyed on source filename (not on surviving rows), it
stays correct even though dedup discards older duplicate fetches. The stacked file is
the durable accumulation: rows persist even after their source file is later removed
from ../output/. If the existing stacked file predates the Daynum/Date columns, it is
migrated on the next run (the one-time conversion of the legacy file).

Stale (all-blank) records -- rows where every column except Symbol/Daynum/Date/
FetchedDate is blank, i.e. a fetch attempt that returned no data -- are dropped
after dedup, across the whole table regardless of Daynum. The count removed is
printed. The final file is written sorted by FetchedDate descending, Symbol
ascending.
"""

import glob
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

OUTPUT_DIR   = '../output/'
STACKED_FILE = '../output_stacked/StockData2_stacked.csv'
LEDGER_FILE  = '../output_stacked/.stack_ledger.json'
CAL_FILE     = '../input/Cal.csv'

CSV_PARAMS = dict(sep=';', decimal=',', encoding='utf-8')

# Exchange suffixes whose market has opened by the ~02:35 Danish fetch time in both
# seasons -> the fetch reflects date D itself.
SAME_DAY_SUFFIXES   = {'AX', 'T', 'KS'}
# Season-dependent: Danish winter -> D (open), Danish summer -> D-1 (not yet open).
SEASON_DEP_SUFFIXES = {'SI'}
# All other suffixes (incl. HK, SS) and US no-suffix -> D-1.

_CPH = ZoneInfo('Europe/Copenhagen')


def _is_danish_summer(day: pd.Timestamp) -> bool:
    """True if the given calendar date is in Danish summer time (CEST, UTC+2).

    Evaluated at local noon to stay clear of the 02:00-03:00 DST transition gap.
    """
    off = datetime(day.year, day.month, day.day, 12, tzinfo=_CPH).utcoffset()
    return off == timedelta(hours=2)


def load_cal() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return sorted (dates64, daynums_int, datestrings) arrays from Cal.csv."""
    cal = pd.read_csv(CAL_FILE, **CSV_PARAMS)
    cal = cal.dropna(subset=['Date', 'Daynum']).copy()
    cal['Date'] = cal['Date'].astype(str).str.strip()
    cal['_dt'] = pd.to_datetime(cal['Date'], format='%Y-%m-%d')
    cal = cal.sort_values('_dt')
    return (cal['_dt'].values,
            cal['Daynum'].astype(int).values,
            cal['Date'].to_numpy())


def parse_fetched(fd_series: pd.Series) -> pd.Series:
    """Parse FetchedDate (both 'DD-MM-YYYY HH:MM' and ISO forms) to datetime64."""
    fd = fd_series.astype(str).str.strip()
    dt = pd.to_datetime(fd, format='%d-%m-%Y %H:%M', errors='coerce')
    miss = dt.isna()
    if miss.any():
        # ISO ('YYYY-MM-DD HH:MM[:SS]') and any other pandas-inferable form.
        dt.loc[miss] = pd.to_datetime(fd[miss], errors='coerce')
    return dt


def add_daynum_date(df: pd.DataFrame, cal: tuple) -> pd.DataFrame:
    """Add Daynum/Date (from Cal.csv, with exchange day-shift) after Symbol.

    Rows with an unparseable FetchedDate or a basis date before Cal.csv's range
    are dropped with a warning.
    """
    cal_dt, cal_daynum, cal_datestr = cal
    df = df.copy()

    dt = parse_fetched(df['FetchedDate'])
    bad = dt.isna()
    if bad.any():
        print(f'  add_daynum_date: dropping {int(bad.sum())} rows with unparseable FetchedDate')
        df = df.loc[~bad]
        dt = dt.loc[~bad]

    day = dt.dt.normalize()
    suffix = df['Symbol'].astype(str).str.extract(r'\.([^.]+)$', expand=False).fillna('')

    same_day = suffix.isin(SAME_DAY_SUFFIXES)
    si       = suffix.isin(SEASON_DEP_SUFFIXES)

    # Default basis = D; shift back one calendar day for the "other" markets.
    basis = day.copy()
    other = ~same_day & ~si
    basis.loc[other] = day.loc[other] - pd.Timedelta(days=1)
    if si.any():
        summer = day.loc[si].map(_is_danish_summer)
        shift_idx = summer.index[summer.to_numpy()]
        basis.loc[shift_idx] = basis.loc[shift_idx] - pd.Timedelta(days=1)

    # Backfill lookup: most recent trading day in Cal.csv with Date <= basis.
    idx = np.searchsorted(cal_dt, basis.to_numpy(), side='right') - 1
    valid = idx >= 0
    if (~valid).any():
        print(f'  add_daynum_date: dropping {int((~valid).sum())} rows before Cal.csv range')
    safe = idx.clip(min=0)

    df['Daynum'] = cal_daynum[safe]
    df['Date']   = cal_datestr[safe]
    df = df.loc[valid]

    # Place Daynum/Date right after Symbol.
    cols = df.columns.tolist()
    for c in ('Symbol', 'Daynum', 'Date'):
        cols.remove(c)
    return df[['Symbol', 'Daynum', 'Date'] + cols]


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per (Symbol, Daynum): the most recent FetchedDate."""
    tmp = df.assign(_ts=parse_fetched(df['FetchedDate'])).sort_values('_ts')
    tmp = tmp.drop_duplicates(subset=['Symbol', 'Daynum'], keep='last')
    return tmp.drop(columns='_ts').reset_index(drop=True)


_ID_COLS = ('Symbol', 'Daynum', 'Date', 'FetchedDate')


def drop_stale(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop rows where every content column (all but Symbol/Daynum/Date/
    FetchedDate) is blank -- a failed fetch that carries no data. Applies
    across the whole table regardless of Daynum.
    """
    content_cols = [c for c in df.columns if c not in _ID_COLS]
    stale = df[content_cols].isna().all(axis=1)
    return df.loc[~stale].reset_index(drop=True), int(stale.sum())


def sort_output(df: pd.DataFrame) -> pd.DataFrame:
    """Final on-disk row order: FetchedDate descending, Symbol ascending."""
    ts = parse_fetched(df['FetchedDate'])
    return (df.assign(_ts=ts)
              .sort_values(['_ts', 'Symbol'], ascending=[False, True])
              .drop(columns='_ts')
              .reset_index(drop=True))


def load_stacked(cal: tuple) -> tuple[pd.DataFrame | None, bool]:
    """Return (existing_df_or_None, migrated_flag).

    If the existing file lacks the Daynum/Date columns it is transformed here
    (the one-time migration of the legacy stacked file).
    """
    if not os.path.exists(STACKED_FILE):
        return None, False
    df = pd.read_csv(STACKED_FILE, **CSV_PARAMS)
    if 'Daynum' not in df.columns or 'Date' not in df.columns:
        print(f'load_stacked: migrating legacy stacked file ({len(df)} rows)')
        return add_daynum_date(df, cal), True
    return df, False


def load_ledger() -> set:
    """Set of source basenames already folded into the stacked file."""
    if not os.path.exists(LEDGER_FILE):
        return set()
    with open(LEDGER_FILE, encoding='utf-8') as fh:
        return set(json.load(fh))


def save_ledger(names: set) -> None:
    with open(LEDGER_FILE, 'w', encoding='utf-8') as fh:
        json.dump(sorted(names), fh, indent=0)


def main():
    cal = load_cal()
    existing_df, migrated = load_stacked(cal)
    ledger = load_ledger()
    ledger_exists = os.path.exists(LEDGER_FILE)

    source_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'StockData2*.csv')))
    if not source_files and existing_df is None:
        print('stackYfinanceData: no source files found in', OUTPUT_DIR)
        return

    # First run under the ledger scheme (no ledger yet): fold in every source file so
    # the accumulation is rebuilt deterministically. Afterwards: only unseen files.
    if ledger_exists:
        todo = [p for p in source_files if os.path.basename(p) not in ledger]
    else:
        todo = source_files

    new_frames = []
    for path in todo:
        try:
            df = pd.read_csv(path, **CSV_PARAMS)
        except Exception as e:
            print(f'stackYfinanceData: could not read {path}: {e}')
            continue
        new_frames.append(add_daynum_date(df, cal))

    if not new_frames and not migrated:
        total = len(existing_df) if existing_df is not None else 0
        print(f'stackYfinanceData: no new source files - stacked file has {total} rows')
        # Only rewrite the ledger if it is genuinely missing entries (keeps true
        # no-op runs write-free and idempotent).
        full = ledger | {os.path.basename(p) for p in source_files}
        if full != ledger:
            save_ledger(full)
        return

    # Existing rows first, then new frames in filename order, so equal-FetchedDate
    # ties resolve deterministically toward the freshest source file.
    frames = ([existing_df] if existing_df is not None else []) + new_frames
    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    result = dedupe(combined)
    result, n_stale = drop_stale(result)
    result = sort_output(result)

    os.makedirs(os.path.dirname(STACKED_FILE), exist_ok=True)
    result.to_csv(STACKED_FILE, sep=';', decimal=',', index=False, encoding='utf-8')
    save_ledger(ledger | {os.path.basename(p) for p in source_files})

    added = sum(len(f) for f in new_frames)
    print(f'stackYfinanceData: {len(todo)} source file(s), {added} rows; '
          f'combined {before} -> {len(result)} after dedup '
          f'({before - len(result) - n_stale} removed), '
          f'{n_stale} stale (all-blank) record(s) removed'
          + ('  [legacy file migrated]' if migrated else ''))


if __name__ == '__main__':
    main()
