"""
The output board — one workbook per development tick,
`report/compare_strategies_<date>.xlsx`. Separates results by process step, per
DesignVersion2.md's input/output separation principle:

    Runs               every active row, verbatim, beside its status
    Step1_groups       elevated groups + member tickers, current daynum
    Step2_picks        the gross list, current daynum (what production also ships)
    Step3_compare      transposed comparison: metric rows x one column per D-purpose row
    Step4_walkforward  per distinct candidate set: pooled summary, per-candidate
                       comparison, fold table
    Charts             cumulative chain / IS-vs-OOS / avg-vs-median gain, per row

Prior dated workbooks move to `_archive/` only once new output exists (matches
strategy_grp v1's rule for its own combined report).
"""

from __future__ import annotations

import shutil
import time
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import control_board as cb
import param_spec as spec
import step2_focusset
import step3_backtest as bt
import step3_report
import step4_walkforward as wf
from shared import expression as expr
from shared import market
from shared.config import REPORT_ROOT

_BOLD = Font(bold=True)
_HEAD = PatternFill("solid", fgColor="BDD7EE")
_ERR_FILL = PatternFill("solid", fgColor="FFC7CE")
_OK_FILL = PatternFill("solid", fgColor="C6EFCE")
_THIN_FILL = PatternFill("solid", fgColor="F8CBAD")
_NOTE = Font(italic=True, size=9, color="595959")


# ---------------------------------------------------------------------------
# Runs / Step1_groups / Step2_picks — current-daynum snapshot, every active row
# ---------------------------------------------------------------------------

def _current_picks(active_rows: list["cb.RunRow"]) -> dict[str, dict]:
    """label -> {daynum, tickers, elevated, params, s0, error} for every active row."""
    out: dict[str, dict] = {}
    n = len(active_rows)
    for i, row in enumerate(active_rows, start=1):
        label = row.resolved.get("label")
        print(f"[{i}/{n}] {label}: steps 0-2 ...", flush=True)
        try:
            daynum, tickers, elevated, params, s0 = step2_focusset.current_pick(row.resolved)
            out[label] = {"daynum": daynum, "tickers": tickers, "elevated": elevated,
                         "params": params, "s0": s0, "error": None}
            print(f"    universe={len(s0.universe)} tickers, {len(s0.group_sizes)} group(s), "
                  f"{len(tickers)} pick(s) at daynum {daynum}", flush=True)
        except (expr.ExpressionError, ValueError) as exc:
            out[label] = {"error": str(exc)}
            print(f"    FAILED: {exc}", flush=True)
    return out


def _write_runs_sheet(wb: Workbook, active_rows: list["cb.RunRow"],
                     picks: dict[str, dict], rejected_rows: list["cb.RunRow"],
                     board_errors: list[str]) -> None:
    """Every row the board marked active — INCLUDING the ones a tick could not run.

    A rejected row used to be filtered out in conductor.cmd_develop and never mentioned
    again, so the board said 4 active and the workbook showed 3 with nothing to say where
    the fourth went (SM, 2026-08-04). It now appears with status=REJECTED and the parse
    error that rejected it, and board-level errors (duplicate labels, bad Settings) get a
    banner above the table.
    """
    ws = wb.create_sheet("Runs")
    r = 1
    for msg in board_errors:
        cell = ws.cell(r, 1, f"BOARD ERROR: {msg}")
        cell.font, cell.fill = _BOLD, _ERR_FILL
        r += 1
    if board_errors:
        r += 1

    header_row = r
    headers = list(spec.RUNS_COLUMNS) + ["status", "universe_size", "n_groups", "daynum", "error"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(header_row, c, h)
        cell.font, cell.fill = _BOLD, _HEAD
    r += 1

    for row in list(active_rows) + list(rejected_rows):
        label = row.resolved.get("label")
        for c, name in enumerate(spec.RUNS_COLUMNS, start=1):
            ws.cell(r, c, spec.format_value(name, row.resolved.get(name)))
        info = picks.get(label, {})
        if not row.ok:
            status, err = "REJECTED", "; ".join(row.errors)
        elif info.get("error"):
            status, err = "FAILED", info["error"]
        else:
            status, err = "OK", None
        status_cell = ws.cell(r, len(spec.RUNS_COLUMNS) + 1, status)
        status_cell.fill = _OK_FILL if status == "OK" else _ERR_FILL
        if status == "OK":
            ws.cell(r, len(spec.RUNS_COLUMNS) + 2, len(info["s0"].universe))
            ws.cell(r, len(spec.RUNS_COLUMNS) + 3, len(info["s0"].group_sizes))
            ws.cell(r, len(spec.RUNS_COLUMNS) + 4, info["daynum"])
        else:
            ws.cell(r, len(spec.RUNS_COLUMNS) + 5, err)
        r += 1

    ws.freeze_panes = f"A{header_row + 1}"
    for c in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 16


def _write_step1_sheet(wb: Workbook, picks: dict[str, dict]) -> None:
    ws = wb.create_sheet("Step1_groups")
    headers = ["label", "daynum", "group", "n_members", "members"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(1, c, h); cell.font, cell.fill = _BOLD, _HEAD
    r = 2
    for label, info in picks.items():
        if info.get("error"):
            ws.cell(r, 1, label)
            ws.cell(r, 3, f"(step 0-2 failed: {info['error']})").font = _NOTE
            r += 1
            continue
        s0 = info["s0"]
        if not info["elevated"]:
            # An absent label used to be indistinguishable from a label that ran fine and
            # elevated nothing today — the second is a normal, informative outcome for a
            # strict level-B/C row, not a missing result.
            ws.cell(r, 1, label)
            ws.cell(r, 2, info["daynum"])
            ws.cell(r, 3, "(no group elevated at this daynum)").font = _NOTE
            ws.cell(r, 4, 0)
            r += 1
            continue
        for group in info["elevated"]:
            members = s0.groups.index[s0.groups == group].tolist()
            ws.cell(r, 1, label)
            ws.cell(r, 2, info["daynum"])
            ws.cell(r, 3, group)
            ws.cell(r, 4, len(members))
            ws.cell(r, 5, ", ".join(members[:30]) + (" ..." if len(members) > 30 else ""))
            r += 1
    ws.freeze_panes = "A2"
    for c, w in zip("ABCDE", (24, 10, 16, 10, 90)):
        ws.column_dimensions[c].width = w


def _write_step2_sheet(wb: Workbook, picks: dict[str, dict]) -> None:
    ws = wb.create_sheet("Step2_picks")
    headers = ["label", "daynum", "rank", "ticker", "priority_attribute", "value"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(1, c, h); cell.font, cell.fill = _BOLD, _HEAD
    r = 2
    for label, info in picks.items():
        if info.get("error"):
            ws.cell(r, 1, label)
            ws.cell(r, 4, f"(step 0-2 failed: {info['error']})").font = _NOTE
            r += 1
            continue
        if not info["tickers"]:
            ws.cell(r, 1, label)
            ws.cell(r, 2, info["daynum"])
            ws.cell(r, 4, "(no pick — cash hop)").font = _NOTE
            r += 1
            continue
        params = info["params"]
        try:
            from shared.data_loader import load_longi
            prio_df = load_longi(f"longi_{params['priority_attribute']}.csv")
        except Exception:                                              # noqa: BLE001
            prio_df = None
        col = str(info["daynum"])
        for i, ticker in enumerate(info["tickers"], start=1):
            val = None
            if prio_df is not None and ticker in prio_df.index and col in prio_df.columns:
                val = prio_df.at[ticker, col]
            ws.cell(r, 1, label)
            ws.cell(r, 2, info["daynum"])
            ws.cell(r, 3, i)
            ws.cell(r, 4, ticker)
            ws.cell(r, 5, params["priority_attribute"])
            ws.cell(r, 6, val)
            r += 1
    ws.freeze_panes = "A2"
    for c, w in zip("ABCDEF", (24, 10, 6, 12, 18, 12)):
        ws.column_dimensions[c].width = w


# ---------------------------------------------------------------------------
# Step3_compare — transposed comparison, one column per D-purpose row
# ---------------------------------------------------------------------------

# The parameter block leads with the three settings that decide WHICH END of a ranking a
# row picks from — dominance_direction, priority_direction and from_rank are independent
# and a mismatch between them silently inverts the strategy (SM, 2026-08-04: "small_wins,
# but from_rank -1"), so they belong side by side where a comparison can catch it.
_STEP3_ROWS: list[str] = [
    "group_expression", "level", "period",
    "dominance_attribute", "dominance_direction",
    "priority_attribute", "priority_direction",
    "from_rank", "focusset_size", "tickers_per_group", "post_filter",
    "StartDaynum", "EndDaynum", "N_hops", "N_hops_active",
    "avg_gain", "median_gain", "hit_rate%", "avg_alpha", "avg_beta",
    "chain_ret", "chain_annual", "chain_n", "origin_sens%", "N_loss", "Worst",
    "avg_partial_gain", "avg_partial_alpha", "n_open_hops",
]


def _write_step3_sheet(wb: Workbook, backtests: dict[str, "bt.BacktestResult"]) -> None:
    ws = wb.create_sheet("Step3_compare")
    ws.cell(1, 1, "metric").font = _BOLD
    order = sorted(backtests, key=lambda lbl: (
        -(backtests[lbl].metrics["chain_annual"]
          if pd.notna(backtests[lbl].metrics["chain_annual"]) else float("-inf"))
    ))
    for c, label in enumerate(order, start=2):
        cell = ws.cell(1, c, label); cell.font, cell.fill = _BOLD, _HEAD
        if backtests[label].metrics.get("thin"):
            cell.fill = _THIN_FILL
    for r, key in enumerate(_STEP3_ROWS, start=2):
        ws.cell(r, 1, key).font = _BOLD
        for c, label in enumerate(order, start=2):
            result = backtests[label]
            if key in result.params:
                val = spec.format_value(key, result.params[key])
            else:
                val = result.metrics.get(key)
            if isinstance(val, float) and pd.notna(val):
                val = round(val, 4)
            elif isinstance(val, tuple):
                val = str(val)
            ws.cell(r, c, val)
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 22
    for c in range(2, len(order) + 2):
        ws.column_dimensions[get_column_letter(c)].width = 16


# ---------------------------------------------------------------------------
# Step4_walkforward — one summary block + fold table per D-purpose row
# ---------------------------------------------------------------------------

_FOLD_COLS: list[str] = [
    "fold", "test_dates", "selected", "is_n", "oos_n", "is_annual", "oos_annual",
    "oos_avg_gain", "oos_median_gain", "oos_hit_rate%", "zeroskill_avg_gain",
    "oos_oracle", "oos_alpha",
]
_SUMMARY_COLS: list[str] = [
    "candidates", "folds", "oos_lots", "is_avg_gain", "oos_avg_gain", "gain_gap",
    "oos_median_gain", "oos_hit_rate%", "is_alpha", "oos_alpha", "alpha_gap",
    "zeroskill_avg_gain", "selection_skill_gain", "is_annual", "oos_annual",
]
_CANDIDATE_COLS: list[str] = [
    "candidate", "folds_selected", "oos_lots", "is_avg_gain", "oos_avg_gain", "gain_gap",
    "oos_median_gain", "oos_hit_rate%", "is_alpha", "oos_alpha", "alpha_gap",
    "is_annual", "oos_annual",
]


def _write_step4_sheet(wb: Workbook, walk_results: list["wf.GroupResult"]) -> None:
    """One block per distinct candidate set: a Summary row (the SELECTED candidate, i.e.
    does selection travel out of sample), a per-candidate table (each strategy's own OOS
    numbers — the per-strategy comparison), then the fold table."""
    ws = wb.create_sheet("Step4_walkforward")
    r = 1
    for result in walk_results:
        summary = wf.summarize(result)
        cell = ws.cell(r, 1, f"{' + '.join(result.owners)}  "
                             f"(vs {len(result.candidate_labels)} candidate(s), "
                             f"period={result.period}d)")
        cell.font = Font(bold=True, size=12)
        r += 1
        ws.cell(r, 1, "Summary — the candidate SELECTED each fold, not any one row's own "
                      "result; see the per-candidate table below").font = _NOTE
        r += 1
        for c, key in enumerate(_SUMMARY_COLS, start=1):
            ws.cell(r, c, key).font = _BOLD
        r += 1
        for c, key in enumerate(_SUMMARY_COLS, start=1):
            val = summary.get(key)
            ws.cell(r, c, round(val, 4) if isinstance(val, float) and pd.notna(val) else val)
        r += 2

        ws.cell(r, 1, "Per candidate — each strategy's own numbers over the same folds, "
                      "best oos_avg_gain first").font = _NOTE
        r += 1
        for c, h in enumerate(_CANDIDATE_COLS, start=1):
            cell = ws.cell(r, c, h); cell.font, cell.fill = _BOLD, _HEAD
        r += 1
        for cand in wf.summarize_candidates(result):
            for c, key in enumerate(_CANDIDATE_COLS, start=1):
                val = cand.get(key)
                ws.cell(r, c, round(val, 4) if isinstance(val, float) and pd.notna(val) else val)
            r += 1
        r += 2

        for c, h in enumerate(_FOLD_COLS, start=1):
            cell = ws.cell(r, c, h); cell.font, cell.fill = _BOLD, _HEAD
        r += 1
        for f in result.folds:
            for c, key in enumerate(_FOLD_COLS, start=1):
                val = f.get(key)
                ws.cell(r, c, round(val, 4) if isinstance(val, float) and pd.notna(val) else val)
            r += 1
        r += 2
    for c in range(1, max(len(_FOLD_COLS), len(_CANDIDATE_COLS), len(_SUMMARY_COLS)) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 15
    ws.column_dimensions["A"].width = 24


# ---------------------------------------------------------------------------
# Charts — cumulative chain / IS-vs-OOS / avg-vs-median, per D-purpose row
# ---------------------------------------------------------------------------

def _greedy_chain_lots(hops: list["bt.Hop"], period: int, threshold) -> list[tuple[int, float]]:
    """Single-origin non-overlapping chain lots (daynum, gain), ascending — a plain equity
    curve for the chart. (Step3_compare's chain_annual is phase-averaged for stability;
    this single origin is only for a visual cumulative-gain shape.)"""
    usable = sorted(
        ((h.daynum, g) for h in hops if h.realized and bt.gate_ok(h, threshold)
         for g in [market.hop_avg(h.gains)] if pd.notna(g)),
        key=lambda t: t[0],
    )
    lots: list[tuple[int, float]] = []
    next_allowed: int | None = None
    for dn, g in usable:
        if next_allowed is None or dn >= next_allowed:
            lots.append((dn, g))
            next_allowed = dn + period
    return lots


def _write_charts_sheet(wb: Workbook, backtests: dict[str, "bt.BacktestResult"],
                       walk_results: list["wf.GroupResult"]) -> None:
    ws = wb.create_sheet("Charts")
    labels = list(backtests)

    # --- Table 1: cumulative chain, by lot index (not calendar daynum -- see docstring) ---
    cum_by_label: dict[str, list[float]] = {}
    for label, result in backtests.items():
        threshold = result.params.get("no_go_gspc_rsi")
        period = int(result.params["period"])
        lots = _greedy_chain_lots(result.hops, period, threshold)
        running = 0.0
        cum: list[float] = []
        for _dn, g in lots:
            running += g
            cum.append(running)
        cum_by_label[label] = cum

    max_lots = max((len(v) for v in cum_by_label.values()), default=0)
    row0 = 1
    ws.cell(row0, 1, "Cumulative chain (by lot index)").font = Font(bold=True, size=12)
    ws.cell(row0 + 1, 1, "lot #")
    for c, label in enumerate(labels, start=2):
        ws.cell(row0 + 1, c, label).font = _BOLD
    for i in range(max_lots):
        r = row0 + 2 + i
        ws.cell(r, 1, i + 1)
        for c, label in enumerate(labels, start=2):
            vals = cum_by_label[label]
            if i < len(vals):
                ws.cell(r, c, round(vals[i], 4))
    if max_lots:
        chart1 = LineChart()
        chart1.title = "Cumulative chain gain (%) by lot index"
        chart1.y_axis.title, chart1.x_axis.title = "cumulative %", "lot #"
        data = Reference(ws, min_col=2, max_col=1 + len(labels),
                         min_row=row0 + 1, max_row=row0 + 1 + max_lots)
        cats = Reference(ws, min_col=1, min_row=row0 + 2, max_row=row0 + 1 + max_lots)
        chart1.add_data(data, titles_from_data=True)
        chart1.set_categories(cats)
        ws.add_chart(chart1, f"A{row0 + max_lots + 4}")

    # --- Table 2: IS vs OOS avg_gain per CANDIDATE (each strategy's own walk-forward
    # numbers). Charting the per-set Summary instead would draw one identical bar pair per
    # owner whenever rows share a candidate set — see _write_step4_sheet. ---
    row1 = row0 + max_lots + 24
    ws.cell(row1, 1, "IS vs OOS avg_gain, per strategy").font = Font(bold=True, size=12)
    ws.cell(row1 + 1, 1, "label"); ws.cell(row1 + 1, 2, "is_avg_gain"); ws.cell(row1 + 1, 3, "oos_avg_gain")
    for c in (1, 2, 3):
        ws.cell(row1 + 1, c).font = _BOLD
    per_candidate: dict[str, dict] = {}
    for result in walk_results:
        for cand in wf.summarize_candidates(result):
            per_candidate.setdefault(cand["candidate"], cand)
    wf_labels = list(per_candidate)
    for i, label in enumerate(wf_labels):
        cand = per_candidate[label]
        r = row1 + 2 + i
        ws.cell(r, 1, label)
        ws.cell(r, 2, round(cand["is_avg_gain"], 4) if pd.notna(cand["is_avg_gain"]) else None)
        ws.cell(r, 3, round(cand["oos_avg_gain"], 4) if pd.notna(cand["oos_avg_gain"]) else None)
    if wf_labels:
        chart2 = BarChart()
        chart2.type, chart2.title = "col", "In-sample vs out-of-sample avg_gain (%)"
        data = Reference(ws, min_col=2, max_col=3, min_row=row1 + 1, max_row=row1 + 1 + len(wf_labels))
        cats = Reference(ws, min_col=1, min_row=row1 + 2, max_row=row1 + 1 + len(wf_labels))
        chart2.add_data(data, titles_from_data=True)
        chart2.set_categories(cats)
        ws.add_chart(chart2, f"E{row1}")

    # --- Table 3: avg_gain vs median_gain per row -- the shape behind the mean ---
    row2 = row1 + max(len(wf_labels), 6) + 20
    ws.cell(row2, 1, "avg_gain vs median_gain, per row").font = Font(bold=True, size=12)
    ws.cell(row2 + 1, 1, "label"); ws.cell(row2 + 1, 2, "avg_gain"); ws.cell(row2 + 1, 3, "median_gain")
    for c in (1, 2, 3):
        ws.cell(row2 + 1, c).font = _BOLD
    for i, label in enumerate(labels):
        m = backtests[label].metrics
        r = row2 + 2 + i
        ws.cell(r, 1, label)
        ws.cell(r, 2, round(m["avg_gain"], 4) if pd.notna(m["avg_gain"]) else None)
        ws.cell(r, 3, round(m["median_gain"], 4) if pd.notna(m["median_gain"]) else None)
    if labels:
        chart3 = BarChart()
        chart3.type, chart3.title = "col", "avg_gain vs median_gain (%) -- the shape behind the mean"
        data = Reference(ws, min_col=2, max_col=3, min_row=row2 + 1, max_row=row2 + 1 + len(labels))
        cats = Reference(ws, min_col=1, min_row=row2 + 2, max_row=row2 + 1 + len(labels))
        chart3.add_data(data, titles_from_data=True)
        chart3.set_categories(cats)
        ws.add_chart(chart3, f"E{row2}")

    ws.column_dimensions["A"].width = 24


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _archive_prior() -> None:
    for path in REPORT_ROOT.glob("compare_strategies_*.xlsx"):
        dest = REPORT_ROOT / "_archive" / time.strftime("%Y%m%d_%H%M%S")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest / path.name))


def assemble(board: "cb.BoardResult", settings: dict) -> Path:
    """Build the combined development-tick workbook. Every active row (P and D) gets a
    Runs/Step1_groups/Step2_picks entry; only active D-purpose rows get Step3/Step4."""
    active_rows = [r for r in board.runs if r.active and r.ok]
    rejected_rows = [r for r in board.runs if r.active and not r.ok]
    if rejected_rows or board.board_errors:
        print(f"\n!!! {len(rejected_rows)} active row(s) REJECTED by board validation — "
              f"they are on the Runs sheet with their error, but produce no results:", flush=True)
        for row in rejected_rows:
            print(f"    row {row.row_num} '{row.resolved.get('label')}': "
                  f"{'; '.join(row.errors)}", flush=True)
        for msg in board.board_errors:
            print(f"    BOARD: {msg}", flush=True)
    print(f"\n=== Steps 0-2: {len(active_rows)} active row(s) ===", flush=True)
    picks = _current_picks(active_rows)

    d_rows = {r.resolved["label"]: r.resolved for r in active_rows
             if r.resolved.get("purpose") == "D"}

    print(f"\n=== Step 3: backtest ({len(d_rows)} row(s)) ===", flush=True)
    backtests: dict[str, "bt.BacktestResult"] = {}
    for i, (label, row_resolved) in enumerate(d_rows.items(), start=1):
        print(f"[{i}/{len(d_rows)}] {label}: building hops ...", flush=True)
        backtests[label] = bt.run_backtest(row_resolved, settings, progress_label=label)
        m = backtests[label].metrics
        print(f"    chain_annual={m['chain_annual']:.2f}  chain_n={m['chain_n']}  "
              f"N_hops={m['N_hops']}", flush=True)

    if backtests:
        run_paths = step3_report.write_run_reports(backtests)
        for p in run_paths:
            print(f"    wrote {p}", flush=True)

    # A walk-forward test belongs to its CANDIDATE SET, not to the row that declared it:
    # two rows naming the same candidates run the identical experiment and would otherwise
    # print the identical fold table twice under two headings. Group by the resolved set,
    # run each distinct one once, and list every owner on the block.
    print(f"\n=== Step 4: walk-forward ({len(d_rows)} row(s)) ===", flush=True)
    by_candidate_set: dict[frozenset[str], list[str]] = {}
    candidates_for: dict[frozenset[str], dict[str, dict]] = {}
    for label, row_resolved in d_rows.items():
        candidates = wf.resolve_candidates(label, row_resolved, d_rows)
        key = frozenset(candidates)
        by_candidate_set.setdefault(key, []).append(label)
        candidates_for[key] = candidates
    if len(by_candidate_set) < len(d_rows):
        print(f"    {len(d_rows)} row(s) -> {len(by_candidate_set)} distinct candidate set(s); "
              f"rows sharing a set share one test", flush=True)

    hops_cache = {label: (r.hops, r.params) for label, r in backtests.items()}
    walk_results: list["wf.GroupResult"] = []
    for i, (key, owners) in enumerate(by_candidate_set.items(), start=1):
        candidates = candidates_for[key]
        print(f"[{i}/{len(by_candidate_set)}] {', '.join(owners)}: walk-forward vs "
              f"{len(candidates)} candidate(s) ...", flush=True)
        try:
            walk_results.append(wf.walk_group(
                owners, candidates, settings,
                min_train=int(settings.get("wf_min_train", wf.DEFAULT_MIN_TRAIN)),
                test_len=int(settings.get("wf_test_len", wf.DEFAULT_TEST_LEN)),
                hops_cache=hops_cache))
        except ValueError as exc:
            print(f"[outputboard] walk-forward skipped for '{owners[0]}': {exc}")

    print("\n=== Writing workbook ===", flush=True)
    wb = Workbook()
    wb.remove(wb.active)
    _write_runs_sheet(wb, active_rows, picks, rejected_rows, board.board_errors)
    _write_step1_sheet(wb, picks)
    _write_step2_sheet(wb, picks)
    if backtests:
        _write_step3_sheet(wb, backtests)
    if walk_results:
        _write_step4_sheet(wb, walk_results)
    if backtests:
        _write_charts_sheet(wb, backtests, walk_results)

    _archive_prior()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"compare_strategies_{date.today():%Y%m%d}.xlsx"
    wb.save(path)
    return path
