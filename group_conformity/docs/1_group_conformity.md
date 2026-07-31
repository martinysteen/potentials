# Group Conformity Grader (GICS / Sector2)

Grades how closely each ticker tracks its own group (GICS or Sector2, from `Stamdata.csv`),
and tests whether low-conformity members are where extreme forward gains come from.
Motivated by `../strategy_grp`'s DomGICS_* family, which selects a *dominating* GICS sector
and then draws its best tickers — a member that moves independently of its sector could dilute
or distort that premise. Split out of `../correlation` (2026-07-29) into its own project once it
outgrew being one more `analyze_*.py` script there — different question, different input subset,
worth its own git-tracked home rather than living inside an archived/gitignored experiment folder.

## Scripts: `analyze_conformity.py`, `analyze_conformity_gains.py`

### Goal
1. Build a per-ticker, per-daynum **conformity grade** for both GICS and Sector2.
2. Answer, with data: do low-conformity members show more dispersion / worse tails in forward
   gain, and is any such pattern robust across history — not an artifact of one market regime?

### Usage
```bash
ssh -p 2222 sm@innovia.dk
conda activate potsystem_env
cd ~/potentials/group_conformity/app/code
python analyze_conformity.py          # builds the grade + validity controls
python analyze_conformity_gains.py    # buckets forward gain by conformity decile
```
Input is fetched by `../fetch_input.sh` (a subset: `Stamdata.csv`, `longi_per1d.csv`,
`longi_grp_{GICS,Sector2}_per1d.csv`, `longi_vola100d.csv`, `longi_future_per{20,50}d.csv` — not the
full Longi/PotDat set `../correlation/fetch_input.sh` pulls). It reads the **local mirror**,
`~/potentials/repositoryRTBI/data/`, not Google Drive; the list itself lives in the registry at
`~/potentials/shared/app/code/repository.py`.

### Why correlation, not beta
`longi_beta*.csv` is beta against the market/core index — a different question. The natural
in-house alternative, **sector beta**, factors as `corr × (σ_i / σ_sector)`: it bundles
conformity with a volatility ratio. Measured directly: raw deviation-from-sector correlates with
volatility at **r ≈ +0.95** (a relabeled volatility grade), while the correlation-based grade is
**orthogonal to volatility (r ≈ −0.02, see controls below)**. Correlation is also scale-free, so
one grade is comparable across a 226-member GICS sector and a 12-member Sector2 category. Sector
beta is still written out (`longi_sectorbeta_*.csv`) as a side-by-side check, not discarded.

### Methodology — the grade (`analyze_conformity.py`)
- Input is **daily returns** (`longi_per1d.csv`) only — `per5d/10d/20d/...` are overlapping trailing
  windows and would inflate any correlation built on them.
- **All `^`-prefixed tickers are excluded up front** (`^VIX`, `^BTC`, `^GSPC`, `^IXIC`, `^AEX`,
  `^FCHI`, `^FTSE`, `^GDAXI`, `^HSI`, `^OMX`, `^OMXC20`, `^OSEBX`, `^STOXX`, `^DJAFK` — 14 tickers)
  — indices/benchmarks, not real sector members; they aren't genuinely part of any Sector2 group.
  Removing them barely moved the controls or the verdict (see below), which is itself a useful
  robustness check — the earlier run's numbers weren't propped up by this artifact.
- For each ticker *i* at daynum *t*, the group return it is compared against is
  **leave-one-out**: `g₋ᵢ,ₜ = (Σ group returns − rᵢ,ₜ) / (n − 1)`. Mandatory, not cosmetic — a
  ticker's weight in its own *published* group mean is `1/n`, and group sizes here range from
  14–226 (GICS) to 2–74 (Sector2), so the self-inclusive mean is mostly a group-size readout for
  small Sector2 categories.
- `conf = corr(rᵢ, g₋ᵢ)` over a rolling 100-daynum window (`min_periods=60`). `beta = cov/var`
  from the same rolling terms, written alongside.
- Blanked wherever fewer than 5 other members remain after leave-one-out (kills the `n=2`
  Sector2 category, `Other[C-Di]`) or a ticker has no group label.

### Outputs
- `output/longi_conf_GICS.csv`, `output/longi_conf_Sector2.csv` — the grade, Longi-shaped
  (ticker × daynum), drop-in for `strategy_grp`'s `col_filter`/`bin_filter`/`rank_by` if ever
  wired in as a factor. **Also uploaded to the central `repositoryRTBI/Longi` store** (see
  `conformity_upload.py`) so they're consumable there without any extra plumbing.
- `output/longi_sectorbeta_GICS.csv`, `output/longi_sectorbeta_Sector2.csv` — the beta
  alternative, also uploaded centrally.
- `output/conformity_controls.csv` — four validity checks, all passed (2026-07-29 run,
  `^`-prefixed index tickers excluded):

  | control | GICS | Sector2 | reading |
  |---|---|---|---|
  | corr(conf, vola100d) | −0.006 | −0.018 | ≈ 0 — not a relabeled volatility grade |
  | corr(group_size, mean_conf), naive | −0.075 | −0.045 | small; residual self-inclusion bias direction |
  | corr(group_size, mean_conf), leave-one-out | −0.004 | +0.108 | small — the Sector2 residual is expected finite-sample attenuation (a small group's leave-one-out mean is itself noisier), not the 1/n bias the correction targets |
  | persistence, corr(confₜ, confₜ₊250) | 0.539 | 0.616 | matches the ≈0.62 banked in the `strategy_grp` intra-sector-conformity measurement — conformity is a real, persistent ticker property |
  | reconstructed group mean vs published `longi_grp_*_per1d.csv` | 0.999996 | 0.999998 | validates both the grouping join and the published grp files |

- `output/conformity_vs_gain.csv` — decile-bucketed `longi_future_per{20,50}d` stats (mean, median,
  std, P5, P95, %|gain|>10), by attribute × horizon × history-half × {conformity, beta} bucket.
  The `horizon` column holds `20d`/`50d` (literal trading days — the "seven-pack" ladder).
  **Rows written before 2026-07-31 are not comparable**, even where the numbers coincide:
  the original `future_gain{20,50}d.csv` also used 20/50-day horizons but entered on the
  signal day itself, whereas `longi_future_per*` enters the day after (there was also a
  same-day intermediate naming, `longi_future_per{1m,3m}.csv` at 22/66 days, superseded within
  the same session by this literal ladder). The headline findings survived the entry-day
  change — Sector2 dispersion still falls with conformity (ρ≈−0.68, holding in both
  half-splits), GICS still inconclusive.
- `output/conformity_vs_gain_hop_secondary.csv` — low-power corroboration (see below).
- `output/conformity_ranking_{GICS,Sector2}.csv` — **"who are they"**: one row per ticker,
  sorted group-then-`rank_within_group`. Columns: `group`, `group_size`, `name`, `n_valid_days`,
  `mean_conf` (whole history), `recent_conf` (trailing ~6 months, `RECENT_WINDOW=126`),
  `rank_within_group` — **same "small number is best" convention as `longi_rank.csv`**:
  `rank_within_group=1` is the *highest*-conformity ticker in its group; low-conformity members
  get high rank numbers. A single representative grade is meaningful because conformity persists
  (control above); `recent_conf` beside it flags names that are drifting rather than needing a
  full time-series column for that. Real extremes (Sector2, indices excluded): the `Gold` group
  sits almost entirely at the conforming end (AEM.TO, KGC, AGI, B, AU all ≈0.83–0.87 — gold miners
  share one dominant factor, the gold price); `Semi` splits cleanly by cap — big names LRCX/KLAC/
  AMAT ≈0.82–0.85, niche names Tokyo Electron/Resonac/Disco Corp ≈0.16–0.24, same group, opposite
  ends, a clean illustration of the effect. Laggards without an index-artifact explanation include
  Eutelsat (Telecom), Endesa (Oil&Gas), Enagas (Trpt_Ship(Ener)), CATL (Other[Indu]).
  **Kept local, not uploaded**: not Longi-shaped, and cheaply reproducible from the two matrices
  above at any time.

### `conformity_upload.py` — pushing the grade to central storage
Uploads exactly the four Longi-shaped matrices (`longi_conf_*`, `longi_sectorbeta_*`) to
`GoogleDrive:PotSystem/repositoryRTBI/Longi` — the same folder `repositoryRTBI/sync_rtbi.sh`
mirrors hourly into `repositoryRTBI/data/Longi`, which is what `../strategy_grp` actually reads
via `load_longi()` (`../strategy` was archived 2026-07-31, no further work planned). Everything
else in `app/output/` (rankings, controls, the
gains verdict) stays local — wrong shape for that folder's contract, and reproducible on demand.
It is a thin wrapper on `~/potentials/shared/app/code/repository.py`, which holds this
family's namespace declaration (`/longi_conf_*.csv`, `/longi_sectorbeta_*.csv`) and runs an
`rclone sync` **scoped to it**. Scoped that way the sync is authoritative over these four
files — so a retired output is actually cleaned up — and blind to the ~70 longi files sharing
the folder. This replaced `rclone copy --update`, which was safe for the neighbours but could
never remove anything. Never add an exclude list here: the previous arrangement required every
family to know every other family's filenames, and the one that got forgotten
(`longi_sectorbeta_*`) was silently deleted and restored every hour for weeks.

```bash
python conformity_upload.py                # or: bash ../upload_output.sh
python conformity_upload.py --dry-run      # what would transfer and what would be deleted
python ~/potentials/shared/app/code/repository.py check     # both guards, all families
```

### `run_conf.sh` — the cron entry point
Chains fetch → `analyze_conformity.py` → `analyze_conformity_gains.py` → `upload_output.sh`,
gating each step on the previous one's exit code, logging to `~/logs/run_conf.log`. Modeled on
`~/potentials/longi/start_longi.sh`. It deliberately does **not** call `sync_rtbi.sh` any more:
a producer's job ends when its own outputs are published, and refreshing the local mirror is
the mirror's business on the mirror's own cron. Cron-scheduled the same way `start_longi.sh`
is: this is the one entry point that should be cron'ed, not `fetch_input.sh`/`upload_output.sh`
individually.

**Cron placement matters now.** `fetch_input.sh` reads `longi_per1d` etc. from the local
mirror rather than from Drive, so this run must follow a `sync_rtbi.sh` tick that itself
followed longi's publish, or it grades an hour-old vintage. The chain is
`longi :15 → publish ~:17 → mirror :37 → run_conf :45 → publish ~:47 → mirror :55`.

```bash
bash ~/potentials/group_conformity/run_conf.sh
```

## Findings (2026-07-29 run, `^`-prefixed index tickers excluded)

**Two distinct effects showed up, with very different reliability:**

1. **Mean forward gain rises monotonically with conformity decile** — strong (Spearman
   ρ 0.84–0.90 over full history, all four attribute×horizon combinations) but **not robust**:
   it holds strongly in the second half of history (ρ 0.88–0.94) and is weak or reversed in the
   first half (ρ 0.54, 0.33, 0.56, and **−0.18** for Sector2/50d). This is the same sign-flip
   pattern that already killed the pre-trade-signal search in `strategy_grp` (every candidate
   there had |r| ≤ 0.16 and flipped sign between halves) — so despite the large headline number,
   **this is regime-dependent, not a usable signal**, and should not be read as "conforming
   stocks perform better."
2. **Dispersion falls with conformity — confirmed for Sector2, inconclusive (not disproved) for
   GICS.** `std_gain` by conformity decile: **Sector2** shows ρ ≈ **−0.62 to −0.68** over the full
   history, surviving 3 of 4 history-half splits (ρ −0.77/−0.65/−0.61; the fourth, 50d second-half,
   is −0.39 — same sign, below the robustness bar). **GICS** shows only ρ ≈ −0.28 to −0.44 in
   every split — same direction throughout, never decisive. That pattern (consistent sign,
   insufficient strength) reads as *underpowered*, not *absent*: GICS's 12 broad umbrella sectors
   (e.g. `Tech` spans 201 tickers from semis to software) make "conforms to its GICS" a much
   noisier peer-similarity signal than Sector2's ~50 narrow categories (`Semi`, `Bank`, `Gold`),
   which likely dilutes a real effect rather than ruling one out. Reading the raw deciles: the top
   conformity decile has the lowest `std_gain` and the shallowest left tail (`p5_gain`) in **all
   four** attribute×horizon tables; the bottom deciles are noisier and don't form a clean ramp.
3. **Secondary hop-level check** (`conformity_vs_gain_hop_secondary.csv`): correlating each
   DomGICS_* run's per-hop focusset mean/min conformity against that hop's realized gain, over
   ~116 hops (≈30 independent, per `strategy_grp`'s own overlap accounting). All six
   attribute/strategy combinations came out **positive** (0.03–0.16) — directionally consistent
   with finding 1 above, but far too weak and low-power on its own to decide anything.

**Bottom line:** the conformity grade is valid and useful (clean controls, real persistence,
excluding indices barely moved any number — a useful robustness check on its own), and there is a
genuine, moderately robust finding that **low-conformity Sector2 members carry more dispersion /
deeper downside tails** — the effect the project set out to test, confirmed for Sector2,
inconclusive for GICS. The stronger-looking "conformity → higher mean gain" result should
be set aside as regime-dependent until proven otherwise. Nothing here has been wired into
`strategy_grp` or `Stamdata.csv`. `Stamdata.csv` in particular can't take a locally-added column at
all — it's destructively re-synced from the upstream Google Sheet on every `fetch_input.sh` run —
so if the grade ever earns a place there it has to go into the Sheet itself, not this pipeline.
