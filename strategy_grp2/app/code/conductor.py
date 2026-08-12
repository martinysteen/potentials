"""
The pipeline driver — longi.py's role for this project. Reads the control board, and for
every active row runs steps 0-4, then hands the results to outputboard.py. See
DesignVersion2.md for the full step write-up.

    python conductor.py --make-board   # write/refresh the board from param_spec.py
    python conductor.py --dry-run      # parse + validate every row; touches no data
    python conductor.py --check        # step 0 only: universe/group counts, data guard
    python conductor.py                # development tick: steps 0-4 for active rows ->
                                        #   compare_strategies_<date>.xlsx AND StrategicStocks.xlsx
    python conductor.py --production   # fast path: steps 0-2 only -> StrategicStocks.xlsx
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import control_board
import outputboard
import preflight
import step0_data
from shared import expression as expr


def _report_board_freshness() -> None:
    """Print when the board on disk was last saved. Cheap, and it is the one line that
    makes 'I forgot to save' visible after the fact as well as before."""
    state = control_board.board_file_state()
    open_note = " — STILL OPEN IN EXCEL" if state.is_open else ""
    print(f"control_board.xlsx last saved: {state.saved_ago}{open_note}\n")


def cmd_make_board() -> int:
    path = control_board.write_board()
    print(f"Wrote {path}")
    return 0


def cmd_dry_run() -> int:
    result = control_board.read_board()

    if result.board_errors:
        print("Board-level errors:")
        for msg in result.board_errors:
            print(f"  ! {msg}")

    for row in result.runs:
        tag = "active" if row.active else "  idle"
        label = row.resolved.get("label", "?")
        if row.ok:
            print(f"[{tag}] row {row.row_num:>3}  {label:<28} OK  "
                  f"level={row.resolved.get('level')} "
                  f"group={row.resolved.get('group_expression')!r}")
        else:
            print(f"[{tag}] row {row.row_num:>3}  {label:<28} FAILED")
            for msg in row.errors:
                print(f"           ! {msg}")

    n_active = len(result.active_runs)
    n_active_bad = sum(1 for r in result.active_runs if not r.ok)
    print(f"\n{len(result.runs)} row(s) total, {n_active} active, "
          f"{n_active_bad} active row(s) with errors.")

    if not result.ok:
        print("\n--dry-run: at least one active row has errors, or the board itself does "
              "(see above). Fix the board and re-run.")
        return 1
    print("\n--dry-run: every active row parses cleanly. Nothing else was resolved "
          "(no data read, no files written).")
    return 0


# ---------------------------------------------------------------------------
# Step 0 diagnostics — `--check`
# ---------------------------------------------------------------------------

def cmd_check() -> int:
    board = control_board.read_board()
    active = [r for r in board.runs if r.active and r.ok]
    if not active:
        print("No active, cleanly-parsing rows to check.")
        return 0

    preflight.ensure_data(board.runs, settings=board.settings)

    bad = 0
    for row in active:
        label = row.resolved.get("label")
        try:
            s0 = step0_data.resolve_step0(row.resolved)
        except expr.ExpressionError as exc:
            print(f"[{label}] STEP0 FAILED: {exc}")
            bad += 1
            continue
        n_groups = len(s0.group_sizes)
        print(f"[{label}] universe={len(s0.universe)} tickers, {n_groups} group(s), "
              f"dominance_attribute={s0.dominance_attribute!r}, "
              f"priority_attribute={s0.priority_attribute!r}")
        if n_groups <= 12:
            sizes = ", ".join(f"{k}={v}" for k, v in sorted(s0.group_sizes.items()))
            print(f"           group sizes: {sizes}")

    print(f"\n{len(active)} row(s) checked, {bad} failed.")
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# Production tick — `--production`, the fast path: steps 0-2 only -> StrategicStocks.xlsx
# ---------------------------------------------------------------------------

def cmd_production() -> int:
    """No `purpose` column gating anymore (2026-08-12) — every active row ships. This is
    the FAST path: steps 0-2 only, skipping Step 3/4's backtest cost, for when you just
    want today's gross list quickly. The bare development tick (cmd_develop) does the same
    steps 0-2 work AND the full backtest AND writes this same file — use --production when
    you don't want to wait for that."""
    board = control_board.read_board()
    active = [r for r in board.runs if r.active and r.ok]
    if not active:
        print("No active rows.")
        return 0

    preflight.ensure_data(board.runs, settings=board.settings)

    picks = outputboard.current_picks(active)
    bad = sum(1 for info in picks.values() if info.get("error"))

    if bad == len(picks):
        print("\nNo row produced a result — StrategicStocks.xlsx not written.")
        return 1

    outputboard.archive_prior_strategic_stocks()
    xlsx_path, csv_path = outputboard.write_strategic_stocks(picks)
    print(f"\nWrote {xlsx_path}")
    print(f"Wrote {csv_path}  ({len(picks)} row(s), {bad} failed)")
    return 1 if bad else 0


def cmd_develop() -> int:
    board = control_board.read_board()
    active = [r for r in board.runs if r.active and r.ok]
    if not active:
        rejected = [r for r in board.runs if r.active and not r.ok]
        print(f"No active, cleanly-parsing rows ({len(rejected)} active row(s) rejected).")
        for row in rejected:
            print(f"  ! row {row.row_num} '{row.resolved.get('label')}': "
                  f"{'; '.join(row.errors)}")
        for msg in board.board_errors:
            print(f"  ! BOARD: {msg}")
        return 1 if rejected or board.board_errors else 0

    preflight.ensure_data(board.runs, settings=board.settings)
    compare_path, strategic_xlsx, strategic_csv = outputboard.assemble(board, board.settings)
    print(f"Wrote {compare_path}")
    print(f"Wrote {strategic_xlsx}")
    print(f"Wrote {strategic_csv}")
    return 0


def main() -> int:
    args = set(sys.argv[1:])

    commands = {
        "--make-board": (cmd_make_board, "--make-board (it would overwrite your open copy)"),
        "--dry-run": (cmd_dry_run, "--dry-run"),
        "--check": (cmd_check, "--check"),
        "--production": (cmd_production, "the production tick"),
    }
    fn, action = cmd_develop, "the development tick"
    for flag, (candidate_fn, candidate_action) in commands.items():
        if flag in args:
            fn, action = candidate_fn, candidate_action
            break

    # Every entry point reads the board, so every entry point checks it was saved first.
    try:
        control_board.require_saved_board(action, allow_open="--board-open-ok" in args)
    except control_board.BoardOpenError as exc:
        print(f"\n*** {exc}\n")
        return 2
    _report_board_freshness()
    return fn()


if __name__ == "__main__":
    sys.exit(main())
