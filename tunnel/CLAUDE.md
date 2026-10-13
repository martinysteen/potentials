# tunnel — price-tunnel diagnostic

For each ticker: the **longest log-linear tunnel (parallel trend channel) that ends at the
newest close**, drawn into an A4 PDF (3 × 6 panels) and tabulated in a European CSV.
Diagnostic only — no scoring, ranking or signals.

**Nightly publish (2026-10-12):** `tunnel/run_tunnel.sh` (cron `0 0 * * *`, also the manual
entry point, flock-guarded) rebuilds `app/output/all/` — every ticker, LB100 **and** LB250 — into
`all.new/`, swaps it in only if both runs succeed, then publishes via `repository.py publish tunnel`
to Drive + mirror `repositoryRTBI/data/Tunnel/all/`. `all/` holds only the newest run, so the
scoped sync retires yesterday’s dated files on Drive too (older days: rerun with `--asof`). ~2½ min.
Log `~/logs/run_tunnel.log`. Other `app/output/<subdir>/` folders are manual runs, never published.

- Spec: [handoff/HANDOFF_tunnel_plots.md](handoff/HANDOFF_tunnel_plots.md) (definitions, CSV
  columns, plot layout). `handoff/tunnel_diag.py` is the original prototype, kept for reference.
- Code: [app/code/tunnel_diag.py](app/code/tunnel_diag.py) (fit + plot + CLI, `find_tunnel()`
  is the public function), [app/code/preflight.py](app/code/preflight.py) (input list +
  snapshot, same mechanics as potrank/strategy_grp2 via `shared/datacheck.py`).
- Output: `app/output/tunnels_<date>_LB<lookback>[_strat|_topN].{csv,pdf}` + `_p1.png`.
  Not tracked in git (regenerable).
- PDF panels of the specialised selections (strategic, top, growth — NOT `all`, SM's choice,
  where each panel fits its own data) share ONE scale per file (2026-10-13, `common_scale()`): same trading days across
  (1.25 × lookback, all ending today) and same log span up (fits the file's tallest tunnel, each
  tunnel centred), so W and S compare by eye. Stated in the page header. Single-ticker PNGs fit
  their own data.
- Selection-wide plots (2026-10-13): [app/code/tunnel_spread.py](app/code/tunnel_spread.py) adds
  `_hist.png` (S in 8 buckets of s around mean(S), ends = outliers beyond ±3s; `all` runs only,
  SM: of little use on specialised selections) and `_SW.png`
  (S vs W; labels the outliers; below 250 tunnels everything beyond ±2s, below 150 beyond ±1s, below 50 every dot) next to each run's CSV; tunnel rows only, s = std of S incl. outliers.
  Called by every `tunnel_diag.py` run except `--ticker`; `python tunnel_spread.py [dir|csv …]`
  backfills (default `output/all`). They match `tunnels_*.png`, so the nightly publish carries them.

## Run (on the server, like all python)

```bash
cd ~/potentials/tunnel/app/code
python tunnel_diag.py                                   # newest StrategicStocks tickers (default)
python tunnel_diag.py --universe top --top 100          # best 100 of longi_rank.csv (rank 1 = best)
python tunnel_diag.py --universe all                    # all ~1,229 longi_price tickers
python tunnel_diag.py --universe all --param lookback=250
python tunnel_diag.py --universe growth --out ../output/topGrowth   # S >= mean+2s of all (--sigma)
```

## Where the port deliberately differs from the handoff (2026-10-06)

| Param | Handoff | Now | Why |
|---|---|---|---|
| `slope_method` | `ols` | **`minwidth`** | SM's standard: hugs the extremes, longer tunnels |
| `lookback` | (full history) | **100** | only the recent N closes are searched; 250 ≈ 1 year as an override |
| `l_min` | 40 | **20** | |
| `w_max` | 0.40 | **0.5** (0 = no cap) | removed, then 100 % after the 250-d run produced 205–358 % "tunnels"; **50 % since 2026-10-13** (SM): drops the few very wide extreme-slope names (PACB +83 %/20d), S skew 1.4–2.0 → 0.3–0.45. Still not Gaussian (peaked centre, ±3s tails ~5–8× normal) |
| universe | all | **StrategicStocks** (+ `top`, `all`) | |

So the handoff's regression numbers (783/446/0, the MSFT/MU/^AEX rows) do **not** apply to the
current defaults.

Reference results, daynum 2253 (2026-10-12), current defaults (w_max 0.5):
all/LB100 → 1,033 tunnel / 194 no_tunnel; all/LB250 → 1,161 / 66.
(Before 2026-10-13, at w_max 1.0, daynum 2249: all/LB100 998/231, all/LB250 1,167/62.)

## Open

- **No tests yet** — the handoff §7.3 list (synthetic tunnel, trend break, minwidth vs brute
  grid, CSV round trip) still to be written.
- Near-zero-width tunnels are cash-likes / deal-pinned stocks (IBTA.L 0.6 %, DBRG, MTB-PH):
  correct but uninteresting. A `w_min` filter was offered, not decided.
