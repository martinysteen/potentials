# HANDOFF – Tunnel diagnostic (plots + table) for all Potentials tickers

**For:** Claude Code, working in the PotSystem repository on gandalf
**From:** Steen (spec drafted with Claude, 6 Oct 2026)
**Attached:** `tunnel_diag.py`, a working reference prototype that was tested on the live `longi_price` (1,229 tickers, daynum 1543–2249). It is the source of truth for the definitions below. Port it into the repo; don't redesign it.

---

## 1. Goal and scope

For **each ticker**, find the **longest log-linear tunnel that ends today**, then:

1. **draw it.** All tickers go into one PDF of A4 pages, 3 plots across and 6 down (5 down as an option).
2. **tabulate it.** One row per ticker in a CSV, using PotSystem's European format.

There is also a single-ticker mode (`--ticker MSFT`) that writes one PNG plus the same CSV row.

**Out of scope, on purpose:** validation, forecasting, ranking, scoring, trade signals, sector or macro analysis. This is a diagnostic so Steen can look at the tunnels. Don't add analysis columns or summary statistics.

**Relation to `HANDOFF_channel_scanner.md`** (if it is in the repo): this tool is the plotting and tabulating part only. Keep the definitions here. Don't build the validator or the agent steps from that document now.

---

## 2. Definitions

Work in **log prices** `y = ln(close)` against **trading-day index** `t = 0 … L-1`. Use trading days, not calendar days. A straight line in (t, ln price) means a constant % gain per trading day.

| Term | Definition |
|---|---|
| **Window** | The last `L` closes, ending at the newest close ("today" = the newest daynum in `longi_price`, or `--asof`). |
| **Slope `b`** | Default: OLS slope of `y` on `t` (`slope_method='ols'`). Option: `'minwidth'`, the slope of the narrowest band that contains every close (the "ruler" channel a person would draw). See §4. |
| **Lines** | Residuals `r = y − b·t`. Upper line = `b·t + max(r)`, lower line = `b·t + min(r)`. Every close in the window is inside or on the lines, and the lines are parallel. Midline = their average (dashed in the plot). |
| **Width** | `width_pct = 100·(exp(max r − min r) − 1)`: the % gain from the lower line to the upper line. It is the same at every t. |
| **Slope per 20 d** | `slope20_pct = 100·(exp(20·b) − 1)`: % gain along the lines per 20 trading days. |
| **Touch** | A close is a touch on the upper line if `r ≥ max r − touch_tol·h`, where `h = max r − min r`. The lower line works the same way. |
| **Support** | A cluster of touches. A new support starts when more than `cluster_gap` trading days pass without a touch on that line. `supports_upper` and `supports_lower` are the counts, and they are Steen's "tunnel quality". |
| **Span** | For each line: (last support day − first support day) / (L − 1). |
| **Tunnel exists for window L** | `width ≤ w_max` **and** both lines have `≥ min_supports` supports **and** both spans are `≥ min_span`. |
| **The tunnel** | The **longest** L from `l_min` up to the full history that satisfies this. If no L does → `no_tunnel`. |

Why each rule exists:
- **Supports ≥ 2 per line:** two points define a line. With only one touch, the "line" is just the most extreme close, and any price series has one of those.
- **Span ≥ 50 %:** stops a tunnel whose supports all sit in one corner of the window. Example: TXG today. Its May–June touches all fall early in the window, and its recent run-up breaks the pattern, so it gets `no_tunnel`.
- **Width cap:** without it, a wide enough band contains any price path.
- **Longest passing L:** Steen wants to see how far back the current tunnel reaches. Because of this rule, the window usually starts on a support: it extends back exactly until one more close would break a rule.

## 3. Parameters (defaults = the reference prototype)

| Name | Default | Meaning |
|---|---|---|
| `l_min` | 40 | shortest tunnel considered (trading days) |
| `w_max` | 0.40 | widest accepted tunnel (40 % lower→upper) |
| `touch_tol` | 0.10 | touch zone = 10 % of the band height next to each line |
| `cluster_gap` | 5 | touches ≤ 5 trading days apart = one support |
| `min_supports` | 2 | per line |
| `min_span` | 0.50 | per line |
| `slope_method` | `'ols'` | or `'minwidth'` |

Keep all of these in one config dict with CLI overrides (`--param key=value`). Print every non-default value in the PDF page header so each printout is self-describing.

**How strict the defaults are**, measured on the 2026-10-06 data (share of 1,229 tickers that get a tunnel):

| method | touch_tol | min_supports | w_max | tunnels | share |
|---|---|---|---|---|---|
| ols | 0.10 | 2 | 0.40 | **783** | **64 %** ← default |
| ols | 0.10 | 2 | 0.30 | 655 | 53 % |
| ols | 0.10 | 3 | 0.40 | 318 | 26 % |
| ols | 0.05 | 2 | 0.40 | 404 | 33 % |
| ols | 0.05 | 3 | 0.40 | 77 | 6 % |
| minwidth | 0.10 | 2 | 0.40 | 1026 | 83 % |
| minwidth | 0.05 | 3 | 0.40 | 209 | 17 % |

The defaults are deliberately loose: Steen sees many tunnels and filters on the supports columns afterwards. `min_supports=3` or `touch_tol=0.05` are the main knobs for tightening.

## 4. Algorithm notes

- **Input per ticker:** closes oldest→newest. Use only the **unbroken run of valid closes (> 0) ending today**. Leading NaNs are normal: 49 tickers are new listings. If today's close is invalid, or there are fewer than `l_min` closes → `insufficient_data`.
- **Loop** L = `l_min` … n, evaluate each window, keep the longest that passes. Don't stop at the first failure. Pass/fail is not monotone in L, and a longer window can pass again.
- **OLS:** plain closed form per window.
- **minwidth:** the narrowest vertical band always has the slope of one of the convex-hull edges. Build the upper and lower hull **incrementally while walking backwards from today** (monotone chain). After k points, the stacks are the hulls of the newest k closes, so one pass serves every L. Then try only the hull-edge slopes. The prototype was checked against a brute-force slope grid and is never wider.
- **Performance:** about 20 s for 1,229 tickers on 2 cores with a process pool. No further optimisation is needed.
- **Plots are rebuilt from the table row only:** `b = ln(lower_end/lower_start)/(L−1)`, and the lines start at `lower_start`/`upper_start`. This guarantees the CSV really describes the plot. Keep it that way, and keep a test for it.

## 5. Outputs

### 5.1 CSV: `tunnels_<YYYY-MM-DD>.csv` (one row per ticker, all tickers)
`;` separator, `,` decimal (PotSystem convention). Columns in this order:

| column | content |
|---|---|
| `ticker` | Yahoo-style ticker |
| `status` | `tunnel` / `no_tunnel` / `insufficient_data` |
| `length_td` | tunnel length in trading days (0 if none) |
| `width_pct` | % gain lower→upper line |
| `slope20_pct` | % gain per 20 trading days |
| `supports_upper`, `supports_lower` | support counts |
| `start_daynum`, `end_daynum` | first and last day of the tunnel (start empty if none) |
| `start_date`, `end_date` | the same days as dates, via `cal` |
| `lower_start`, `upper_start`, `lower_end`, `upper_end` | line prices at the first and last day |
| `last_close` | today's close |

Reference rows from 2026-10-06 (regression check):
```
MSFT;tunnel;45;6,11;1,95;3;2;2205;2249;2026-08-05;2026-10-06;476,0719;505,178;496,7117;527,0797;525,18
MU;no_tunnel;0;;;0;0;;2249;;2026-10-06;;;;;1063,96
^AEX;tunnel;72;3,66;0,84;2;2;2178;2249;2026-06-29;2026-10-06;1065,34;1104,3;1097,3293;1137,4591;1135,05
```

### 5.2 PDF: `tunnels_<YYYY-MM-DD>.pdf`
- A4 portrait, **3 across × 6 down** (`--rows 5` option). Today's run is 44 pages.
- **Default: tunnels only, alphabetical by ticker.** `--plot-all` also draws `no_tunnel`/`insufficient_data` tickers as a plain grey price line titled with their status.
- **Each panel:**
  - log-price y axis
  - **x axis = trading-day index, labelled with month starts (`yy-mm`).** A calendar-date axis makes the straight lines kink at weekends and holidays.
  - tunnel closes in dark blue, plus `max(60, L/2)` days of earlier history in light grey
  - upper and lower lines in green, midline red dashed (same style as the TXG chart Steen liked)
  - one orange dot per support, at its most extreme close
  - title = ticker. A small top-right label: `L 45 d   W 6%   S +1.9%/20d   sup 3/2`.
- **Page header:** `Tunnels ending <date> – <n> of <N> tickers – <non-default params> – page i/k`.

### 5.3 Single ticker
`--ticker MSFT [MU …]` → the same CSV and PDF restricted to those tickers, plus `tunnel_<TICKER>_<date>.png` (6×3.2 in, 150 dpi).

## 6. Data in the repo

- The prototype reads `longi_price.csv`: a wide table, row = ticker, column = daynum **newest first**, `;` and `,` decimal. It also reads `Cal.csv` (`Daynum;Date`, daynum written as `2278,00`). **Replace `load_prices()` with the repo's own loader** for longi_price/prices and the `cal` table (PostgreSQL on gandalf, if that is where the existing code reads from). Reuse the existing loader; don't write a new DB access layer.
- **Today's column is intraday.** Data refreshes hourly. At 13:15 CET, daynum 2249 (today) equalled 2248 for 72 % of tickers, because US markets hadn't opened yet. That is expected. "Ends today" means the newest column. `--asof <daynum>` lets Steen run it on the last complete day instead.
- Prices are in each ticker's own currency. That doesn't matter here, because everything is in % or log terms.

## 7. Implementation checklist

1. Put the code where the repo's conventions say. For example: a module `tunnels/fit.py` (pure functions plus the `Tunnel` dataclass, no I/O), `tunnels/plot.py`, and a CLI entry point. Use the `potsystem_env` conda environment. numpy, pandas and matplotlib are enough.
2. Keep `find_tunnel(ticker, closes, daynums, params) -> Tunnel` as the public function. It is the "data object" other code will call later.
3. **Tests:**
   - **Synthetic tunnel:** generate a price path that zig-zags inside known parallel lines (slope, width, 3 touches each side), append 60 random days before it, and assert that the length, width (±0.5 pp), slope and support counts are recovered.
   - **Random walk with a strong trend break at the end** → `no_tunnel` or a short tunnel.
   - **minwidth slope** vs a brute-force grid of slopes: never wider.
   - **CSV round trip:** lines rebuilt from the row have slope `slope20_pct` and width `width_pct`, and the last close is inside them.
   - **Regression:** on the 2026-10-06 snapshot, 783 / 446 / 0 for tunnel / no_tunnel / insufficient_data, and the three rows in §5.1 match.
4. Output folder via CLI or config, dated filenames, no overwriting of other days.
5. Optional, only if Steen asks: a cron line in `orchestrator.sh` after the data refresh. Not part of this task.

## 8. Choices left to Steen (defaults are already set, so nothing blocks the build)

- Tunnel strictness: `w_max`, `touch_tol`, `min_supports` (see the table in §3).
- `ols` vs `minwidth`. OLS follows the trend through all closes. Minwidth hugs the extremes and gives longer tunnels.
- Page order: alphabetical (default) or e.g. by sector (Stamdata `Sector2`) or by length.
- 6 or 5 rows per page.
