# tunnel — price-tunnel diagnostic

For each ticker: the **longest log-linear tunnel (parallel trend channel) that ends at the
newest close**, drawn into an A4 PDF (3 × 6 panels) and tabulated in a European CSV.
Diagnostic only — no scoring, ranking or signals. Manual runs; no cron; publishes nothing.

- Spec: [handoff/HANDOFF_tunnel_plots.md](handoff/HANDOFF_tunnel_plots.md) (definitions, CSV
  columns, plot layout). `handoff/tunnel_diag.py` is the original prototype, kept for reference.
- Code: [app/code/tunnel_diag.py](app/code/tunnel_diag.py) (fit + plot + CLI, `find_tunnel()`
  is the public function), [app/code/preflight.py](app/code/preflight.py) (input list +
  snapshot, same mechanics as potrank/strategy_grp2 via `shared/datacheck.py`).
- Output: `app/output/tunnels_<date>_LB<lookback>[_strat|_topN].{csv,pdf}` + `_p1.png`.
  Not tracked in git (regenerable).

## Run (on the server, like all python)

```bash
cd ~/potentials/tunnel/app/code
python tunnel_diag.py                                   # newest StrategicStocks tickers (default)
python tunnel_diag.py --universe top --top 100          # best 100 of longi_rank.csv (rank 1 = best)
python tunnel_diag.py --universe all                    # all ~1,229 longi_price tickers
python tunnel_diag.py --universe all --param lookback=250
```

## Where the port deliberately differs from the handoff (2026-10-06)

| Param | Handoff | Now | Why |
|---|---|---|---|
| `slope_method` | `ols` | **`minwidth`** | SM's standard: hugs the extremes, longer tunnels |
| `lookback` | (full history) | **100** | only the recent N closes are searched; 250 ≈ 1 year as an override |
| `l_min` | 40 | **20** | |
| `w_max` | 0.40 | **1.0** (0 = no cap) | was removed entirely, then reinstated at 100 % after the 250-d run produced 205–358 % "tunnels" |
| universe | all | **StrategicStocks** (+ `top`, `all`) | |

So the handoff's regression numbers (783/446/0, the MSFT/MU/^AEX rows) do **not** apply to the
current defaults.

Reference results, daynum 2249 (2026-10-06), current defaults:
all/LB100 → 998 tunnel / 231 no_tunnel; all/LB250 → 1,167 / 62; top100/LB100 → 78 / 22;
top100/LB250 → 91 / 9.

## Open

- **No tests yet** — the handoff §7.3 list (synthetic tunnel, trend break, minwidth vs brute
  grid, CSV round trip) still to be written.
- Near-zero-width tunnels are cash-likes / deal-pinned stocks (IBTA.L 0.6 %, DBRG, MTB-PH):
  correct but uninteresting. A `w_min` filter was offered, not decided.
