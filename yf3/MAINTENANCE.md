# yf3 Maintenance Notes

## 2026-06-08 — Improved logging for failed tickers

**Problem:** HTTP 404 errors and failed-ticker messages were buried mid-run among 1000+ `Processing N/N:` lines. The end-of-run summary only said `Failed: N stocks` without naming them (gated on `VERBOSE = True`, which was `False`).

**Changes in `app/code/yf3.py`:**
- Suppressed yfinance's raw `HTTP Error 404: {JSON}` noise via `logging.getLogger('yfinance').setLevel(logging.CRITICAL)`
- Always print failed tickers at end of run (removed `VERBOSE` gate)
- Tickers failing with "Insufficient data" / "No valid data" (i.e. 404 — ticker not found on Yahoo) are now flagged `*** POSSIBLY OBSOLETE / DELISTED ***`
- Failed stocks log file (`Failed_stocks_YYYYMMDD-HHMM.txt`) is now always written to `output/`, not only when `VERBOSE = True`

**Background:** GBRK and similar tickers were causing repeated 404 errors every run. The log gave no clear signal that these needed to be reviewed and removed from the ticker list.
