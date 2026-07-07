# Handoff: Experimental sandbox for front-loading, fit quality, and model composition (Win/Loss system)

**Audience:** Claude Code, working in the PotSystem repo on gandalf. **Nature of the job:** DEVELOPMENT OF EXPERIMENTAL MODULES. This is a sideline laboratory next to a running production system.

---

## Ground rules — read before writing any code

1. **Production is untouchable.** Do not modify, rename, or move: `app/code/longi_winloss_probs.py`, `app/code/aux_winloss_shared.py`, `orchestrator.sh`, any cron configuration, or any file under `app/output/` or `app/input/`. The embargo (label look-ahead) fix is ALREADY applied in production — do not re-apply or "improve" it there.  
2. **All new code lives in a new directory** `app/exp/`. All experimental outputs go to `app/exp/output/` with filenames prefixed `exp_`. Production directories are read-only inputs.  
3. **Import vs. fork rule:** import stable read-only helpers from `aux_winloss_shared` (`read_indicator_matrix`, `stack_non_null`, `ensure_files_exist`, `TargetSpec`, `TARGET_SPECS`, `FEATURE_FILES`, `CLASS_NAMES`, `CLASS_TO_INT`, `label_from_gain`, `build_feature_frame`, `build_labeled_dataset`, `compute_error_counts`, `get_*_from_potdat`). Fork (copy into `exp_shared.py` and extend) only the fit function, which must change. Never edit the production module to make an import easier — copy instead and mark the copy with a comment `# forked from aux_winloss_shared vN, extended for experiments`.  
4. **No production-format collisions.** Experimental matrices keep longi layout (see conventions) for easy side-by-side comparison in Excel, but always the `exp_` prefix and parameter suffix, e.g. `exp_longi_P20d_win_H63.csv`. Equal-weight runs use suffix `_Hnone`.  
5. **Every run writes/updates a manifest** `app/exp/output/manifest.txt`: append one line per run — ISO date, script name, full argument list, wall-clock seconds, daynums covered.  
6. Work phase by phase; stop and report after each phase with acceptance evidence before continuing. Ask before deviating from names, flags, or formats.

### Repo conventions (same as production)

- CSV: semicolon separator, comma decimals. Read `sep=";", decimal=","`. Blank cell \= not calculable. 3 decimals for probabilities/metrics (comma decimal, blank for NaN — copy the `format_prob` pattern into `exp_shared.py`).  
- longi matrix layout: ticker rows in PotDat source order, daynum columns in PotDat header order (newest-first). Caret tickers (`^...`) always blank.  
- Per-ticker minimum training data: 150 (see effective-sample gate in Phase 2).  
- Never a `;` inside a cell value; multi-part cells use `|`.  
- Embargoed training filter everywhere in experimental fitting: `data["daynum"] <= daynum_case - horizon_days` (production already does this; experiments must match so comparisons are honest).

### Background (context for the agent)

Production fits, per (ticker, daynum) cell, a fresh 3-class softmax (`Loss=0, NoLoss=1, Win=2`) on that ticker's embargoed history: sklearn `Pipeline(StandardScaler → LogisticRegression(solver="newton-cholesky", C=1/reg_lambda))`, 20 indicator features (`FEATURE_FILES`), targets `future_gain20d/50d.csv` with hurdles 6%/10%. Production emits `longi_P{20d,50d}_{win,loss}.csv`. The experiments investigate: (a) exponential recency weighting of training rows (half-life), (b) per-cell fit quality (in-sample and realized), (c) per-cell model composition (top driving indicators), plus per-day cross-sections, and A/B comparison against production's own probability files.

---

## Phase 1 — `app/exp/exp_shared.py`: extended fit core

**Purpose:** one module owning everything experimental scripts share; the only place the fit logic is forked.

Contents:

1. `fit_predict_multinomial_ext(x_train, y_train, x_test, reg_lambda, max_iter, *, sample_weight=None)` → `(y_pred, probs_full, FitDiagnostics)`. Fork of the production function, extended:  
   - Normalize weights before fitting so mean weight \= 1.0 (protects L2 strength: sklearn balances the penalty against the raw weighted loss sum; unnormalized decayed weights would silently strengthen regularization): `sample_weight = sample_weight * (len(sample_weight) / sample_weight.sum())`  
   - Fit via `pipeline.fit(x_train, y_train, clf__sample_weight=sample_weight)` (the `clf__` prefix routes the kwarg to the LogisticRegression step; `None` passes through legally).  
   - Keep the production single-class early exit; in that branch return `FitDiagnostics(pipeline=None, train_probs=None)`.

```py
@dataclass
class FitDiagnostics:
    pipeline: Optional[Pipeline]        # fitted, or None for degenerate fits
    train_probs: Optional[np.ndarray]   # predict_proba(x_train), expanded to full 3-class layout like probs_full
```

2. `exp_weights(ages: np.ndarray, half_life: Optional[float]) -> Optional[np.ndarray]` — `0.5 ** (ages / half_life)`, or `None` for equal weighting.  
3. `effective_n(w) -> float` — `(w.sum()**2) / (w*w).sum()`; returns raw length when `w is None`.  
4. `mcfadden_r2(y_train, train_probs, sample_weight=None) -> float` — weighted mean cross-entropy of the model vs. a null model predicting the (weighted) class base rates; `1 - ll_model/ll_null`; NaN when degenerate or `ll_null <= 0`; eps \= 1e-12 inside logs.  
5. `top_drivers(pipeline, x_row, target_class_int, feature_cols, k=3) -> Optional[str]` — exact logit decomposition: `contrib = clf.coef_[row_of_class] * scaler.transform(x_row)[0]`; top-k by |contrib|; cell string like `+rsi|-ma50|+beta3m` (sign \= push direction, `longi_` prefix stripped). Return `None` (→ blank) when: pipeline is None, requested class absent from `clf.classes_`, or the fit was binary (`len(clf.classes_) == 2`, where sklearn stores one coefficient row with different semantics — blank is the accepted handling; count and report how often it occurs).  
6. `format_cell(value, decimals=3)` — copied comma-decimal formatter; strings pass through untouched.  
7. Matrix I/O helpers for exp files: reuse-by-copy of production's overlay read/write pattern (`read_existing_matrix_cells`, `write_probability_matrix`) so partial runs update columns without destroying others.

**Acceptance:**

- `pytest`\-style or inline `__main__` self-test on synthetic data: (i) `sample_weight=np.ones(n)` reproduces the unweighted fit's coefficients to tolerance; (ii) strong decay produces different coefficients; (iii) `effective_n` of equal weights \= n; (iv) `mcfadden_r2` \= 0.0 when model probs equal base rates, \> 0 for an informative synthetic signal; (v) `top_drivers` returns 3 signed tokens matching regex `^[+-]\w+(\|[+-]\w+){2}$`.  
- No production file modified (`git status` clean outside `app/exp/`).

## Phase 2 — `app/exp/exp_winloss_probs.py`: experimental scorer

**Purpose:** the experimental twin of the production scorer — same cell semantics, plus half-life weighting and the two new per-cell artifacts, writing parameter-stamped exp files.

Spec:

1. Flags: `--half-life H` (float, optional; omitted \= equal weighting, suffix `_Hnone`), `--daynum N`, `--backfill-all`, `--max-daynums N`, `--min-stock-samples` (default 150), `--reg-lambda` (default 0.01), `--max-iter` (default 1000). Default mode with no daynum flags \= newest daynum only (fast; mirrors production behavior for easy same-night comparison).  
2. Per (ticker, daynum, horizon) cell, using embargoed training (`<= daynum_case - horizon_days`):  
   - `ages = daynum_case - train_daynums`; `w = exp_weights(ages, half_life)`.  
   - **Effective-sample gate:** blank the cell when `effective_n(w_of_this_ticker) < min_stock_samples` (reduces to the raw-count gate when equal weighting). Count gate-blanked cells separately from raw-count-blanked and report both.  
   - **Class-starvation guard:** if any class present in `y_train` carries \< `MIN_CLASS_WEIGHT_SHARE = 0.01` of total weight, drop its rows for this cell (it then flows through the existing missing-class expansion). Module-level constant with explanatory comment.  
   - Fit once via `fit_predict_multinomial_ext`; from the single fit extract: `p_win`, `p_loss`, `mcfadden_r2`, win-driver string, loss-driver string. One fit feeds all five outputs — no refitting.  
3. Output files per horizon (suffix `_H{int(H)}` or `_Hnone`): `exp_longi_P{h}_win_*`, `exp_longi_P{h}_loss_*`, `exp_longi_fitR2_{h}_*`, `exp_longi_drivers{h}_win_*`, `exp_longi_drivers{h}_loss_*` (h ∈ {20d, 50d}). All longi layout in `app/exp/output/`.  
4. Startup banner echoes half-life, mode, gates; end-of-run summary prints cells scored/blanked and appends the manifest line.

**Acceptance:**

- `--daynum <newest>` with no `--half-life`: `exp_longi_P20d_win_Hnone.csv` newest column matches production `longi_P20d_win.csv` for the same daynum to 3 decimals (proves the fork is faithful). Report any mismatches with examples.  
- `--daynum <newest> --half-life 63` runs; probabilities differ from `_Hnone`, remain valid (each in \[0,1\], win+loss ≤ 1 per cell).  
- Driver cells match the sign-token regex; fitR2 values plausible (report cross-ticker median).  
- Runtime for one daynum reported; expected within \~1.2× of production's per-daynum time.

## Phase 3 — `app/exp/exp_winloss_quality.py`: realized quality \+ A/B vs production

**Purpose:** score predictions against what actually happened. Pure arithmetic on files — no fitting, runs in seconds. Scores BOTH production matrices and any experimental variant with identical code, enabling honest A/B.

Spec:

1. Flag `--source {prod, H63, Hnone, ...}`: `prod` reads `app/output/longi_P*` (read-only); anything else reads the matching `exp_longi_P*_{source}.csv`. Multiple `--source` values allowed in one run.  
2. Reconstruct `p_noloss = 1 - p_win - p_loss` (clamp tiny negative rounding artifacts to 0, renormalize). Realized class via imported `label_from_gain` on `future_gain{20d,50d}.csv` — never duplicate threshold logic.  
3. Outputs per source and horizon: `exp_longi_logloss_{h}_{source}.csv` (per-cell `-log(p_realized + 1e-12)`; ln 3 ≈ 1.099 \= "uniform ignorance" reference) and `exp_longi_brier_{h}_{source}.csv` (`sum((p_k - onehot_k)^2)`, range \[0,2\]). Blank when probability cell blank or outcome not yet known (newest `horizon` columns are blank by construction — this is correct, not a bug).  
4. Cross-sectional summary `exp_day_summary_{source}.csv`, tidy long format, one row per (daynum, horizon, metric): `n_scored`, `median_p_win`, `median_p_loss`, `median_fitR2` (exp sources only), `mean_logloss`, `mean_brier`, `top_driver_1..3` as `name:count` (exp sources only; from first token of win-driver strings). Replace rows by key on rerun; keep sorted daynum-descending.  
5. End-of-run comparison table when multiple sources given: per horizon, mean log-loss per source side by side, plus per-source mean (fitR2 − realized-quality proxy) gap note — the A-vs-B overfitting signal.

**Acceptance:**

- Full-history scoring of `prod` completes in seconds (report timing) and touches nothing under `app/output/`.  
- One hand-verified cell: recompute log-loss manually from the three probabilities and realized gain; match to 3 decimals.  
- Newest 20 (resp. 50\) columns blank in the logloss matrices.

## Phase 4 — `app/exp/qa_halflife_grid.py`: the half-life experiment

**Purpose:** choose H with data, not taste. Walk-forward evaluation over recent history comparing H ∈ {63, 126, 252, None}.

Spec:

1. Flags: `--grid` (comma list, default `63,126,252,none`), `--last-daynums` (default 250), `--tickers` (comma list, optional — smoke runs), `--horizons` (default `20d,50d`).  
2. For each H, each scoreable daynum in the window, each ticker: embargoed training, weighted fit via `exp_shared`, predict the held-out day, accumulate `compute_error_counts` (imported from production) and realized log-loss.  
3. Output `exp_qa_halflife_results.csv`: one row per (H, horizon) — first/second/signal-vs-nothing error totals, mean log-loss, cells scored, wall-clock. Print a ranked table (rank by mean log-loss; show error counts alongside).  
4. Docstring warning: full grid ≈ 4× a full backfill in compute. Recommend: smoke run first (`--tickers` with \~5 names, `--last-daynums 20`), then per-horizon full runs. Never wire into cron.

**Acceptance:**

- Smoke run (5 tickers × 20 daynums × full grid) completes; table renders; `none` column reproduces equal-weight behavior.  
- Manifest lines written for every run.

## Phase 5 — Final report

Summarize: files created (all under `app/exp/`), flags per script, output-file naming scheme with one-line meaning each, measured runtimes (one-daynum scoring per H; quality scoring; smoke grid), fidelity-check result (Phase 2, exp `_Hnone` vs production), and confirmation via `git status` that nothing outside `app/exp/` changed.

**Explicitly out of scope (do not do):** modifying production scripts or orchestrator/cron; regenerating production matrices; "promoting" any experimental feature into production — promotion is a separate future task performed as a deliberate rewrite once the experiments have picked winners.  
