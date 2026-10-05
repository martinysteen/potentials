# strategy_target — archived, never built

**Frozen. Do not edit, and nothing outside `_archive/` may read from here** (root `CLAUDE.md`).

## What it was

An interactive log-price "tunnel" (TradingView-style parallel channel, 3 degrees of freedom) drawn
over the daily `StrategicStocks_<daynum>.csv` list: the machine bids a channel, SM corrects it, and
the correction is stored and learned from. Motivation: users found the spread of outcomes on the
strategy list too wide, and the list is blind to a ticker's position within its range.

## Status at archive time

- Planned and approved 2026-09-25. **Zero code written** — only the empty `app/` skeleton.
- The Step 0 gate (`validate_pos.py`: does position-in-tunnel narrow the dispersion of forward 20d
  gains?) was **never run**, so the core premise is unproven either way.
- No cron, no `repository.py` family, nothing published to Drive.

Archived 2026-10-05 by SM's decision: deprioritised in favour of a new goal.

## Where the substance is

[PLAN.md](PLAN.md) — the full approved spec, verbatim, including the decision log and the
measurements made while planning (Ollama `gemma4:e4b` benchmark, rejection of rebuilding prices
from `longi_per1d`, ranking windows by cross-window stability instead of R²).
