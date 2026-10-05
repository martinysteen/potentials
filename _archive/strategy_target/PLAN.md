# strategy_target — interactive tunnel drawing, machine bids / you correct

## Context

`strategy_grp2 --production` publishes `StrategicStocks_<daynum>.csv` (15 rows) to Drive, from
where the **PotRank_FastStrategy** Google Sheet imports it and adds indicators. That sheet is what
users get. The premise was that the list is enough to pick winners; it has not worked out, because
the **spread of outcomes is uncomfortably wide** even when the average is acceptable. Users
therefore go to TradingView and hand-draw **tunnels** on logarithmic price plots, reading targets
off the upper rail and skipping anything too chaotic to tunnel. Doing that daily for 15 names is
the chore to automate.

The list is measurably blind to where a name sits in its own range — on daynum 2242, ALAB sat at
the very top of its channel (+1.8% to the ceiling, −29.8% to the floor) while SOFI sat near the
bottom (+13.7% / −4.1%). Same list, same day, opposite risk/reward.

**This is a circular learning process, not a scoring pipeline.** The machine makes a first bid at
a reasonable tunnel; SM corrects it; the correction is kept and shapes the next bid. SM's
judgement is the scarce good, and the system's job is to capture and distribute it — not to
replace it with a statistic.

---

## How to read this document

This is a **living spec with a decision log**, in the same style as
`strategy_grp2/DesignVersion2.md` — revisions are recorded with their reason, not silently
replaced. Sections marked *(carried forward)* were settled in the first draft and are unaffected
by later changes of direction; they are infrastructure facts about this repo, not design opinions.

## Decision log

**2026-09-25, draft 1 — dismissed by SM.** Proposed a cron-driven batch: fit tunnels three times a
day, score them, publish, with a fixed statistical gate deciding what users see. SM: *"This is
machine learning, not AI. I imagine a circular learning process, where machine proposes something,
and user modifies."*

**2026-09-25, draft 2 — the revision below.** What changed and why:

| Dismissed | Now | Reason |
|---|---|---|
| Cron at `:32`/`:02`, batch publish | **No cron.** Fitted when SM asks | SM: "everything live and interactive" |
| Credibility score gates the output | Score only **prunes** before presenting | The gate usurped the judgement that is the whole product |
| Symmetric ±2σ envelope | **Parallel channel, 3 DOF** | SM: TradingView shows 6 linked handles = 3 real DOF |
| Rails always contain every extreme | Rails at independent quantiles | SM wants "peaks punching upper", "vague underpinning" below |
| One-shot output | Bid → correct → store → learn | The circular process is the point |
| Per-user question open | **Master only** — SM's drawings | SM's answer; a learning loop needs one teacher |
| PNG/XLSX rendering, matplotlib | Client-side chart, no images | Follows from the page being interactive |

**Carried forward unchanged from draft 1** (verified against the source, still true):
the double-registration discipline and the `OWNERS` entry; the `datacheck._is_matrix()` exemption
that forces a local vintage check; the `rclone sync` "Drive holds only the current daynum" caveat;
the `_read_flat()` fix for `StrategicStocks_*.csv`; the stale cron lines in root `CLAUDE.md`; the
Durbin-Watson honesty caveat; and the Step 0 validation gate.

**Still open:** whether draft 1's batch mode should ever return as an *additional* path — once SM
has accepted tunnels, re-checking them against fresh prices each morning is cheap and needs no
judgement. Not proposed now; noted so the idea is not lost.

---

## The tunnel model

TradingView's Parallel Channel shows six handles — four corners plus a midpoint on each rail — but
they are linked, so it is **three degrees of freedom**, and both rails stay parallel. In
log-price space a tunnel is therefore exactly:

```
(window_start, window_end,  slope b,  base_level a,  width w)     # all in ln(price)
upper(t) = exp(a + w + b*t)          lower(t) = exp(a + b*t)
```

Stored per ticker; that is the whole data model.

**Calculations in `ln(price)`, plots in price.** SM asked whether to compute on
`longi_per1d.csv` instead, since log-linearity is assumed. Checked, and it costs accuracy for
nothing: `longi_per1d` is itself derived from `PotDat` closes (reproducing it straight from prices
matches to an RMS of 0.01–0.03 percentage points — pure 2-decimal rounding), NaN coverage is the
same (110 vs 108 over 120 days), and accumulating those rounded returns back into a log path
drifts monotonically to **0.15–0.36% over 120 days**, worst at the long windows where a tunnel
matters most. `ln(price)` *is* the exact constant-%-per-day path; per1d is the rounded version of
the same thing.

---

## The first bid

1. **Sweep windows** — 20, 30, 40, 50, 60, 75, 100, 150 days.
2. **Fit each** — OLS slope on `ln(price)`; detrend; place the two parallel rails at residual
   quantiles (`q_dn`, `q_up`), default **0.05 / 0.95** rather than the absolute extremes.
   Anchoring to extremes is what produces nonsense: ALAB at 150d comes out **197% wide**.
3. **Throw out the obvious bad** — width beyond a usable ceiling, fewer than ~2 separated touches
   on either rail, or today's price far outside the channel (it just broke). Pruning only; nothing
   is silently *chosen* for SM.
4. **Rank survivors by cross-window stability**, not by fit quality. A channel that says the same
   thing at 50, 75, 100 and 150 days is real; one that only exists at a single window is an
   artefact. SOFI is 26–30% wide across all four (real); ALAB swings 36% → 197% (fragile). This
   replaces R², which is actively misleading here — a flat, perfectly tradeable horizontal channel
   scores R²≈0 purely for being flat.
5. **Present the best plus one alternative**, drawn, with the numbers that follow from them.

Honesty note for the spec: the rails are a **descriptive envelope**, the same thing a human draws
by hand. Measured Durbin-Watson on the residuals is 0.12–0.84 (strongly autocorrelated), so no
probabilistic claim may be attached to them.

---

## The correction loop

SM adjusts any of the five numbers, two ways, on the same view:

- **Direct** — drag the handles, exactly like TradingView. This is always available and always
  works.
- **Plain language** — "let the top be punched by the two spikes", "looser underneath", "start it
  later", "use 60 days". Verified this knob is meaningful: on ALAB/100d, moving `q_up` from 1.00 to
  0.95 lets 5 days poke through and pulls the target from 470 (+30.6%) to 408 (+13.4%).

### Language backend: local Ollama — benchmarked, viable as a convenience

Ollama is already live as a systemd unit with `gemma4:26b` and `gemma4:e4b` pulled. No API key, no
per-message cost, nothing leaves the machine. **The server has no GPU** (8 cores, 30 GB RAM), so
everything runs on CPU. Measured on `gemma4:e4b`:

| Model | Setup | Warm latency | Accuracy |
|---|---|---|---|
| e4b | Zero-shot, rich 9-field JSON schema | 27.7 s mean | **0/8** — every answer `unknown` |
| e4b | Zero-shot, 2-field JSON schema | 7.7 s | **Wrong idiom** — "peaks punch the upper line" → `none` |
| e4b | Few-shot, 4-field JSON schema | 12–15 s | 6/6 correct |
| **e4b** | **Few-shot, terse single token** | **8.1 s** | **7/8** — `"this one is hopeless"` → `ACCEPT` |
| 26b | Zero-shot, rich schema | 30–87 s, **half timed out at 180 s** | unusable |

Findings that shape the design:

- **Output-space size dominates, more than token count.** The rich nullable-enum schema did not
  merely slow e4b down, it broke it — 0/8, everything `unknown`. Collapsing the answer to one
  token from a fixed vocabulary took it to 7/8. Keep the output space tiny.
- **Few-shot examples are mandatory.** Zero-shot gets the single most important idiom backwards:
  letting peaks punch through a rail makes it *looser*, and the model called it "none".
- **`gemma4:26b` is out** — measured, not assumed: 18 GB on 8 CPU cores times out.
- Two bugs to fix in the prompt: add a `REJECT` exemplar (the `"hopeless"` miss would accept a
  tunnel SM wanted discarded), and map the empty reply on off-topic input to `NONE`.
- Keep the model resident with `keep_alive: 30m`; a cold call pays +48 s to load 9.6 GB.

**Decision: hybrid, drag handles primary.** A deterministic pre-parse handles the common,
unambiguous commands (`use 60 days`, `shorter`, `accept`) instantly by regex; only genuinely fuzzy
phrasing falls through to gemma4:e4b at ~8 s. Handles remain the fast path and always work, so an
8-second sentence is an occasional convenience rather than the mechanism. This keeps everything
local and free, and it works for any future user rather than only at SM's terminal.

Every accepted tunnel is written with the bid that preceded it, so the correction itself is the
record.

---

## The learning loop

`accepted.csv` accumulates one row per accepted tunnel: ticker, the machine's bid, SM's final
parameters, and features of the series at the time (volatility, trend strength, sector, price
level). This is the training data, and it is the point of the whole design.

Start with the honest version — **not** a model:

- **Tier 1 (immediately):** per-ticker memory. If SM drew ALAB at 78 days with a punched top last
  week, that is the starting bid this week, aged out after N sessions.
- **Tier 2 (once there are ~100 accepted tunnels):** learn the *defaults* — which window lengths
  and quantiles SM tends to land on, conditioned on volatility and sector. A shallow fit
  (per-bucket medians, or a small regression) is the right size; `sklearn` is available if it
  earns its place.
- **Tier 3 (only if tier 2 pays):** predict the corrections themselves.

Do not build tiers 2-3 up front. Tier 1 alone will visibly improve the bid, and the accumulated
file is what makes the later tiers possible — collecting it from day one is the load-bearing part.

---

## Delivery to users

**Master only.** One set of tunnels, SM's, seen by everyone. A corrective loop needs one coherent
teacher, and per-user drawing would hand the manual chore back to every user.

When SM accepts, targets publish on that action — not on a timer:
`TunnelTargets_<daynum>.csv` → `repository.publish(OWNERS["strategy_target"], target="both")` →
`GoogleDrive:PotSystem/repositoryRTBI/Target/` → the Sheet pulls it with the existing
`UrlFetchApp` recipe (`repositoryRTBI/USE_CASE_DOWNLOAD.md:84-124`).

Columns: `daynum;ticker;name;window;slope_pct_day;width_pct;pos;price;sell_target;sell_target_20d;
buy_ref;upside_pct;downside_pct;rr;touches_up;touches_dn;punched;drawn_by;drawn_at;source`
(`source` ∈ `machine | corrected`, so the sheet shows which SM personally signed off).
Tickers SM judged untunnelable are published with blank targets and a reason — flagged, not hidden.

`repository.publish` is `rclone sync`, so Drive holds only the current daynum; the Sheet must
resolve the name from `GET /files` rather than hardcoding a dated URL.

---

## Where it runs

Live and interactive, on the infrastructure that already exists — verified this session: Caddy on
80/443 with TLS for `innovia.dk`, uvicorn on 8765, systemd, **port 8766 free**, Ollama on 11434.

A small FastAPI service on 8766 behind a new `handle /tunnels/*` block in
`repositoryRTBI/Caddyfile` serves the page and the fit/refit/accept calls. The existing
`repositoryRTBI/api/main.py` is **not touched** — it is a deliberately narrow read-only CSV server
(`_safe_path` line 31 rejects every non-CSV suffix), and since the chart is drawn client-side from
JSON there are no PNGs to serve anyway.

Auth: the Sheet button is a plain hyperlink and a browser cannot send the existing `X-API-Key`
header, so use a long random token in the query string (`?k=…`) over TLS, validated server-side.
A bounded, deliberate trade-off for a single-user system — recorded as such, not an oversight.

---

## Files, registration and guards *(carried forward from draft 1)*

Everything in this section is a fact about how this repo works, established in draft 1 and
unaffected by the move to an interactive model.

```
strategy_target/
├── CLAUDE.md, DesignTunnels.md          entry card + living spec
└── app/
    ├── code/
    │   ├── channel.py      the 3-DOF fit: slope, base, width; pure numpy, no I/O
    │   ├── bid.py          window sweep, prune, cross-window stability ranking
    │   ├── language.py     Ollama client, JSON-schema constrained; vocabulary fallback
    │   ├── memory.py       tunnels.csv / accepted.csv read+write; tier-1 recall
    │   ├── targets.py      rails -> targets, TunnelTargets_<daynum>.csv
    │   ├── publish.py      repository.publish wrapper (warn, never fail)
    │   ├── validate_pos.py the Step 0 gate below
    │   └── shared/{config,data_loader}.py
    ├── api/{main.py, static/index.html, strategy-target-api.service}
    ├── control/{tunnels.csv, accepted.csv}
    └── report/TunnelTargets_<daynum>.csv
```

Reuse `strategy_grp2/app/code/shared/data_loader.py` (`load_potdat`, `load_stamdata`,
`daynum_to_date`, `lru_cache`, `DataUnavailable`) and potrank's `shared/config.py` shape. Add
`_read_flat()` for `StrategicStocks_*.csv` — it is a record table, so `index_col=0` is wrong and
`label` must stay a column.

**Vintage guard, lighter than before.** No cron means no frozen snapshot is needed, but the skew
hazard is real, and **`datacheck._is_matrix()` (verified at line 119) covers only `Longi/*` and
`PotDat.csv`** — `Strategy/StrategicStocks_*.csv` is exempt from the vintage rule. So on load,
assert the list's daynum equals `PotDat.csv`'s newest column and refuse loudly on mismatch: a
tunnel fitted on a different price generation than the pick list is exactly the silent failure
root `CLAUDE.md` warns about.

**`.gitignore` negation — load-bearing, easy to miss.** Line 7 blanket-ignores `*.csv`, so
`app/control/accepted.csv` — the accumulated record of SM's corrections, i.e. the whole learning
loop — would be untracked and never backed up by `git_pot.sh`'s 03:40 push. It needs the same
treatment `control_board.xlsx` already gets on line 47:

```gitignore
# --- strategy_target's tunnel definitions and correction history are hand-made INPUT,
#     not generated data — track them despite the blanket *.csv rule above ---
!strategy_target/app/control/tunnels.csv
!strategy_target/app/control/accepted.csv
```

Deliberately NOT negated: `app/report/TunnelTargets_*.csv` is generated output and stays ignored,
matching `StrategicStocks_*.csv`, which is also untracked. The distinction is hand-made input vs.
regenerable output. `**/app/data/input/` (line 37) already covers the snapshot root by glob, so
that needs nothing.

**Registration list 1** — `shared/app/code/repository.py`:
```python
"strategy_target": Owner(
    name="strategy_target",
    source=POTENTIALS / "strategy_target" / "app" / "report",
    input_dir=POTENTIALS / "strategy_target" / "app" / "data" / "input",
    subdir="Target",                       # not "Strategy" — never two syncs into one folder
    owns=("/TunnelTargets_*.csv",),
    needs=(), local_only=("*.cmd", "_archive/**"),
),
```
Create the directory tree **before** registering: `check_owner()` fails on a missing source dir and
`cmd_check()` returns 1 on any owner, so registering early breaks `repository.py check` system-wide.

---

## Step 0 — the gate (do this first)

`strategy_grp` was rejected for having no pre-trade signal ("6 candidates, all |r| ≤ 0.16"), so
test before building. Using `longi_future_per20d.csv` as realized forward gain across all daynums
and the full universe: **does position-in-tunnel narrow the _dispersion_ of outcomes?** Spread is
the complaint, not average. If it separates, build. If not, say so and stop.

This is also the one place the machine can be checked against SM: once there are a dozen
hand-drawn examples, compare the machine's bid to SM's drawing on the same names.

---

## Verification

1. `validate_pos.py` — the dispersion table. Gate.
2. Bid quality against SM's own examples: machine bid vs SM's tunnel on the supplied names.
3. `channel.py` reproduces the probe: ALAB/100d at `q_up=0.95` → 5 days punched, target ≈ 408
   (+13.4%); at `q_up=1.00` → 0 punched, target ≈ 470 (+30.6%). SOFI stable 26-30% wide across
   50/75/100/150d. These are the regression tests.
4. Vintage guard: list daynum ≠ PotDat daynum must refuse, naming both.
5. Language: ~20 real instructions → correct parameter change, with measured latency; nonsense
   input must return "unknown", never a silent wrong edit.
6. `repository.py check` clean; `TunnelTargets_<daynum>.csv` lands in both
   `repositoryRTBI/data/Target/` and Drive; `Strategy/StrategicStocks_*.csv` untouched.
7. `https://innovia.dk/rtbi-api/files` still 403s without a key — the existing service provably
   unaffected.

All Python over `ssh -p 2222 sm@innovia.dk` in `potsystem_env`. Never pip.

---

## Also needs fixing *(carried forward from draft 1)*

The committed cron docs are **wrong**. `crontab -l` shows `strategy_grp2/run_production.sh` at
**`16 8-23` and `46 8-23`** — twice an hour — not the `0 1,11,19` claimed by root `CLAUDE.md` and
`strategy_grp2/CLAUDE.md:69`. `potrank` likewise has two entries (`:25` and `:55`), not one. This
plan adds no cron of its own, but the stale lines should be corrected while we are here.

---

## Open

- **SM's example tunnels** for today's STRATEGY stocks — the most valuable input available. They
  define what "reasonable" means, they calibrate the first bid against real targets instead of my
  guesses, and they are the first rows of `accepted.csv`. Send these whenever convenient; the
  build does not block on them, but the bid quality does.
