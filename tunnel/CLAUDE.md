# tunnel — price-tunnel diagnostic

For each ticker: the **longest log-linear tunnel (parallel trend channel) that ends at the
newest close**, drawn into an A4 PDF (3 × 6 panels) and tabulated in a European CSV.
Diagnostic only — no scoring, ranking or signals.

**Nightly refresh + publish works on all of `app/output/` (SM, 2026-10-13).** Every subfolder is
a selection; they are rebuilt together and published together. `tunnel/run_tunnel.sh` (cron
`0 0 * * *`, also the manual entry point, flock-guarded) runs each folder's **recipe**
`app/output/<folder>/tunnel_runs.txt` (one line of `tunnel_diag.py` args per run, `#` comments)
into `app/output.new/<folder>/`, swaps `output.new/` in for `output/` only if every run of every
folder succeeded, then `repository.py publish tunnel` → Drive + mirror `repositoryRTBI/data/Tunnel/<folder>/`
(owner pattern `/*/**`). ~1 min. Log `~/logs/run_tunnel.log`.

- **New selection** = new folder + `tunnel_runs.txt`; no script edit. A folder without a recipe is
  carried over unchanged (log WARNING), published but never refreshed.
- Recipes are the only git-tracked files under `app/output/` (`.gitignore` exception).
- `output/` holds only the newest runs, so the scoped sync retires yesterday's dated files on Drive
  too (older days: rerun with `--asof`). Deleting a folder locally deletes it on Drive.
- Loose files directly in `app/output/` are dropped by the nightly swap and fail an ad-hoc publish
  (unclaimed). Scratch runs: `--out /tmp/...`. Immediate refresh: just run `run_tunnel.sh`.

| Folder | Recipe |
|---|---|
| `all/` | `--universe all`, LB100, **4 × 7** panels per page |
| `all_GICS/` | `--universe gics`, LB100, 4 × 7: PDF grouped GICS > Sector2 (below) |
| `FastStrategy/` | `--universe strategic`, LB100 |
| `topGrowth/` | `--universe growth --sigma 2`, LB100 |
| `ZOP/` | `--universe zop`, LB100: tickers marked `ZOP` in `longi_macd_Z` on the newest day |
| `personal/SM/` | `--universe flag --flag SM_ejet`, LB100: SM's own holdings (Stamdata flag, indices left out) |

2026-10-15 (SM): LB250 dropped from the standard recipes (add `--param lookback=250` to a recipe
to bring it back); `Rank_top100/` erased (`--universe top` still exists). Specialised selections
stay 3 × 6; `--cols/--rows` set per recipe line. **A group folder** (`personal/`) holds selections
one level down, each with its own recipe; `run_tunnel.sh` handles it, `.gitignore` tracks the
nested recipe. `personal/SM/` is **published like every folder** (SM's decision, to be discussed
with the inner circle; if they object, make it private by narrowing `OWNERS["tunnel"].owns`).
Ownership by folder placement is a stopgap, a better way to say whose report it is comes later.

**`all_GICS` PDF** (`write_pdf_grouped`): page 1 is an index (every GICS and Sector2 a clickable
link with page numbers), the PDF bookmark tree is GICS > Sector2 (collapsed; written by a
`PdfFile` subclass swapped in by `pdf_with_outline`, relies on matplotlib 3.10 internals, no
PDF library installed). Each GICS opens with a divider page (name only); Sector2s flow on within
it, each opened by a dark banner. Own-scale panels. PNGs: one tall PNG per GICS in `png_GICS/`.
Hist/S-W: ONE file each with a panel per GICS (`tunnel_spread.write_spread_grouped`). CSV gains
`GICS`, `Sector2`.

**Panel label / CSV (2026-10-15):** spec line `W 12%  S20d +1.5%  closePos 0.37`, company name
(Stamdata `Name`) above it, same font; the PDF/PNG header and the CSV top-left cell carry the same
creation stamp. CSV decimals fixed: width, slope20 1; line prices, last_close, close_pos 2.
`close_pos = (last_close - lower_end)/(upper_end - lower_end)`, last CSV column (before GICS/Sector2).
Stamdata.csv is a standing input of every run.

- Spec: [handoff/HANDOFF_tunnel_plots.md](handoff/HANDOFF_tunnel_plots.md) (definitions, CSV
  columns, plot layout). `handoff/tunnel_diag.py` is the original prototype, kept for reference.
- Code: [app/code/tunnel_diag.py](app/code/tunnel_diag.py) (fit + plot + CLI, `find_tunnel()`
  is the public function), [app/code/preflight.py](app/code/preflight.py) (input list +
  snapshot, same mechanics as potrank/strategy_grp2 via `shared/datacheck.py`).
- Output: `app/output/<folder>/tunnels_<date>_LB<lookback>[_strat|_topN|_growthNs].{csv,pdf}`. (The
  page-1 preview `_p1.png` is commented out since 2026-10-13 — one line in `main()` to reinstate.)
  **Viewer-free PNG, 2026-10-14, every selection except `all`** (strategic, top, growth): ALL pages
  stacked into ONE tall PNG, `tunnels_LB100_strat_latest.png` / `_top100_` / `_growth2s_` —
  deliberately UNDATED so a link in a Google Sheet stays stable across nights. (Multipage TIFF
  rejected: browsers and Sheets `IMAGE()` don't show it.) `all` gets none (~1,000 tickers).
  Height ≈ 1,070 px per page at 110 dpi (top100 ≈ 6,400 px, 0.9 MB).
  Not tracked in git (regenerable). CSV top-left cell (header of the ticker column) = creation
  stamp `dd-mm-yyyy hh-mm` (2026-10-13), as in PotDat/longi_*; readers rename column 0 to `ticker`.
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

**Historical tunnels (2026-10-23, built, cron NOT yet added):** `app/code/tunnel_history.py` fits all
tickers for EVERY daynum in longi_price (~720, production; `--days 250` while developing, `--every N`)
into ONE long CSV `app/output/history/tunnels_history_LB100.csv`, rows `[daynum, ticker]` + all the
usual columns, no plots. Row (D,T) is identical to `tunnel_diag.py --ticker T --asof D` (checked).
**Always a full rebuild, never incremental** (SM: PotDat/Stamdata are corrected across the whole
past). Measured: 250 days = 8 min, 310,000 rows, 29 MB (all ~720 days ~ 25 min, ~85 MB).
`run_tunnel_history.sh` (shares `/tmp/tunnel.lock`, waits up to 30 min) rebuilds + publishes;
proposed cron `20 0 * * *`. `run_tunnel.sh` carries `history/` across its nightly swap without a
WARNING. Plan for on-demand (MCP) and intraday refresh: items 2 and 3 of
`~/.claude/plans/my-ideas-for-next-synthetic-lobster.md`.

**On-demand report (2026-10-23, built; goes live after the 3 sudo steps below):** MCP tool
`tunnel_report(tickers, end_date, name)` in repositoryRTBI/mcp/server.py -> `app/code/tunnel_ondemand.py`
(also usable by hand: `python tunnel_ondemand.py MSFT MU --date 2026-09-30 --name x`). Runs
`tunnel_diag.py --live --plot-all --ticker ... --asof-date D` (live repository, no snapshot, so it never
collides with the nightly run) into `/srv/tunnel-reports/<name>_<random token>/`: CSV, PDF, one tall
PNG, a PNG per ticker when <= 6. Served read-only by Caddy at https://innovia.dk/tunnel-reports/<folder>/
(link = the only access; folders > 7 days old are deleted on the next call). Max 200 tickers, one report at
a time (flock). Not under app/output/, so never published to Drive. `--asof-date` and the tall PNG for
`--ticker` runs are new tunnel_diag options. Live steps (sudo): `sudo mkdir /srv/tunnel-reports && sudo chown sm:sm
/srv/tunnel-reports`; copy repositoryRTBI/Caddyfile to /etc/caddy/Caddyfile and `sudo systemctl reload caddy`;
`sudo systemctl restart rtbi-mcp`.

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
