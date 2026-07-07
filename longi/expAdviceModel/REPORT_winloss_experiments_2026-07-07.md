# Report: Win/Loss experimental sandbox — front-loading, fit quality, model composition

**Date:** 2026-07-07
**Scope:** Implementation of all 5 phases of `HANDOFF_winloss_experiments.md`, plus the
half-life grid on a 100-ticker sample and a focus report on the 23 interest tickers (HOOD.txt).
**Ground rules compliance:** No production file modified (`git status` clean outside `app/exp/`).
All code in `app/exp/`, all outputs `exp_`-prefixed in `app/exp/output/`, every run logged in
`app/exp/output/manifest.txt`. Embargo follows production exactly: strict `<`
(`train daynum < case daynum - horizon`) — confirmed with SM after noting the handoff wrote `<=`
while production uses `<`.

---

## 1. Executive summary

1. **Half-life recency weighting: REJECTED.** Walk-forward over 250 daynums on 100 tickers
   (23 interest + 77 random, seed 42): equal weighting beats H ∈ {63, 126, 252} on mean realized
   log-loss at **both** horizons. The shorter the half-life, the worse.
2. **The dominant pathology is overconfidence, not staleness.** The production model put
   probability **0.000 on the outcome that actually happened** in **28%** (20d) and **47%** (50d)
   of all historical cells. Median realized log-loss (2.45 / 6.22) is far above the ln 3 ≈ 1.10
   "know nothing" reference. Probabilities are best read as *rankings*, not probabilities.
3. Recency weighting made in-sample fit *look* better (median fitR2 0.56 vs 0.37 at 20d) while
   predicting *worse* — the textbook overfitting signature.
4. **Recommended next experiment** (not started, out of scope per handoff): stronger
   regularization (`--reg-lambda` sweep; flag already exists) and/or post-hoc probability
   calibration. The sandbox tooling (scorer, quality A/B, walk-forward harness) is ready for it.

---

## 2. Phase 1 — `exp_shared.py` (extended fit core)

The only fork of production logic: `fit_predict_multinomial_ext` (marked
`# forked from aux_winloss_shared v1`) with mean-1.0-normalized `sample_weight`, single-class
early exit returning `FitDiagnostics(None, None)`. Plus `exp_weights`, `effective_n` (Kish),
`mcfadden_r2`, `top_drivers` (exact logit decomposition), `format_cell`, copies of production
overlay matrix I/O, and `append_manifest`.

**Acceptance (self-test on synthetic data, all PASS):**

| Check | Result |
|---|---|
| (i) `sample_weight=ones` == unweighted | max coef deviation 0.00e+00 |
| (ii) strong decay changes coefficients | max coef diff 0.765 |
| (iii) `effective_n(ones)` = n | 600.0; H=30 decay → 86.6 |
| (iv) `mcfadden_r2` | 0.0 at base rates; 0.175 for informative signal |
| (v) `top_drivers` regex `^[+-]\w+(\|[+-]\w+){2}$` | `-f0\|+f1\|+f2`, None-pipeline → blank |

Spec note: `effective_n(w)` cannot derive the raw length from `w=None`, so it takes an optional
`n_rows` argument used only in that case (SM: no objection).

## 3. Phase 2 — `exp_winloss_probs.py` (experimental scorer)

Twin of production with `--half-life`, effective-sample gate, class-starvation guard
(`MIN_CLASS_WEIGHT_SHARE = 0.01`), and per-cell fitR2 + win/loss driver outputs from the same
single fit. Files: `exp_longi_P{h}_{win,loss}_{suffix}`, `exp_longi_fitR2_{h}_{suffix}`,
`exp_longi_drivers{h}_{win,loss}_{suffix}`, suffix `H{int}` / `Hnone`.

**Acceptance (all at daynum 2183, the newest):**

- **Fidelity `_Hnone` vs production to 3 decimals:** blank patterns identical in all four
  matrices; 4,651 / 4,656 comparable cells match exactly. All 5 mismatches (max diff 0.011:
  PMT-PA 20d; EG, ENB-PFV.TO, LADR, XNIF.L 50d) are class-starvation-guard cells — each has a
  Win class carrying <1% of training rows, dropped per spec where production keeps it.
  Verified ticker-by-ticker.
- **H63 run:** valid (all probabilities in [0,1], win+loss ≤ 1); differs from `_Hnone` on
  82.1% (20d) / 49.7% (50d) of shared cells.
- **Drivers:** every filled cell matches the 3-token regex; zero malformed (1,157/1,157 20d win Hnone).
- **fitR2 medians:** Hnone 0.368 (20d) / 0.639 (50d); H63 0.563 / 0.758.
- **Runtime:** 15.3s (Hnone) / 16.7s (H63) per daynum vs production ~15s (nightly log
  22:59:05→22:59:20) — within the 1.2× budget.
- Cell accounting (H63): 20d scored 1,159 (16 raw-count-blanked, 8 effective-gate-blanked,
  4 no-features); 50d scored 1,154 (22 / 7 / 4). Gate blanks reported separately as specified.

## 4. Phase 3 — `exp_winloss_quality.py` (realized quality + A/B)

Pure file arithmetic: reconstructs p_noloss (clamp+renormalize), realized class via imported
`label_from_gain`, writes per-cell log-loss (`-log(p_realized + 1e-12)`) and Brier matrices,
tidy `exp_day_summary_{source}.csv` (replace-by-key), A/B table + overfitting-gap note for
multiple `--source` values.

**Acceptance:**

- Full-history scoring of `prod`: 404,463 cells / 351 daynums (20d) + 334,760 / 291 (50d) in
  **3.6s**; three-source run 4.7s. Nothing under `app/output/` touched.
- Hand-verified cell 0522.HK @ daynum 2163 (p_win 0.517, p_loss 0.447, gain +15.19 → Win):
  manual log-loss 0.660 = file 0.660; manual Brier 0.434 = file 0.434.
- Newest 20 (20d) resp. 50 (50d) columns blank in the log-loss matrices, as required.

**Finding — production probabilities are severely overconfident** (ln 3 ≈ 1.099 = uniform ignorance):

| Metric | 20d | 50d |
|---|---|---|
| mean log-loss | 9.03 | 13.65 |
| median log-loss | 2.45 | 6.22 |
| cells with p(realized class) = 0.000 | **28.1%** | **47.1%** |
| mean log-loss excluding those | 1.77 | 1.21 |
| mean Brier (uniform = 0.667, max 2) | 1.11 | 1.20 |

Zero-probability cells cost −ln(1e-12) ≈ 27.63 each, so the mean is dominated by
confident-wrong predictions; Brier (bounded) confirms the picture independently.

## 5. Phase 4 — `qa_halflife_grid.py` (the half-life experiment)

Walk-forward: per H, per scoreable daynum (newest N per horizon), per ticker — embargoed
weighted fit, held-out prediction, production `compute_error_counts` + realized log-loss.
Results in `exp_qa_halflife_results.csv` (replace by (H, horizon) key). Compute warning in
docstring; never wired to cron.

**Smoke acceptance:** 5 tickers × 20 daynums × full grid in 10.6s; table renders; equal-weight
probe (`none` vs explicit ones-weights on the same cell): max probability deviation 0.00e+00.

**Full run** (100 tickers: 23 interest + 77 random seed 42, list in
`app/exp/output/exp_grid_ticker_sample.txt`; 250 scoreable daynums per horizon; 868.5s):

| rank | H (20d) | mean log-loss | 1st-ord | 2nd-ord | sig-vs-no | cells |
|---|---|---|---|---|---|---|
| 1 | **none** | 4.864 | 6,718 | 3,990 | 4,745 | 24,610 |
| 2 | 252 | 4.887 | 6,748 | 3,987 | 4,731 | 24,604 |
| 3 | 126 | 5.059 | 6,729 | 4,004 | 4,722 | 24,590 |
| 4 | 63 | 5.834 | 6,604 | 4,074 | 4,641 | 24,500 |

| rank | H (50d) | mean log-loss | 1st-ord | 2nd-ord | sig-vs-no | cells |
|---|---|---|---|---|---|---|
| 1 | **none** | 10.779 | 6,426 | 4,435 | 4,500 | 24,504 |
| 2 | 252 | 10.824 | 6,422 | 4,465 | 4,506 | 24,501 |
| 3 | 126 | 10.909 | 6,446 | 4,498 | 4,498 | 24,500 |
| 4 | 63 | 10.945 | 5,949 | 4,119 | 3,968 | 22,238 |

H=63 at 50d also loses ~2,300 cells to the effective-sample gate (its effective history is too
short for many tickers). A 20-daynum/5-ticker smoke run had hinted H might help at 50d; the
balanced sample refuted that — window and sample size matter.

## 6. Focus report — the 23 interest tickers (HOOD.txt)

Script `exp_focus_report.py` (added on SM's request, outside original handoff). Output:
`app/exp/output/exp_focus_report_Hnone.csv` (Excel-ready) — per ticker and horizon: newest
probabilities, fitR2, win/loss drivers, and the production model's historical reliability on
that ticker (n cells, mean/median log-loss, mean Brier, % of days the realized class had been
given probability 0.000).

Highlights (snapshot daynum 2183, source `_Hnone`; history = full production record):

| Ticker | P20 win | P50 win | 20d %zero | 50d %zero | Note |
|---|---|---|---|---|---|
| KRC | 0.924 | 1.000 | 12.3 | 24.4 | most trustworthy model in the list |
| ASX | 0.976 | 1.000 | 17.1 | 41.9 | best 20d median log-loss (0.29) |
| AFRM | 0.987 | 1.000 | 19.7 | 39.2 | |
| OKTA | 0.999 | 1.000 | 22.2 | 35.7 | |
| HOOD | 0.942 | 0.999 | **54.1** | **71.5** | model wrong-confident most days |
| EIF.TO | 0.929 | 1.000 | 39.9 | **77.3** | |
| CAT | 0.932 | 1.000 | 36.2 | **74.6** | |
| 0522.HK | 0.916 | 0.995 | 32.2 | **82.8** | least reliable 50d in the list |

Full 23-ticker tables (both horizons, incl. drivers) are in the CSV. Interpretation: at 50d
nearly every focus ticker gets p_win ≈ 1.000 today, while historically the model's stated
certainty was contradicted by reality on 25–83% of days depending on ticker. Treat the values
as relative scores, not calibrated probabilities, until the calibration experiment is done.

## 6b. Calibration of the stated probabilities (added on SM's question, post-Phase 5)

Question: the Phase 3 metrics score the whole 3-class distribution — but is **Prob(target
reached)** itself reliable? I.e. when the model states p_win = 0.9, does gain > 6% (20d) /
> 10% (50d) happen ~90% of the time?

Method (`exp_calibration.py`): every historical cell with both a stated probability and a
realized gain, binned by stated probability into 10 fixed-width bins; per bin compare mean
stated probability with realized event frequency. Events via imported `label_from_gain`
(win = class Win, loss = class Loss). Probabilities taken **as stated** in the files.
Full tables: `app/exp/output/exp_calibration_prod.csv` (scopes: all tickers + 23 focus).

**Result: the stated probabilities carry essentially no calibration information at the
pooled level.** The realized event rate is roughly the base rate in *every* bin:

| stated p_win (20d, all) | n | realized win rate |
|---|---|---|
| 0.0–0.1 | 251,271 | 27.4% |
| 0.9–1.0 | 81,769 | 30.5% |
| (base rate) | 404,463 | 28.6% |

| stated p_loss (20d, all) | n | realized loss rate |
|---|---|---|
| 0.0–0.1 | 167,388 | 45.5% |
| 0.9–1.0 | 137,465 | 45.1% |
| (base rate) | 404,463 | 45.4% |

50d looks the same (win rate 31.0% in the lowest bin vs 36.8% in the highest, base 32.5%;
loss flat at ~40–43% everywhere). The focus-23 subset mirrors it (e.g. 50d: stated 0.9–1.0
realizes 57.0% wins vs 58.6% in the 0.0–0.1 bin — no lift at all).

In words: pooled across tickers and days, a cell stating p_win = 0.99 wins the target no more
often than one stating p_win = 0.01. The distribution of stated values is extremely bimodal
(most cells in the 0–0.1 or 0.9–1.0 bins — consistent with the overconfidence finding), and
the extremes are uninformative about the outcome.

**Important caveat before concluding "no signal":** this is a *pooled, unconditional* test.
Within-day or within-ticker discrimination can survive pooling — e.g. if the probabilities
rank stocks usefully *within a given day* while their absolute level drifts with market
regime, pooled calibration washes it out. The strategy layer consumes these files as
*rankings within a day*, so the decision-relevant follow-up test is: per daynum, do
higher-p_win stocks win more often than lower-p_win stocks that same day (cross-sectional
rank lift)? Not yet run — proposed as the next experiment alongside
regularization/calibration.

## 6c. Within-day rank lift (the follow-up test from 6b)

Question: pooled calibration is flat, but does ranking stocks by p_win *within a day* — how
the strategy layer actually uses the files — carry signal?

Method (`exp_rank_lift.py`): per daynum, all scoreable stocks split into within-day deciles
by stated probability (decile 10 = highest that day, deterministic tie-breaking); realized
event rates averaged across days (equal day weight); paired per-day top-minus-bottom lift.
Full table: `app/exp/output/exp_rank_lift_prod.csv`.

**Result: a small but consistent cross-sectional signal in p_win; none in p_loss.**

| | 20d p_win | 50d p_win | 20d p_loss | 50d p_loss |
|---|---|---|---|---|
| decile 1 realized rate | 27.3% | 33.1% | 45.5% | 40.2% |
| decile 10 realized rate | 30.2% | 36.4% | 46.1% | 40.1% |
| mean per-day lift (top−bottom) | **+2.9pp** | **+3.4pp** | +0.6pp | −0.1pp |
| days with positive lift | 60.7% (of 351) | 67.7% (of 291) | 53.3% | 50.5% |

Reading:
- **p_win ranking works, modestly**: the day's top decile wins ~3pp more often than the bottom
  decile (~10% relative edge over the ~29–33% base rate), positive on 61–68% of days, and the
  decile curve rises roughly monotonically. The model's *ordering* has value even though its
  *scale* is meaningless.
- **p_loss ranking carries nothing**: flat deciles, lift indistinguishable from zero. The loss
  probabilities appear to be noise both as probabilities (6b) and as rankings.
- Caveat on the "% positive days" figures: consecutive days share overlapping outcome windows
  (20/50 days), so the effective number of independent observations is far below 351/291 —
  the consistency is suggestive, not airtight.

Combined 6b+6c conclusion: use p_win as a relative ranking signal only; ignore p_loss until
the model is reworked; and any use of the numbers *as probabilities* requires the calibration
experiment. This also reframes the promotion question: improving log-loss (Phase 4 style) and
improving rank lift are different objectives — future variants should be judged on rank lift
too (`exp_rank_lift.py --source <variant>` after a backfill).

## 6d. Per-ticker persistence: are some tickers more predictable? (SM's question #2)

Question: does the "model is overfit / near-uninformative" conclusion hold uniformly, or are
some tickers genuinely more predictable than others (as the focus report's spread — KRC 12%
zero-prob days vs 0522.HK 83% — might suggest)?

Method (`exp_ticker_persistence.py`): history split at the global median daynum (1988); per
ticker and half, AUC of stated p_win vs realized win event (0.5 = no discrimination); then
across ~750–1,150 tickers, correlate half-1 AUC with half-2 AUC. If per-ticker predictability
is real, early AUC should predict late AUC. Full per-ticker table:
`app/exp/output/exp_ticker_persistence_prod.csv` (focus tickers flagged).

**Result: zero persistence. Per-ticker "predictability" is noise.**

Persistence correlations (half-1 vs half-2 AUC across tickers): Pearson −0.005 to +0.053,
Spearman −0.015 to +0.038, for all four (horizon × win/loss) combinations. The quintile table
is textbook regression-to-the-mean — tickers that looked strongly predictable OR strongly
anti-predictive in half 1 all land at the same ~0.51–0.52 in half 2:

| half-1 AUC quintile (20d p_win) | mean h1 AUC | mean h2 AUC |
|---|---|---|
| Q1 (worst) | 0.302 | 0.517 |
| Q3 | 0.491 | 0.523 |
| Q5 (best) | 0.700 | 0.510 |

Same pattern at 50d and for p_loss.

Implications:
- The general conclusion applies **uniformly across tickers**. There is no stable subset of
  "predictable" tickers.
- Historical per-ticker reliability (the focus report's %zero / median log-loss columns, KRC's
  flattering numbers, HOOD's terrible ones) **must not be used as a trust screen** — those
  differences did not persist and would not have predicted the next period.
- Mean per-ticker AUC sits slightly above 0.5 (0.50–0.56) in both halves — the same thin,
  broad signal seen in the rank-lift test (6c), spread evenly over the universe rather than
  concentrated in particular names.

## 6e. Standalone lift of the raw indicators (step 1 of the stratification approach)

Question (SM): instead of mending the softmax, build up empirical conditional probabilities —
strongest indicator first, then add uncorrelated indicators, measuring lift at each step.
This section is step 1: which raw indicators carry real, persistent standalone signal?

Method (`exp_indicator_lift.py`): full history (~520–620 usable daynums, ~730k cells), per
indicator per day, within-day deciles by raw indicator value; realized win-event rate per
decile; per-day top-minus-bottom lift; persistence = mean lift in older vs newer half.
Loss events measured identically. Full table: `app/exp/output/exp_indicator_lift.csv`.

**Win-event lift ranking (20d; 50d is qualitatively identical):**

| indicator | decile-1 win rate | decile-10 win rate | lift | pos. days | h1 lift | h2 lift |
|---|---|---|---|---|---|---|
| vola100d | 12.3% | 40.1% | **+27.8pp** | 94% | +26.2 | +29.5 |
| vola20d | 12.4% | 37.8% | +25.3pp | 93% | +18.8 | +31.9 |
| beta3m | 19.9% | 40.1% | +20.2pp | 82% | +16.9 | +23.6 |
| spr100d | 24.6% | 34.1% | +9.5pp | 70% | +13.6 | +5.4 |
| ma50 (price level) | 31.3% | 23.7% | −7.6pp | 23% | −10.6 | −4.5 |
| median_30d (rank) | 35.2% | 28.9% | −6.2pp | 38% | −2.3 | −10.1 |
| coreindex | 24.2% | 29.9% | +5.7pp | 71% | +5.8 | +5.6 |
| per3m | 31.3% | 36.2% | +4.9pp | 63% | **−1.4** | **+11.3** |
| … (rsi, stepups, macd_signal ≤ ±2pp) | | | | | | |

**The crucial loss-side check** (does the same decile also lose more?):

| indicator (d10 vs d1) | win lift | loss lift | reading |
|---|---|---|---|
| vola100d | +27.8pp | +5.7pp | partly mechanical: volatile stocks cross ±thresholds more; but strongly asymmetric because winning needs a +6% move while losing only needs <0 |
| **beta3m** | **+20.2pp** | **−2.2pp** | **cleanest signal: high beta wins far more often WITHOUT losing more** |
| median_30d (low=good rank) | +6.2pp (d1) | −4.8pp (d1) | modest but double-sided: good momentum rank → more wins AND fewer losses |
| ma50 (low price) | +7.6pp (d1) | −0.5pp (d1) | low-priced stocks win more at no loss cost (small-cap/vola proxy) |
| spr100d | +9.5pp | +4.7pp | mixed; also decaying h1→h2 |

Headline findings:

1. **A single raw indicator beats the whole model.** vola100d's within-day top decile wins
   40% vs 12% for the bottom (+28pp, positive on 94% of days, stable in both halves). The
   fitted 20-feature softmax achieves +3pp (section 6c). The model destroys signal its own
   inputs contain.
2. **beta3m is the cleanest single conditioner**: +20pp win lift at zero loss penalty,
   persistent in both halves. (beta and vola correlate; step 2 must measure their joint lift.)
3. **The momentum/rank family** (median_XXd, ma-price-level) gives a modest double-sided
   benefit (more wins and fewer losses). per3m/sh3m/PdivMA50 are regime-unstable (sign flip
   between halves) — treat with suspicion.
4. **The softmax leans on the wrong features**: its driver columns are dominated by
   ma10/ma20/ma50, while the persistent standalone signal is in vola/beta. Also note the
   win threshold asymmetry (win = >+6%, loss = <0) means volatility mechanically boosts win
   rates — any conditioning on vola must present the accompanying loss rate honestly.

Proposed step 2 (not yet run): joint stratification — e.g. within-day beta3m top-tercile ×
median_30d best-tercile — empirical win/loss rates with counts, plus persistence check;
that is the next rung of SM's "Bayes ladder" and would yield honestly calibrated
conditional probabilities.

## 6f. Joint stratification: the first honestly calibrated success-chance table (step 2)

Method (`exp_joint_strata.py`): within-day terciles of beta3m (A) × within-day terciles of
median_30d (B; low value = strong momentum rank), empirical win/loss rates per cell (equal
day weight), ~50–90k observations per cell, persistence via older/newer half split.
Full tables: `exp_joint_strata_beta3m_x_median_30d.csv`, `exp_joint_strata_vola100d_x_median_30d.csv`.

**beta3m × median_30d, 20d horizon** (win% / loss%; base 27.5 / 45.3):

| | B1 strong momentum | B2 mid | B3 weak |
|---|---|---|---|
| **A3 high beta** | **37.5 / 43.4** | 32.8 / 45.4 | 32.4 / 47.0 |
| A2 mid | 29.6 / 42.5 | 26.0 / 43.7 | 24.8 / 48.6 |
| A1 low beta | 23.8 / 45.4 | 19.2 / 44.8 | 21.8 / 47.1 |

50d: best cell 38.9 / 41.8 vs base 28.8 / 43.5. The vola100d variant is marginally stronger
on win rate (39.0 / 41.2) but pays with a loss rate at/above base — beta3m keeps the loss
rate *below* base, confirming it as the cleaner conditioner.

Properties that the softmax never had:

- **Monotone in both directions**: every step up in beta and every step toward stronger
  momentum raises the win rate. No fitted cell — these are counted frequencies.
- **Persistent**: the gradient survives the half-split everywhere (20d best cell
  33.9% → 41.0%; worst cell 18.0% → 20.3%). Levels shift with regime (h2 was friendlier),
  but the *ordering* of cells is stable — so use the table as a relative screen, with the
  level read from the current regime.
- **Honest**: with n ≈ 50–90k per cell the sampling error is ~0.2pp; the real uncertainty
  is regime drift, which the h1→h2 columns expose instead of hiding.
- Effects are roughly additive (little interaction): beta contributes ~14pp across terciles,
  momentum ~4–5pp on top.

**Practical reading:** "high-beta stocks currently in the strongest momentum tercile" win the
20d +6% target ~37–38% of the time (vs 27.5% for everything) while losing slightly *less*
often than average — a ~2× win-rate separation from the worst cell (19.2%). This 3×3 table,
kept updated daily and combined with a regime-level base rate, is a defensible advisory core —
which the softmax probabilities, as shown in 6b–6d, are not.

Possible step 3 (not run): a third conditioner (coreindex or spr100d) on top of the best
cell, or finer beta bins — with the standing caution that each added split multiplies the
multiple-testing risk and must pass the same persistence gate.

## 6g. Finer bins + the daily corner-cell screen (SM's requests)

**Do finer bins sharpen without losing persistence? Yes.** beta3m × median_30d corner cell
(top beta bin × strongest momentum bin), win/loss rates:

| bins | 20d corner | 50d corner | 20d persistence (h1→h2) | n (hist) | ~names/day |
|---|---|---|---|---|---|
| 3×3 | 37.5 / 43.4 | 38.9 / 41.8 | 33.9 → 41.0 | 84k | ~150 |
| 5×5 | 41.9 / 41.8 | 44.0 / 40.6 | 37.1 → 46.7 | 38k | ~69 |
| 10×10 | **45.4 / 40.7** | **48.2 / 40.7** | 40.0 → 50.8 | 14k | ~26–44 |

Monotone sharpening, persistence intact at every granularity (the newer half is uniformly
stronger — regime effect; the *gradient* is what persists). Note the corner cell is larger
than 1/K² would suggest (14k not 6.4k): high-beta stocks cluster in the momentum extremes.

**The daily screen** (`exp_screen_today.py`, default = decile corner): lists today's members
with honest historical expectations printed first. Output:
`exp_screen_{daynum}_beta3m10_x_median_30d1.csv`.

Historical expectations for the corner cell (full history, n = 13–14k):

| | 20d | 50d |
|---|---|---|
| win rate | 44.0% | 45.0% |
| loss rate (<0) | 42.3% | 43.9% |
| gain < −5% | 31.6% | 37.8% |
| gain < −10% | **22.3%** | **31.6%** |
| median gain | +3.4% | +5.5% |
| mean gain | +5.6% | +12.3% |
| p10 / p90 | −19.3 / +32.2 | −30.2 / +61.0 |

**Honesty note on "winning & not losing much":** this cell wins often and earns well on
average, but it does NOT satisfy "not losing much" — when it loses, it loses big (22–32% of
outcomes are worse than −10%; that's high beta doing what high beta does). A candidate
refinement (step 3, not yet run): trim the corner by vola100d (keep the lower-vola half of
corner members) and test whether the tail shrinks more than the win rate does.

Today's list (daynum 2183): **44 tickers**, heavily semiconductor/tech-momentum flavored
(MU, AMD, LRCX, KLAC, AMAT, TSM, ASML.AS, ARM…). Focus tickers included: TER, SNDK, UCTT,
INTC, ASX, STX. **Caveat:** the corner is currently one sector cluster — the 44 names are
far from 44 independent bets, and a semis reversal hits the whole list at once.

## 6h. Step 3 — vola-trim of the corner cell (`exp_corner_trim.py`)

Within each day's corner membership, members are ranked by vola100d and the lower half kept
(`--keep-frac 0.5`). Full history, three segments compared:

**20d (win > 6%):**

| segment | n | win% | loss% | <−5% | <−10% | p10 | med | mean | win h1→h2 | tail10 h1→h2 |
|---|---|---|---|---|---|---|---|---|---|---|
| full | 13,987 | 44.1 | 42.1 | 31.5 | 22.3 | −19.3 | +3.4 | +5.6 | 36.0→49.8 | 28.9→17.6 |
| **kept (low vola)** | 6,866 | **44.0** | 39.0 | 26.5 | **16.4** | **−14.4** | +3.9 | +5.4 | 33.0→51.9 | 25.7→**9.8** |
| dropped (high vola) | 7,121 | 44.1 | 45.2 | 36.3 | 28.1 | −23.9 | +2.7 | +5.7 | 39.0→47.8 | 32.0→25.2 |

**50d (win > 10%):**

| segment | n | win% | loss% | <−5% | <−10% | p10 | med | mean | win h1→h2 | tail10 h1→h2 |
|---|---|---|---|---|---|---|---|---|---|---|
| full | 12,553 | 45.4 | 43.5 | 37.5 | 31.5 | −30.4 | +5.9 | +12.7 | 34.8→53.9 | 41.2→23.8 |
| **kept (low vola)** | 6,155 | **48.6** | **37.7** | 31.3 | **25.3** | **−23.9** | **+9.1** | +12.1 | 31.9→61.9 | 40.6→**13.1** |
| dropped (high vola) | 6,398 | 42.4 | 49.0 | 43.5 | 37.5 | −35.0 | +0.9 | +13.3 | 37.7→46.2 | 41.7→34.2 |

**Verdict: the hypothesis holds — the tail was living in the high-vola half.**
- **20d:** win rate unchanged (44.0 vs 44.1) while the <−10% tail drops 22.3% → 16.4% and p10
  improves −19.3 → −14.4. Pure tail reduction at zero win cost.
- **50d:** even better — the trim *raises* the win rate (45.4 → 48.6), cuts the loss rate
  (43.5 → 37.7), cuts the tail (31.5 → 25.3), and raises the median gain (+5.9 → +9.1).
  The dropped half is strictly worse on every downside metric.
- Persistence intact: the kept segment's h2 tail10 is just 9.8% (20d) / 13.1% (50d).
- Mean gain is ~equal between kept and dropped: the high-vola half compensates its fat left
  tail with a fat right tail (p90 +38/+77) — lottery tickets. Kept = same average, far
  fewer disasters, which is exactly the "winning & notLosingMuch" objective.

**Today (daynum 2183): 22 of 44 corner members survive the trim** — AMD, LRCX, AMKR, ON,
LSCC, MOD, KLAC, ONTO, STM, ASX, ASML.AS, AMAT, POWL, ASM.AS, TOELY, STX, GFS, UMC, TSM,
SANM, BESI.AS, FIX. Focus tickers surviving: **ASX, STX** (TER, SNDK, UCTT, INTC fall in the
high-vola half). Sector-cluster caveat unchanged: still essentially one semis bet.

Output: `exp_corner_trim_beta3m10_x_median_30d1_by_vola100d.csv`. Flags:
`--ind-a --ind-b --bins --trim-ind --keep-frac --min-cells-per-day --horizons --focus-file`.

## 6i. Sector concentration of the survivor sample over full history (SM's question)

Question: today's survivor list is ~one semis bet — is that a property of the strategy or
just of the current regime?

Method (`exp_sector_concentration.py`): rebuild corner + vola-trim for every usable daynum,
drop the oldest 150 as warm-up (leaves 391 days, daynums 1793–2183), map members to Sector2
(Stamdata, production column convention; 0 unmapped), measure per day the top-sector share
(most frequent Sector2 count / member count), distinct sectors, and HHI. Computed for both
the untrimmed corner and the trimmed survivors. No outcome files involved, so the timeline
reaches the newest daynum. Full timeline: `app/exp/output/exp_sector_concentration_timeline.csv`.

**Result: concentration is a regime phenomenon, not a structural property — but the current
regime is long-lived and intensifying.**

| survivors (median members/day 14) | value |
|---|---|
| top-sector share: mean / median | 38.2% / 31.6% |
| p10 / p90 / max | 18.2% / 66.7% / 100.0% |
| days with top share ≥ 1/3 / ≥ 50% / ≥ 75% | 48.8% / 33.5% / 3.8% |
| effective sectors per day (1/HHI), median | 4.7 |
| median top share h1 → h2 | 22.2% → **53.3%** |
| most frequent top sector | Semi (58% of days), TechToProfs (14%), Bank (7%), Electronics (7%) |

Time profile (survivors, median top-sector share per 50-daynum bucket):

| bucket | 1793–1849 | 1850–99 | 1900–49 | 1950–99 | 2000–49 | 2050–99 | 2100–49 | 2150–83 |
|---|---|---|---|---|---|---|---|---|
| median top share | 22% | 25% | 20% | 21% | 43% | 53% | 53% | **68%** |
| dominant top sector | TechToProfs | Bank | Semi | Electronics | Semi | Semi | Semi | Semi |
| % of days that sector on top | 38% | 40% | 50% | 40% | **100%** | **100%** | **100%** | **100%** |

Reading:
- **Before daynum ~2000**: healthy rotation. Top share ~20–25%, top sector alternates
  (TechToProfs, Bank, Semi, Electronics), ~7 effective sectors/day.
- **From daynum ~2000 on**: Semi is the top sector on *every single day* and its share ramps
  43% → 68% (today 22 of 22 survivors ≈ one cluster). The current concentration is the most
  extreme of the whole history.
- **The trim worsens concentration mechanically**: corner median top share 25.0% / 7.7
  effective sectors vs survivors 31.6% / 4.7. Halving the list and tilting low-vola both
  narrow the sector mix.

Implication for the advisory product: the historical win/loss label (6h) averages over the
rotating-regime era AND the semis era; in a one-sector regime the survivors' outcomes are one
correlated draw, so the realized dispersion around the label is much wider than the pooled
n≈6–7k suggests. The concentration measure itself is cheap (runs in ~1s) and could be printed
by the daily screen as an honesty metric ("today's effective sectors: X"). A sector-cap or
per-sector pick limit is a candidate refinement, but it changes the sample the 6g/6h rates
were measured on — it would need its own win/loss re-measurement.

## 6j. Probe samples: the survivor list at every 50th daynum (SM's request)

`exp_probe_samples.py`: every 50th usable daynum backwards from the newest (2183, 2133, …,
1833 — 8 probes within the post-warm-up range), the full survivor list with ticker, Name,
Sector2, the **point-in-time** win/loss label per horizon, beta3m, median_30d, vola100d, and
RankNow (longi_rank at the probe day, rank 1 = best), sorted ascending on RankNow. The label
at probe day D is the cell-level rate over survivor history *known at D*: daynums from the
end of warm-up (1793) to D − horizon (strict `<`, production embargo — the last 20/50 days'
outcomes are not yet realized at D). Identical for every member of a probe by design (6d).
Full data: `app/exp/output/exp_probe_samples.csv` (incl. `nhist` per horizon).

**The point-in-time labels swing hard with the era** (win% / loss%, n of label history):

| probe | n | 20d label | nhist20 | 50d label | nhist50 |
|---|---|---|---|---|---|
| 2183 | 22 | 46.5 / 36.4 | 5,094 | 53.4 / 32.3 | 4,390 |
| 2133 | 19 | 43.3 / 39.2 | 4,080 | 48.4 / 36.3 | 3,643 |
| 2083 | 15 | 43.1 / 39.3 | 3,348 | 44.5 / 39.8 | 2,918 |
| 2033 | 16 | 39.7 / 42.8 | 2,532 | 41.2 / 43.5 | 1,975 |
| 1983 | 18 | 35.8 / 44.4 | 1,723 | 35.1 / 50.6 | 1,423 |
| 1933 | 12 | 28.2 / 53.7 | 1,194 | 22.6 / 65.2 | 959 |
| 1883 | 4 | 18.9 / 65.9 | 901 | **6.0 / 85.8** | 649 |
| 1833 | 12 | 38.4 / 38.4 | 331 | (no realized history yet) | 0 |

Readings: (1) eyeball confirmation of 6i — the two newest probes are 68–77% Semi, 1983 and
older are genuinely diverse (Electronics/Fintech/Defense/Utilities eras), probe 1883 has just
4 survivors (thin corner days exist; the daily screen should show n prominently). (2) The
early labels are dominated by the bear era: at 1883 the honest backward-looking label said
"6% win / 86% loss at 50d" — an advisory product would have (correctly, at that time) warned
against its own list. Labels stabilize as nhist grows, converging toward the pooled 6h values
(44.0/39.0, 48.6/37.7). A rolling-window variant (e.g. trailing 250d) instead of
expanding-from-warm-up would track regime faster at the cost of noise — open design choice
for the advice product.

**Realized fate of the picks** (columns `gain20d`/`gain50d` added to the CSV on SM's request;
per-probe realized rates vs the stated point-in-time label, win% / loss%):

| probe | n | 20d label | 20d realized | 50d label | 50d realized |
|---|---|---|---|---|---|
| 2183 | 22 | 46.5 / 36.4 | (not yet realized) | 53.4 / 32.3 | (not yet realized) |
| 2133 | 19 | 43.3 / 39.2 | 57.9 / 21.1 | 48.4 / 36.3 | 52.6 / 31.6 |
| 2083 | 15 | 43.1 / 39.3 | 33.3 / 46.7 | 44.5 / 39.8 | 66.7 / 13.3 |
| 2033 | 16 | 39.7 / 42.8 | 31.3 / 43.8 | 41.2 / 43.5 | 81.3 / 12.5 |
| 1983 | 18 | 35.8 / 44.4 | 50.0 / 44.4 | 35.1 / 50.6 | 27.8 / 55.6 |
| 1933 | 12 | 28.2 / 53.7 | 66.7 / 25.0 | 22.6 / 65.2 | 75.0 / 8.3 |
| 1883 | 4 | 18.9 / 65.9 | **100 / 0** | 6.0 / 85.8 | **100 / 0** |
| 1833 | 12 | 38.4 / 38.4 | **8.3 / 83.3** | (no history) | 8.3 / 75.0 |

Per-probe realized rates scatter wildly around the label — expected, since one probe day is
n≈4–22 heavily correlated draws (one sector cluster, overlapping windows), not independent
samples. The extremes are instructive: 1833 was the bear onset (10 of 12 picks lost, PLTR
−31%, HOOD −29%) while 1883 — where the backward label was at its most damning — went 4/4
wins. The expanding backward label is a *trailing* regime indicator: most pessimistic exactly
at the bottom, still catching up in recoveries. Whatever label design is chosen, the product
must not present it as the expectation for *this* day's list — it is a long-run average
conditioned on regime persistence.

## 6k. Small-purse sub-selection: picking K of the day's survivors (SM's question)

Question: investors who cannot buy the whole list must pick 1–5 names. Does picking the best
by RankNow (longi_rank, 1 = best) beat picking blind? Caution going in: the strategy
project's from_rank experiments found bottom-of-ranking sometimes beats top on heavily
filtered focus sets.

Method (`exp_subgroup_pick.py`): full survivor history; per day pick top-K / bottom-K /
random-K (seed 42) by RankNow; days thinner than K contribute all members (no day skipped —
covers the 4-survivor days like 1883). `--chooser` accepts any longi indicator. Note the
correct baseline for a K-picker is **random-K, not the group**: the group pools all cells so
fat 22-name days dominate it, while a K-picker caps every day at K. Full table:
`app/exp/output/exp_subgroup_pick_rank.csv`.

**Result: RankNow top-picks win — top > random > bottom at every K, both horizons.**

| 50d (win >10%) | win% | loss% | <−10% | median | mean | win h1→h2 |
|---|---|---|---|---|---|---|
| group | 48.6 | 37.7 | 25.3 | +9.1 | +12.1 | 31.9→61.9 |
| **top1** | **57.0** | **29.7** | 20.0 | **+14.9** | +17.8 | 50.8→63.3 |
| random1 | 54.2 | 33.8 | 22.4 | +12.6 | +15.1 | 40.7→67.8 |
| bottom1 | 43.6 | 44.6 | 29.3 | +6.0 | +8.9 | 38.2→49.0 |
| top5 | 53.5 | 33.3 | 22.7 | +12.5 | +15.0 | 41.7→64.9 |
| random5 | 51.4 | 35.0 | 23.4 | +10.9 | +13.1 | 39.5→62.7 |
| bottom5 | 48.6 | 37.6 | 24.6 | +9.1 | +12.3 | 37.4→59.4 |

20d shows the same ordering, more weakly (top1 47.4/36.9 vs random1 45.5/35.5 vs bottom1
40.7/42.0; group 44.0/39.0).

Readings:
- **The from_rank anti-predictive worry does NOT apply inside the survivor list** — top beats
  bottom by 3–13pp win rate everywhere, and the gradient is monotone in K (sharper pick =
  bigger edge: top1 > top3 > top5).
- **The edge over random is modest but real and most persistent where it matters**: at 50d,
  top1's h1 win rate is 50.8% vs random1's 40.7% — the rank chooser earned its keep in the
  harder half. Top1-50d is the standout: 57% win / 30% loss / median +14.9%.
- **Random-K beats the pooled group at 50d** (54.2 vs 48.6 win at K=1) — an artifact of day
  weighting worth remembering: capping at K per day *underweights* the fat semis days, which
  were on average slightly worse per pick than thin days.
- Caveat: K=1 rows are 491–521 picks with overlapping outcome windows — effective sample far
  smaller; treat the exact levels loosely, the ordering held in both halves.
**Chooser alternatives (SM's request):** "Cross1020/2050" clarified as *speed quotients* —
ma10/ma20 resp. ma20/ma50, HIGH = good, computed on the fly from the longi_ma files
(`--choosers rank,quot1020,quot2050`; the script parses any `quotXXYY` from MA windows
10/20/50/200). The procedure mirrors the strategy work: build the promising group in steps,
then prioritize within it.

**quot2050 is the best chooser tested — the top1-50d line is the strongest result in the
whole sandbox** (win% / loss% / median gain / win h1→h2):

| chooser, top1 | 20d | 50d |
|---|---|---|
| random1 (baseline) | 45.5 / 35.5 / +4.6 | 54.2 / 33.8 / +12.6 (40.7→67.8) |
| rank | 47.4 / 36.9 / +5.1 | 57.0 / 29.7 / +14.9 (50.8→63.3) |
| quot1020 | 48.2 / 38.4 / +5.1 | 55.0 / 35.2 / +14.7 (55.7→54.3) |
| **quot2050** | 51.1 / 31.5 / +6.3 | **61.9 / 30.1 / +19.5 (59.8→64.1)** |
| **rsi** (high = good) | **52.2 / 32.8 / +6.6 (48.7→55.8)** | 53.6 / 34.0 / +14.7 |

- quot2050 top1 leads on every 50d metric except a slightly deeper p10 (−25.7 vs −23.0 for
  rank); its 20d tail is the smallest of all rules (13.1% < −10%). Persistence is the
  strongest seen (59.8% → 64.1% at 50d — no half was weak). top3 keeps most of it
  (57.0 / 33.6 / +16.2); by top5 the edge over random is mostly diluted.
- **RSI (added on SM's request) is the best 20d chooser** — top1 52.2 / 32.8 / +6.6 with the
  best p10 (−13.0) and solid persistence (48.7→55.8); at 50d it is mid-pack on win rate but
  has the smallest 50d tail of all top1 rules (17.7% < −10%, p10 −20.2). **The horizon match
  is systematic: RSI14 for the 20d pick, quot2050 (20/50-day speed) for the 50d pick** — each
  chooser works best at the horizon matching its own lookback. Low-RSI ("pullback entry",
  the bottom rows) is the worst rule tested everywhere (bottom1: 37.2% win 20d, 44.8% 50d) —
  do not buy dips within the survivor list.
- quot1020 ≈ rank overall; its 50d persistence is *inverted* (55.7→54.3 top vs bottom
  rising) — the 10/20 speed is too twitchy at 50d horizon.
- All choosers' bottom-picks underperform their top-picks — the from_rank inversion does not
  appear inside the survivor list for any tested chooser.
- Multiple-testing caution: 3 choosers × 3 K × 2 horizons were compared; quot2050-top1's lead
  is large and both-halves-persistent, which is the strongest defense available here, but the
  exact 61.9% should be treated as an in-sample best-of-grid, not an expectation.
- If quot2050 is adopted by the advice product, a production `longi_quot2050.csv` (and
  `longi_quot1020.csv`) module is a trivial addition: ma20/ma50 quotient, PdivMA-style.

## 6l. DECISION (SM, 2026-07-07): three chooser-strategies, 20d primary

The advice product is settled as **three strategies that differ only by the chooser**
(RankNow, RSI14, quot2050) on top of the identical 3-step group build:
within-day top beta3m decile × strongest median_30d decile × lower-vola100d half,
then buy the chooser's top picks ("buy the top").

- **Primary: 20d horizon**, executed chainwise or split into 4 weekly installments —
  i.e. the chain / ladder execution modes of the strategy framework.
- **50d is the fallback option** (or for lazy members) and shall be reported alongside.
- **Out of scope by decision: buy-the-dip or any other entry tactics.** Low-RSI picks were
  measured as the worst rule tested (6k); the product line is "buy the top or you're on
  your own."
- Prerequisite for the quot2050 strategy outside the sandbox: production quotient modules —
  **both `longi_quot2050.csv` and `longi_quot1020.csv`** (maXX/maYY, PdivMA-style; SM: build
  quot1020 too, to be prepared). **DONE 2026-07-07**: `longi_quot1020.py` / `longi_quot2050.py`
  implemented (PdivMA-style, ×100 percentage, 2 decimals), registered in the orchestrator
  (depends on the MA modules; added to `across` deps → the quotients appear in the daily
  cross-sectional snapshot), first run produced both files (1,200 tickers × 641 daynums),
  values verified against an independent pandas computation (max diff = rounding, blank
  patterns identical), dependency graph validation passes with 38 modules. Enters the nightly
  pipeline on the next `start_longi.sh` run; CLAUDE.md updated.

## 6m. Cleanup: all probability-based code removed (2026-07-07)

Consequence of the 6l decision ("probability-based strategizing is dead"), executed the
same day in two commits on `~/potentials` (`main`):

- **`6d62aff`** — the quotient modules by themselves (see the DONE note in 6l): a normal
  extension of the longi arsenal, kept separate from the demolition.
- **`c18a47d`** — the demolition (25 files, −2083 lines):
  - **longi**: `longi_winloss_probs.py` + `aux_winloss_ablation.py` deleted; `winloss_probs`
    deregistered from the orchestrator (37 modules remain, graph validates); the four
    `longi_P{20,50}d_{win,loss}.csv` removed from `app/output/` and from the QC expected-file
    set (next `longi_upload` sync removes them from Google Drive); the nightly crontab
    backfill job removed (backup: `~/crontab_backup_2026-07-07_pre_winloss_cleanup.txt`);
    the old `explorationOfLogiticModel/` handoff docs deleted.
  - **strategy**: all 9 `strategy_P*.py` strategies plus the 3 parked `P*ZOP` variants and
    their `_not_used/` extension runners deleted; `sweep_config.py` reduced to Cross1020 /
    Cross2050 / Ranknow (the `p_win_min` LINKED alias removed); P-file examples in
    `shared/engine.py` docstrings replaced; the unused P20/P50 slots dropped from the
    extension-sheet param header; both CLAUDE.md files updated.
  - **Kept deliberately**: `aux_winloss_shared.py` (this sandbox imports TARGET_SPECS and the
    CSV IO from it), the `future_gain20d/50d` modules and files (realized outcomes — the
    label/verification machinery of this report depends on them), and `app/exp/` itself as
    the evidence trail.

Validation after the cut: longi dependency graph OK (37 modules), `aux_qc_repo.py` 48/48
pass, `run_sweep.py --list`/`--dry-run` import cleanly and show only the three survivors.

**Sweep re-run (same day)**: `run_sweep.py` regenerated the three surviving strategies; the
old P report folders were archived to `report/_not_used/` (the parked-ZOP convention) and
`best_strategy_20260707.xlsx` rebuilt with only the survivors. **New reigning winner:
Ranknow** — chain_annual 89.5% vs Cross1020 74.8% and Cross2050 65.5% (ladder side ranks the
same way); Ranknow also has the best avg_gain/lot (7.1%) and the least-bad Worst lot
(−21.1 vs −29.8 for Cross2050), at the price of the widest origin sensitivity (69.8–122.0).
All three are far below the retired P-strategies' (illusory, uncalibrated) 200–250% figures —
the honest baseline the three 6l chooser strategies must now beat.

## 6n. Tally strategies implemented in the strategy framework (2026-07-07)

SM named the win/loss counting **"Tally"** (counted history, deliberately past-tense — never
"odds/probability"). The three 6l chooser strategies are now production declarations in
`~/potentials/strategy/app/code/strategies/`: **Tally_Rank**, **Tally_RSI**, **Tally_2050** —
the identical 3-step group build, differing only by chooser (lowest RankNow / highest RSI14 /
highest MA20-MA50 quotient).

**Engine additions** (`shared/engine.py`, all declaration-level):
- `corner_filter(top_csv, bottom_csv, "corner_bins")` — the two-indicator corner cell binned
  within the JOINT valid set, byte-identical to `build_trimmed_corner` steps 1-2 (same
  rank-first tie-breaking, same epsilon, same min-100-per-day guard). A first attempt with two
  independent per-CSV `bin_filter`s was caught by the parity check: at daynum 2183 the decile
  edge over median_30d's own 1,187 valid tickers vs the joint 1,185 dropped FIX (21 vs 22
  survivors) — the joint corner_filter fixes exactly that. (`bin_filter` was kept as a generic
  single-CSV engine knob.)
- `trim_filter(csv, "vola_keep_frac")` + a `trims=` stage in `make_strategy` — applied after
  the filter intersection, ranking WITHIN the survivor set (step 3, the low-vola half).

**Parity check PASSED 8/8** probe days: engine survivors equal the verified
`exp_probe_samples.csv` lists exactly (1833…2183, incl. the 22-ticker list at 2183).

**Report machinery**: `best_strategy.py` no longer aborts on mixed horizons — runs are grouped
by `period`, each horizon gets its own comparison sheet with its own common span. Sheet 1 =
20d (primary), "Best Strategy 50d" = the fallback horizon; extensions run on 20d params.
The sweep runs each Tally strategy at `period` [20, 50] (`sweep_config.py`).

**First sweep** (focusset 5, step 5, from_rank 1, common span floor 1548 / cap 2163 at 20d;
Tally usable from daynum 1643 — vola100d warm-up + the 100-per-day guard):

| 20d chain | Tally_Rank | Tally_RSI | Tally_2050 | Cross2050 | Cross1020 | Ranknow |
|---|---|---|---|---|---|---|
| chain_annual % | 72.8 | 69.6 | **77.5** | 65.5 | 74.8 | **89.5** |
| avg_gain %/lot | 5.97 | 5.71 | 6.37 | 5.20 | 5.94 | 7.11 |
| Worst lot % | −26.4 | −29.6 | −24.8 | −29.8 | −23.2 | −21.1 |
| N_loss (of ~25-31) | **8** | **8** | **9** | 14 | 13 | 15 |
| origin_sens% | 59-83 | 60-81 | **70-83** | 51-84 | 50-102 | 70-122 |

| 50d chain | Tally_Rank | Tally_RSI | Tally_2050 |
|---|---|---|---|
| chain_annual % | 65.1 | 60.5 | **67.2** |
| avg_gain %/lot | 13.1 | 12.2 | **13.6** |
| Worst lot % | −23.7 | −22.4 | **−21.0** |
| N_loss (of 9) | 3 | 4 | 3 |

Readings:
- **Ranknow keeps the chain_annual crown at 20d (89.5)**, but the Tally strategies lose far
  less often: N_loss 8-9 vs 13-15 on similar lot counts, with visibly tighter origin
  sensitivity — the build is doing exactly what it was designed for ("winning &
  notLosingMuch"), it buys that with ~1.5x fewer percentage points per year.
- **Tally_2050 is the best of the three at BOTH horizons** (77.5 / 67.2 annual, best per-lot
  gain, best Worst at 50d). The sandbox's horizon-matching (RSI at 20d) does not carry over
  to focusset-5 chains — RSI is the weakest chooser here at both horizons.
- 50d per-lot gains (12-14%) match the sandbox group medians; only 9 non-overlapping lots
  fit the common span, so treat 50d numbers as low-N.
- Caveats: single-configuration run (no threshold grid), in-sample, and the current semis
  concentration regime dominates the recent span (6i).

Operational note: the strategy framework reads from `repositoryRTBI/data/Longi/`, which gets
the longi files via the Google-Drive round trip — `longi_quot1020/2050.csv` were copied there
manually this once (the nightly sync takes over from tonight).

## 7. Inventory

**Scripts** (`app/exp/`): `exp_shared.py`, `exp_winloss_probs.py`, `exp_winloss_quality.py`,
`qa_halflife_grid.py`, `exp_focus_report.py`.

**Flags:**
- `exp_winloss_probs.py`: `--half-life --daynum --backfill-all --max-daynums --min-stock-samples --reg-lambda --max-iter`
- `exp_winloss_quality.py`: `--source` (repeatable; `prod` or exp suffix)
- `qa_halflife_grid.py`: `--grid --last-daynums --tickers --horizons --min-stock-samples --reg-lambda --max-iter`
- `exp_focus_report.py`: `--tickers-file --source`

**Outputs** (`app/exp/output/`), naming scheme and meaning:

| File | Meaning |
|---|---|
| `exp_longi_P{h}_{win,loss}_{Hnone,H63}.csv` | experimental probabilities, longi layout |
| `exp_longi_fitR2_{h}_{suffix}.csv` | per-cell in-sample McFadden pseudo-R2 |
| `exp_longi_drivers{h}_{win,loss}_{suffix}.csv` | top-3 signed indicators per cell, e.g. `+rsi\|-ma50\|+beta3m` |
| `exp_longi_logloss_{h}_prod.csv` | per-cell realized log-loss of production (ln 3 ≈ 1.099 = ignorance) |
| `exp_longi_brier_{h}_prod.csv` | per-cell Brier score, range [0,2] |
| `exp_day_summary_prod.csv` | tidy per-day cross-sections (n, medians, means, top drivers) |
| `exp_qa_halflife_results.csv` | grid results, one row per (H, horizon) |
| `exp_focus_report_Hnone.csv` | 23-ticker snapshot + historical reliability |
| `exp_grid_ticker_sample.txt` / `exp_focus_tickers.txt` | ticker lists (reproducibility) |
| `manifest.txt` | one line per run: date, script, args, wall-clock, daynums |

**Measured runtimes:** one-daynum scoring 15.3s (Hnone) / 16.7s (H63); full-history quality
scoring 4.7s (3 sources); smoke grid 10.6s; full 100-ticker grid 868.5s.

## 8. Out of scope / next steps

Per handoff, nothing was promoted to production and no production script, orchestrator, or cron
entry was touched. Suggested next experiments (deliberate future work):

1. **Regularization sweep** — rerun `qa_halflife_grid.py`-style walk-forward over `--reg-lambda`
   ∈ {0.01, 0.03, 0.1, 0.3, 1.0} with equal weighting; overconfidence should fall with stronger L2.
2. **Probability calibration** — post-hoc (e.g. temperature scaling on embargoed history) applied
   to production probabilities; Phase 3 tooling measures the improvement directly.
3. If a variant wins: promotion is a separate deliberate rewrite, per handoff.
