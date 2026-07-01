# yf3 Maintenance Notes

## 2026-07-01 — Trading-day index on the stacked file + PotDatML snapshot

**Nightly chain (`start_yf3.sh`):** fetch (`yf3.py`) → stack (`stackYfinanceData.py`) →
snapshot (`makeYfinanceSnapshot.py`). `updgd_yf3.sh` then uploads `app/output_stacked/`
to Drive `PotSystem/repositoryRTBI/Yfinance/` (excludes `.stack_ledger.json`). The daily
`StockData2-*.csv` files are no longer uploaded to Drive — the whole `~/potentials` tree
is backed up to Asustor.

**`stackYfinanceData.py` — Daynum/Date index + dedup.** Each row gets `Daynum` and `Date`
(from `input/Cal.csv`) inserted after `Symbol`; the raw `FetchedDate` is kept. Downstream
index is `(Symbol, Daynum)`; duplicates on that key are collapsed keeping the most recent
FetchedDate.
- Both FetchedDate formats are parsed (`DD-MM-YYYY HH:MM` and ISO).
- **Exchange day-shift** (only valid for the 02:15–02:35 Danish fetch window): whether a
  fetch reflects date D depends on whether the ticker's market has opened by ~02:35.
  `.AX .T .KS` → D (open both seasons); `.HK .SS` and everything else (US no-suffix, EU,
  `.JO`) → D−1; `.SI` → D in Danish winter, D−1 in summer (EU DST via
  `zoneinfo("Europe/Copenhagen")`). The basis date is then backfilled to the most recent
  Cal.csv trading day ≤ basis (also folds weekend/holiday fetches).
- **Idempotent** via a filename ledger `output_stacked/.stack_ledger.json` (not the raw
  FetchedDate, which dedup discards). Re-running with no new source files is a no-op. A
  legacy stacked file without Daynum/Date is migrated on the next run.

**`makeYfinanceSnapshot.py` — `Yfinance.csv`.** One row per ticker at its most-recent
Daynum (robust to fetch gaps), columns `Ticker;Daynum;Target_*;Recommendation_*;
NumberOfAnalysts`. Imported by the **PotDatML** Google Sheet, then `importRange`'d onward.
The `COLUMNS` constant is the single place to route additional fields the same way.
Note: yFinance is a weak source for long-term history — this snapshot is a "today's
picture" companion to PotRank, not a longterm store.

## 2026-06-08 — Improved logging for failed tickers

**Problem:** HTTP 404 errors and failed-ticker messages were buried mid-run among 1000+ `Processing N/N:` lines. The end-of-run summary only said `Failed: N stocks` without naming them (gated on `VERBOSE = True`, which was `False`).

**Changes in `app/code/yf3.py`:**
- Suppressed yfinance's raw `HTTP Error 404: {JSON}` noise via `logging.getLogger('yfinance').setLevel(logging.CRITICAL)`
- Always print failed tickers at end of run (removed `VERBOSE` gate)
- Tickers failing with "Insufficient data" / "No valid data" (i.e. 404 — ticker not found on Yahoo) are now flagged `*** POSSIBLY OBSOLETE / DELISTED ***`
- Failed stocks log file (`Failed_stocks_YYYYMMDD-HHMM.txt`) is now always written to `output/`, not only when `VERBOSE = True`

**Background:** GBRK and similar tickers were causing repeated 404 errors every run. The log gave no clear signal that these needed to be reviewed and removed from the ticker list.
