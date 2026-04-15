# Longi Project - Experiment Index

Use this file for short-lived experimental work. Keep stable system facts in `PROJECT_CONTEXT.md`.

## Rules
- Put experimental code in `app/code_exp/`
- Put experiment outputs in `app/output/exp/<EXP-ID>/`
- Keep one folder per experiment run or run family
- Record reproducibility metadata (git commit, command, inputs, seed)
- Promote successful experiments into `app/code/` and then update `PROJECT_CONTEXT.md`

## Experiment Table
| EXP-ID | Date | Owner | Status | Hypothesis | Code | Output | Notes |
|---|---|---|---|---|---|---|---|
| EXP-2026-02-11-001 | 2026-02-11 | sm | done | Global multinomial model on 20d target gives measurable out-of-range signal over latest 10 daynums | `app/code_exp/exp_phase1_multinomial_20d.py` | `app/output/exp/EXP-2026-02-11-001/` | Win>6, Loss<0, Nothing otherwise; no trim; global only |
| EXP-2026-02-11-002 | 2026-02-11 | sm | done | Per-stock multinomial model with minimum history can improve predicted-row accuracy vs global model | `app/code_exp/exp_phase1_multinomial_20d.py` | `app/output/exp/EXP-2026-02-11-002/` | Includes global + per-stock outputs; `min_stock_samples=150`; 10 daynums |
| EXP-2026-02-11-003 | 2026-02-11 | sm | done | 5%/95% X-value trim reduces exposure and may reduce first-order errors | `app/code_exp/exp_phase1_multinomial_20d.py` | `app/output/exp/EXP-2026-02-11-003/` | Global only; trim=5%; many rows marked no prediction |
| EXP-2026-02-11-004 | 2026-02-11 | sm | done | 50d target with stricter Win threshold may improve per-stock signal quality | `app/code_exp/exp_phase1_multinomial_20d.py` | `app/output/exp/EXP-2026-02-11-004/` | Target `future_gain50d.csv`; Win>10, Loss<0; includes global + per-stock; `min_stock_samples=150`; 10 daynums |
| EXP-YYYY-MM-DD-001 | YYYY-MM-DD | initials | planned/running/done/promoted/archived | short statement | `app/code_exp/<script>.py` | `app/output/exp/<EXP-ID>/` | one line |

## Status Definitions
- `planned`: defined but not run
- `running`: currently being executed
- `done`: completed and evaluated
- `promoted`: moved to production path (`app/code/`)
- `archived`: kept for reference, not active

## In prediction experiments the following data are relevant
- As independent variable (X-values)
longi_beta3m.csv
longi_coreindex.csv
longi_coreindexRSI.csv
longi_GICS_3m.csv
longi_ma10.csv
longi_ma20.csv
longi_ma50.csv
longi_macd_signal.csv
longi_median_10d.csv
longi_median_30d.csv
longi_median_50d.csv
longi_PdivMA50.csv
longi_per1m.csv
longi_per3m.csv
longi_rsi.csv
longi_Sector2_3m.csv
longi_sh3m.csv
longi_spr100d.csv
longi_stepup100.csv
longi_stepup40.csv
longi_vola100d.csv
longi_vola20d.csv
- As result variables (Y-values)
future_gain20d.csv
future_gain50d.csv

## Planning
### Basic thoughts
My overarching goal is to help users of Potentials data to select stocks for add/buy (or hold/reduce). I want to build the best possible rules for doing this. Advice can be probability based (for example P(Win), P(Loss), P(Nothing)) with clear decision rules. Independent variables are indicators or their deciles, optionally after outlier filtering (marked as "unpredictable"). Models are evaluated on recent daynums while training only on older daynums.

### Phase 1 (completed): Probabilistic Per-Stock Models (20d and 50d)
**Aim**
- Build an out-of-training-range classification model that outputs per-ticker probabilities `P(Win)`, `P(Loss)`, and `P(Nothing)` for actionable decision support.
- Test whether ticker-specific models materially reduce blunt errors versus one global model.
- Deliver a production-style prototype for newest daynum scoring (`daynum=2081`) across the stock universe (excluding caret-prefixed tickers).

**Methodology**
- Features (X): 22 indicator files listed above (technical/relative strength/performance/risk signals).
- Targets and class definitions:
  - 20d: `future_gain20d.csv`, `Win > 6`, `Loss < 0`, `Nothing` otherwise.
  - 50d: `future_gain50d.csv`, `Win > 10`, `Loss < 0`, `Nothing` otherwise.
- Model: multinomial softmax regression (L2 regularization), trained per walk-forward split.
- Validation protocol:
  - Strict walk-forward on newest 10 daynums.
  - Train only on older daynums (`daynum < test_daynum`), no leakage.
  - Out-of-training-range evaluation only.
- Per-stock setup:
  - Minimum history per ticker: `min_stock_samples=150`.
  - If insufficient history or out-of-range feature value after trim (when enabled), return no prediction.
- Error tracking:
  - First-order: predicted `Win` when actual `Loss`, or predicted `Loss` when actual `Win`.
  - Second-order: predicted `Nothing` when actual `Win`/`Loss`.
  - Signal-vs-nothing: predicted `Win`/`Loss` when actual `Nothing`.

**Outcome**
- `EXP-2026-02-11-001` (global, 20d, no trim):
  - Accuracy `0.4293`, first-order error `3552/10920`.
- `EXP-2026-02-11-002` (per-stock, 20d, no trim):
  - Accuracy `0.6103`, first-order error `1459/10800`.
  - Major reduction in blunt error `Win<->Loss` errors versus global baseline.
- `EXP-2026-02-11-003` (global, 20d, trim 5%):
  - Accuracy `0.4027`, first-order `1362/4075`, but many no-predictions (`6845`).
- `EXP-2026-02-11-004` (per-stock, 50d, Win>10):
  - Accuracy `0.7099`, first-order `696/10792`.
- Prototype delivered:
  - `app/output/exp/PHASE1_SUMMARY_2026-02-11/PHASE1_PRODUCTION_PROTOTYPE_day2081_all_non_caret.csv`
  - Universe coverage: 1104 non-caret tickers, with probabilities produced for 1080 tickers on both 20d and 50d models.
  - Output includes side-by-side `pred_label`, `P_win`, and `P_loss` for 20d and 50d, sorted by `P_win_20d`.

## End-of-Day Handoff (2026-02-11)
### What is operational now
- Daily production output:
  - Script: `app/code/aux_win-loss.py`
  - Output: `app/output/aux_win-loss.csv`
  - Scope: all non-caret tickers, newest daynum, alphabetical ticker order
- QA package:
  - Script: `app/code/QA_win-loss.py`
  - Output dir: `app/output/QA/`
  - Focus: split-level and ticker-level validity/error diagnostics
- Pipeline integration:
  - `longi.py` now includes `aux_win-loss.py` (`win_loss` module)

### Default operations commands
- Daily production:
```powershell
python app/code/aux_win-loss.py
```
- QA check:
```powershell
python app/code/QA_win-loss.py
```

### Next phase startup checklist
- Freeze Phase 1 baseline settings for comparability:
  - 20d classes: Win>6, Loss<0, Nothing otherwise
  - 50d classes: Win>10, Loss<0, Nothing otherwise
  - Validation: 10 newest daynums, walk-forward, no leakage
  - Per-stock minimum history: 150 rows
- Use `app/output/aux_win-loss.csv` as daily reference output while testing next-phase variants.
- For each next-phase run, record in Experiment Table:
  - hypothesis, code path, output folder, parameter values, and summary metrics.

### Phase 2: PCA
reduced models

### Phase 3: Categorization model / bayes-style reasoning

### Phase 4: Pattern/neural network
3-day matrix flattened and used as input
