# Session Wrap - 2026-02-11

## Scope completed
- Phase 1 implemented and executed with 20d target (`future_gain20d.csv`).
- Class setup used:
  - `Win`: gain `> 6.00`
  - `Loss`: gain `< 0.00`
  - `Nothing`: otherwise
- Validation setup used:
  - Out-of-training-range only
  - Walk-forward over latest 10 test daynums

## Main conclusion
- Your conclusion is supported by results: per-stock modeling appears necessary for this Phase 1 setup.
- Per-stock notably reduces blunt errors where a real `Win` is predicted as `Loss`.

## Runs and key outputs

### 1) Global model, no trim
- Run: `EXP-2026-02-11-001`
- Files: `app/output/exp/EXP-2026-02-11-001/`
- Summary:
  - `n_pred_rows_total`: 10920
  - `accuracy_pred_rows_overall`: 0.4293
  - `first_order_error_total`: 3552
  - `second_order_error_total`: 276
  - `signal_vs_nothing_error_total`: 2404

### 2) Per-stock model, no trim (plus global outputs)
- Run: `EXP-2026-02-11-002`
- Files: `app/output/exp/EXP-2026-02-11-002/`
- Per-stock summary:
  - `n_pred_rows_total`: 10800
  - `n_no_pred_rows_total`: 120
  - `accuracy_pred_rows_overall`: 0.6103
  - `first_order_error_total`: 1459
  - `second_order_error_total`: 1383
  - `signal_vs_nothing_error_total`: 1367

### 3) Global model, trim 5%
- Run: `EXP-2026-02-11-003`
- Files: `app/output/exp/EXP-2026-02-11-003/`
- Summary:
  - `n_pred_rows_total`: 4075
  - `n_no_pred_rows_total`: 6845
  - `accuracy_pred_rows_overall`: 0.4027
  - `first_order_error_total`: 1362
  - `second_order_error_total`: 61
  - `signal_vs_nothing_error_total`: 1011

### 4) Per-stock model on 50d target, Win > 10 (plus global outputs)
- Run: `EXP-2026-02-11-004`
- Files: `app/output/exp/EXP-2026-02-11-004/`
- Setup:
  - Target: `future_gain50d.csv`
  - Class setup: `Win > 10.00`, `Loss < 0.00`, `Nothing` otherwise
  - Per-stock enabled: `min_stock_samples=150`
  - Walk-forward: latest 10 daynums
- Per-stock summary:
  - `n_pred_rows_total`: 10792
  - `n_no_pred_rows_total`: 118
  - `accuracy_pred_rows_overall`: 0.7099
  - `first_order_error_total`: 696
  - `second_order_error_total`: 1236
  - `signal_vs_nothing_error_total`: 1199
- Global summary (same run):
  - `n_pred_rows_total`: 10910
  - `n_no_pred_rows_total`: 0
  - `accuracy_pred_rows_overall`: 0.3647
  - `first_order_error_total`: 3704
  - `second_order_error_total`: 1054
  - `signal_vs_nothing_error_total`: 2173

## Blunt error detail (from prediction files)
- Definition used here:
  - `Win->Loss`: real `Win`, predicted `Loss`
  - `Loss->Win`: real `Loss`, predicted `Win`

### Global no trim (`EXP-2026-02-11-001`)
- `Win->Loss`: 3222 / 3616 true Wins = 89.10%
- `Loss->Win`: 330 / 4601 true Losses = 7.17%
- First-order error total rate: 3552 / 10920 = 32.53%

### Per-stock no trim (`EXP-2026-02-11-002`, per-stock predictions)
- `Win->Loss`: 1020 / 3588 true Wins = 28.43%
- `Loss->Win`: 439 / 4525 true Losses = 9.70%
- First-order error total rate: 1459 / 10800 = 13.51%

Interpretation:
- The severe blunt error `Win->Loss` drops strongly under per-stock modeling.
- `Loss->Win` rises somewhat, but total first-order error drops materially.

## Files changed this session
- `app/code_exp/exp_phase1_multinomial_20d.py`
- `PROJECT_EXP.md`
- `app/output/exp/EXP-2026-02-11-001/*`
- `app/output/exp/EXP-2026-02-11-002/*`
- `app/output/exp/EXP-2026-02-11-003/*`
- `app/output/exp/EXP-2026-02-11-004/*`
- `app/output/exp/SESSION_WRAP_2026-02-11.md`

## Resume commands for later
- Re-run global baseline:
```powershell
python app/code_exp/exp_phase1_multinomial_20d.py --exp-id EXP-2026-02-11-001 --n-test-days 10
```
- Re-run per-stock baseline:
```powershell
python app/code_exp/exp_phase1_multinomial_20d.py --exp-id EXP-2026-02-11-002 --n-test-days 10 --run-per-stock --min-stock-samples 150
```
- Re-run trim-5 global:
```powershell
python app/code_exp/exp_phase1_multinomial_20d.py --exp-id EXP-2026-02-11-003 --n-test-days 10 --trim-percent 5
```
- Re-run 50d per-stock (Win > 10):
```powershell
python app/code_exp/exp_phase1_multinomial_20d.py --exp-id EXP-2026-02-11-004 --n-test-days 10 --run-per-stock --min-stock-samples 150 --target-file future_gain50d.csv --win-threshold 10
```

## Final wrap-up for today
- Phase 1 is closed with working per-stock probability models for both 20d and 50d targets.
- Operational scripts are now in place:
  - `app/code/aux_win-loss.py` -> `app/output/aux_win-loss.csv` (daily production)
  - `app/code/QA_win-loss.py` -> `app/output/QA/*` (quality assurance)
- `longi.py` includes daily production generation (`win_loss` module).
- A full day-2081 prototype over all non-caret tickers has been produced and validated:
  - `app/output/exp/PHASE1_SUMMARY_2026-02-11/PHASE1_PRODUCTION_PROTOTYPE_day2081_all_non_caret.csv`

## Ready state for next phases
- Baseline for comparison is fixed:
  - 20d: Win>6, Loss<0
  - 50d: Win>10, Loss<0
  - walk-forward newest 10 daynums
  - per-stock min history 150
- Next investigations can proceed under these fixed baseline assumptions:
  - Phase 2: PCA reduced models
  - Phase 3: categorization / bayes-style models
  - Phase 4: pattern/neural input structures
