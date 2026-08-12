"""
Step 4 — walk-forward evaluation: how much of a row's Step-3 backtest edge survives
out-of-sample. Ports strategy_grp v1's walkforward.py — the "candidate grid" of
parameter-sets there becomes one row's `wf_group` here: each board row already IS an
independent hop series (step3_backtest.build_hops), so there is no parameter re-sweep to
reconstruct, only a different set of candidates to pick from.

    train = [oldest daynum .. T - period]     pick the best candidate here (by chain_annual)
    test  = [T + 1 .. T + test_len]           score THAT candidate here, never re-picking

`T - period` is an embargo, not an off-by-one: a hop entered at daynum d does not realize
until d + period, so training up to T would let a hop closing inside the test window vote
on the candidate choice.

One GroupResult is produced per distinct CANDIDATE SET, not per row: a walk-forward test
is a property of the set of candidates being chosen between, so rows whose `wf_group`
resolves to the same set share one test and are listed together as its owners. (With
`wf_group` blank on every row — the default, "every other active D row sharing my
`period`" — all rows resolve to one identical set, and reporting that test once per owner
printed the same fold table N times under N different headings.) All candidates in a test
must share one `period` — a mixed-horizon comparison is rejected, mirroring strategy_grp
v1's rule that a comparison never mixes holding lengths.

A test's Summary describes the SELECTED candidate each fold, so it says how well
selection-by-training-performance travels — it is not any one row's own out-of-sample
result. `summarize_candidates()` gives that: every candidate's own IS/OOS numbers over the
same folds, which is what a "how did each of my four strategies do out of sample?"
comparison needs.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import pandas as pd

import step3_backtest as bt
from shared import market
from shared.data_loader import daynum_to_date

DEFAULT_MIN_TRAIN = 315
DEFAULT_TEST_LEN = 63


def build_folds(dn_min: int, dn_max: int, min_train: int, test_len: int,
                period: int) -> list[tuple[int, int, int, int]]:
    """(train_floor, train_cap, test_floor, test_cap), oldest first. A trailing remainder
    shorter than `period` is dropped — it cannot contain even one complete holding window."""
    out: list[tuple[int, int, int, int]] = []
    t = dn_min + min_train
    while t < dn_max:
        test_hi = min(t + test_len, dn_max)
        if test_hi - t >= period:
            out.append((dn_min, t - period, t + 1, test_hi))
        t += test_len
    return out


def _lots_for(hops: list["bt.Hop"], params: dict,
             floor_daynum: int, cap_daynum: int) -> list[tuple[float, float]]:
    """(hop gain, benchmark gain) for every gated, realized hop in [floor, cap] — the
    per-hop pool `_pooled`/zeroskill/oracle are drawn from, matching v1's window_metrics."""
    threshold = params.get("no_go_gspc_rsi")
    lots: list[tuple[float, float]] = []
    for h in hops:
        if not h.realized or h.daynum < floor_daynum or h.daynum > cap_daynum:
            continue
        if not bt.gate_ok(h, threshold):
            continue
        gain = market.hop_avg(h.gains)
        if pd.isna(gain):
            continue
        lots.append((gain, h.mkt_gain))
    return lots


def _pooled(lots: list[tuple[float, float]]) -> tuple[float, float, int]:
    """(mean gain, mean alpha, n) over pooled lots — NaN market values dropped for alpha."""
    if not lots:
        return float("nan"), float("nan"), 0
    gains = [g for g, _m in lots]
    alphas = [g - m for g, m in lots if pd.notna(m)]
    return (statistics.fmean(gains),
            statistics.fmean(alphas) if alphas else float("nan"),
            len(gains))


def _shape(gains: list[float]) -> tuple[float, float]:
    """(median lot gain, % of lots positive) — the shape behind the mean. This family's
    returns are right-tail driven by construction, so a mean alone cannot tell a broad
    edge from one lottery ticket (see strategy_grp v1's walkforward.py for the spr100d
    fold that made this concrete: mean 61.48 on median 24.29, one ticker +1552%)."""
    if not gains:
        return float("nan"), float("nan")
    return statistics.median(gains), 100.0 * sum(g > 0 for g in gains) / len(gains)


@dataclass
class GroupResult:
    owners: list[str]                       # every row that declared THIS candidate set
    candidate_labels: list[str]
    period: int
    folds: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    pooled_selected: list[tuple[float, float]] = field(default_factory=list)
    pooled_all: list[tuple[float, float]] = field(default_factory=list)
    pooled_by_label: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    span: tuple[int, int] = (0, 0)

    @property
    def owner(self) -> str:
        return self.owners[0]


def resolve_candidates(owner_label: str, owner_row: dict, active_rows: dict[str, dict]) -> dict[str, dict]:
    """Candidate label -> resolved params for one row's walk-forward test. `active_rows` is
    every active, cleanly-parsing row's resolved dict, keyed by label."""
    wf_group_raw = str(owner_row.get("wf_group") or "").strip()
    if wf_group_raw:
        names = [n.strip() for n in wf_group_raw.split(",") if n.strip()]
        candidates = {n: active_rows[n] for n in names if n in active_rows}
    else:
        candidates = dict(active_rows)
    candidates[owner_label] = owner_row       # the owner is always a candidate for itself
    return candidates


def walk_group(owners: list[str], candidates: dict[str, dict], settings: dict,
              min_train: int = DEFAULT_MIN_TRAIN, test_len: int = DEFAULT_TEST_LEN,
              hops_cache: dict[str, tuple[list["bt.Hop"], dict]] | None = None
              ) -> GroupResult:
    """Run every fold for one candidate set, owned by `owners`. Raises ValueError if the
    candidates mix `period` values.

    `hops_cache` (label -> the `build_hops` pair Step 3 already produced for that row) is
    reused as-is: `build_hops` is deterministic in `row_resolved`, so re-simulating a
    candidate here would only redo the tick's most expensive loop for an identical answer.
    """
    hops_cache = hops_cache or {}
    hops_by_label: dict[str, list[bt.Hop]] = {}
    params_by_label: dict[str, dict] = {}
    missing = [lbl for lbl in candidates if lbl not in hops_cache]
    if missing:
        print(f"    building hops for {len(missing)} candidate(s) "
              f"({len(candidates) - len(missing)} reused from Step 3) ...", flush=True)
    for label, row in candidates.items():
        if label in hops_cache:
            hops, params = hops_cache[label]
        else:
            hops, params = bt.build_hops(row, progress_label=f"{owners[0]}/{label}")
        hops_by_label[label] = hops
        params_by_label[label] = params

    periods = {p["period"] for p in params_by_label.values()}
    if len(periods) > 1:
        raise ValueError(
            f"wf_group for '{owners[0]}' mixes period values {sorted(periods)} — a "
            f"walk-forward comparison needs one shared holding horizon."
        )
    period = int(next(iter(periods)))
    min_lots = int(settings.get("min_chain_lots", 3))

    realized_daynums = [h.daynum for hops in hops_by_label.values() for h in hops if h.realized]
    dn_min, dn_max = min(realized_daynums), max(realized_daynums)
    folds = build_folds(dn_min, dn_max, min_train, test_len, period)
    print(f"    {len(folds)} fold(s), history {dn_min}..{dn_max}", flush=True)

    fold_rows: list[dict] = []
    cand_rows: list[dict] = []
    pooled_sel: list[tuple[float, float]] = []
    pooled_all: list[tuple[float, float]] = []
    pooled_by_label: dict[str, list[tuple[float, float]]] = {lbl: [] for lbl in hops_by_label}

    for fi, (tr_lo, tr_hi, te_lo, te_hi) in enumerate(folds, start=1):
        scored: list[tuple[str, dict, dict]] = []
        for label, hops in hops_by_label.items():
            params = params_by_label[label]
            tr = bt.compute_metrics(hops, params, settings, tr_lo, tr_hi)
            te = bt.compute_metrics(hops, params, settings, te_lo, te_hi)
            scored.append((label, tr, te))
            cand_rows.append({
                "fold": fi, "label": label,
                "is_annual": tr["chain_annual"], "is_avg_gain": tr["avg_gain"],
                "is_alpha": tr["avg_alpha"],
                "oos_annual": te["chain_annual"], "oos_avg_gain": te["avg_gain"],
                "oos_median_gain": te["median_gain"], "oos_hit_rate%": te["hit_rate%"],
                "oos_alpha": te["avg_alpha"], "oos_n": te["chain_n"],
                "selected": False,
            })
            lots = _lots_for(hops, params, te_lo, te_hi)
            pooled_all.extend(lots)
            pooled_by_label[label].extend(lots)

        usable = [s for s in scored if pd.notna(s[1]["chain_annual"]) and s[1]["chain_n"] >= min_lots]
        if not usable:
            print(f"    fold {fi}/{len(folds)}: no usable candidate (skipped)", flush=True)
            continue
        label_sel, tr_sel, te_sel = max(usable, key=lambda s: s[1]["chain_annual"])
        for r in cand_rows[-len(scored):]:
            if r["label"] == label_sel:
                r["selected"] = True
        pooled_sel.extend(_lots_for(hops_by_label[label_sel], params_by_label[label_sel], te_lo, te_hi))
        print(f"    fold {fi}/{len(folds)}: train {tr_lo}..{tr_hi}  test {te_lo}..{te_hi}  "
              f"selected={label_sel}  oos_annual={te_sel['chain_annual']:.2f}  "
              f"oos_n={te_sel['chain_n']}", flush=True)

        oos_annuals = [s[2]["chain_annual"] for s in scored if pd.notna(s[2]["chain_annual"])]
        oos_avgs = [s[2]["avg_gain"] for s in scored if pd.notna(s[2]["avg_gain"])]
        oos_alphas = [s[2]["avg_alpha"] for s in scored if pd.notna(s[2]["avg_alpha"])]

        fold_rows.append({
            "fold": fi, "train_from": tr_lo, "train_to": tr_hi,
            "test_from": te_lo, "test_to": te_hi,
            "test_dates": f"{daynum_to_date(te_lo)} .. {daynum_to_date(te_hi)}",
            "selected": label_sel,
            "is_annual": tr_sel["chain_annual"], "is_n": tr_sel["chain_n"],
            "is_avg_gain": tr_sel["avg_gain"], "is_alpha": tr_sel["avg_alpha"],
            "oos_annual": te_sel["chain_annual"], "oos_n": te_sel["chain_n"],
            "oos_avg_gain": te_sel["avg_gain"], "oos_median_gain": te_sel["median_gain"],
            "oos_hit_rate%": te_sel["hit_rate%"], "oos_alpha": te_sel["avg_alpha"],
            "zeroskill_avg_gain": statistics.fmean(oos_avgs) if oos_avgs else float("nan"),
            "zeroskill_alpha": statistics.fmean(oos_alphas) if oos_alphas else float("nan"),
            "zeroskill_annual": statistics.fmean(oos_annuals) if oos_annuals else float("nan"),
            "oos_oracle": max(oos_avgs) if oos_avgs else float("nan"),
        })

    return GroupResult(owners=list(owners), candidate_labels=list(candidates), period=period,
                       folds=fold_rows, candidates=cand_rows,
                       pooled_selected=pooled_sel, pooled_all=pooled_all,
                       pooled_by_label=pooled_by_label, span=(dn_min, dn_max))


def summarize(result: GroupResult) -> dict:
    """The one Summary row for a candidate set's walk-forward test — mirrors strategy_grp
    v1's per-strategy Summary row (write_report's "Summary" sheet). This describes the
    SELECTED candidate per fold, i.e. how well selection travels out of sample; for one
    row's own OOS result see `summarize_candidates`."""
    g_sel, a_sel, n_sel = _pooled(result.pooled_selected)
    g_all, a_all, _n = _pooled(result.pooled_all)
    g_is = _mean_of(result.folds, "is_avg_gain")
    a_is = _mean_of(result.folds, "is_alpha")
    m_sel, h_sel = _shape([g for g, _m in result.pooled_selected])
    return {
        "owner": result.owner, "owners": ", ".join(result.owners),
        "candidates": len(result.candidate_labels),
        "folds": len(result.folds), "oos_lots": n_sel,
        "is_avg_gain": g_is, "oos_avg_gain": g_sel, "gain_gap": g_sel - g_is,
        "oos_median_gain": m_sel, "oos_hit_rate%": h_sel,
        "is_alpha": a_is, "oos_alpha": a_sel, "alpha_gap": a_sel - a_is,
        "zeroskill_avg_gain": g_all, "zeroskill_alpha": a_all,
        "selection_skill_gain": g_sel - g_all if pd.notna(g_all) else float("nan"),
        "selection_skill_alpha": a_sel - a_all if pd.notna(a_all) else float("nan"),
        "is_annual": _mean_of(result.folds, "is_annual"),
        "oos_annual": _mean_of(result.folds, "oos_annual"),
    }


def summarize_candidates(result: GroupResult) -> list[dict]:
    """One row per CANDIDATE — each strategy's own in-sample and out-of-sample numbers over
    the same folds, best pooled `oos_avg_gain` first.

    The Summary block above answers "does picking the training winner work?", which is one
    number for the whole set. This answers "how did THIS strategy do out of sample?", which
    is the per-strategy comparison. Gains/alpha/median/hit are pooled over every OOS lot the
    candidate produced across all folds (so a fold with more lots weighs more, matching how
    Summary pools the selected); the annual figures are means over folds, matching the fold
    table. `folds_selected` is how often this candidate won its training window.
    """
    by_label: dict[str, list[dict]] = {}
    for c in result.candidates:
        by_label.setdefault(c["label"], []).append(c)

    out: list[dict] = []
    for label, rows in by_label.items():
        lots = result.pooled_by_label.get(label, [])
        g_oos, a_oos, n_oos = _pooled(lots)
        m_oos, h_oos = _shape([g for g, _m in lots])
        g_is = _mean_of(rows, "is_avg_gain")
        a_is = _mean_of(rows, "is_alpha")
        out.append({
            "candidate": label,
            "folds_selected": sum(1 for r in rows if r["selected"]),
            "oos_lots": n_oos,
            "is_avg_gain": g_is, "oos_avg_gain": g_oos, "gain_gap": g_oos - g_is,
            "oos_median_gain": m_oos, "oos_hit_rate%": h_oos,
            "is_alpha": a_is, "oos_alpha": a_oos, "alpha_gap": a_oos - a_is,
            "is_annual": _mean_of(rows, "is_annual"),
            "oos_annual": _mean_of(rows, "oos_annual"),
        })
    out.sort(key=lambda d: d["oos_avg_gain"] if pd.notna(d["oos_avg_gain"]) else float("-inf"),
             reverse=True)
    return out


def _mean_of(folds: list[dict], key: str) -> float:
    vals = [f[key] for f in folds if pd.notna(f[key])]
    return statistics.fmean(vals) if vals else float("nan")
