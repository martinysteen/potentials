"""
The control board — read, validate, and (re)generate `app/control/control_board.xlsx`.

The processor never writes to this file while a tick is running (a file open in Excel
can't be written anyway, and input/output separation is the point — see
DesignVersion2.md). `--make-board` is the one path that touches it, and only to add
columns/legend rows the schema has grown since the file was last written; existing rows'
values are preserved.

Three sheets:
    Runs     one row per run; `active` is the tick (see param_spec.PARAMS for columns)
    Settings global knobs, not per-run (see param_spec.SETTINGS)
    Legend   generated from param_spec — never hand-edited
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

sys.path.insert(0, str(Path(__file__).resolve().parent))

import param_spec as spec
from shared.config import CONTROL_BOARD_PATH, CONTROL_ROOT

_HEADER_FILL = PatternFill("solid", fgColor="BDD7EE")
_META_FILL = PatternFill("solid", fgColor="D6DCE4")
_STEP_FILLS = {
    0: PatternFill("solid", fgColor="FFE599"),
    1: PatternFill("solid", fgColor="C6EFCE"),
    2: PatternFill("solid", fgColor="FFF2CC"),
    3: PatternFill("solid", fgColor="F8CBAD"),
    4: PatternFill("solid", fgColor="D9D2E9"),
}
_ERROR_FILL = PatternFill("solid", fgColor="FFC7CE")


# ---------------------------------------------------------------------------
# Value coercion — one function per column, driven by param_spec.ParamDef
# ---------------------------------------------------------------------------

_TRUTHY = {"x", "X", "yes", "y", "true", "1"}


def _coerce_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip() in _TRUTHY


def _is_blank(raw) -> bool:
    return raw is None or (isinstance(raw, str) and raw.strip() == "")


def coerce(pdef: "spec.ParamDef", raw, row_num: int):
    """Blank cell -> schema default (error if required). Otherwise dtype/parser-driven
    coercion, raising ValueError with the row number so a bad cell is easy to find."""
    blank = _is_blank(raw)
    if blank:
        if pdef.required:
            raise ValueError(f"row {row_num}: '{pdef.name}' is required and blank — {pdef.help}")
        return pdef.default

    try:
        if pdef.parser is not None:
            value = pdef.parser(raw)
        elif pdef.dtype == "bool":
            value = _coerce_bool(raw)
        elif pdef.dtype == "int":
            value = int(float(raw))
        elif pdef.dtype == "float":
            value = float(raw)
        elif pdef.dtype in ("str", "expr"):
            value = str(raw).strip()
        elif pdef.dtype == "choice":
            s = str(raw).strip()
            match = next((c for c in (pdef.choices or ()) if c.lower() == s.lower()), None)
            if match is None:
                raise ValueError(f"'{raw}' is not one of {list(pdef.choices or ())}")
            value = match
        elif pdef.dtype == "list_str":
            value = tuple(x.strip() for x in str(raw).split(",") if x.strip())
        else:
            raise ValueError(f"unhandled dtype '{pdef.dtype}'")
    except ValueError as exc:
        raise ValueError(f"row {row_num}: '{pdef.name}'={raw!r} invalid — {exc}") from None

    if pdef.dtype == "int" and pdef.choices and str(value) not in pdef.choices:
        raise ValueError(
            f"row {row_num}: '{pdef.name}'={value} invalid — must be one of {list(pdef.choices)}"
        )
    return value


# ---------------------------------------------------------------------------
# Runs sheet: read + resolve
# ---------------------------------------------------------------------------


@dataclass
class RunRow:
    row_num: int                       # 1-based Excel row (for error messages)
    raw: dict[str, object]             # exactly what the cells held
    resolved: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def active(self) -> bool:
        return bool(self.resolved.get("active", False))


_GROUP_TOKEN_RE = re.compile(r"Stamdata\.(\w+)")


def _derive_label(resolved: dict) -> str:
    """A short, readable default when the row's `label` cell is blank. This is a display
    heuristic only — the real parse of group_expression lives in step0_data.py's
    expression engine (phase 2); here it just extracts column names for a readable name.

    Includes from_rank whenever it differs from the default best-n (1): two rows that
    differ ONLY in from_rank — e.g. the 1 / "mid" / -1 comparison the design calls for
    (see DesignVersion2.md) — must not collide on label, since the board-level duplicate
    check would otherwise reject exactly the rows meant to sit side by side."""
    expr = str(resolved.get("group_expression", "")).strip()
    if expr == "#ALL" or not expr:
        group_token = "ALL"
    else:
        tokens = _GROUP_TOKEN_RE.findall(expr)
        group_token = "_".join(dict.fromkeys(tokens)) if tokens else "expr"
    level = resolved.get("level", "A")
    prio = resolved.get("priority_attribute", "")
    label = f"{level}_{group_token}_{prio}"
    parsed = resolved.get("from_rank")
    if parsed and parsed != ("edge", 1):
        import param_spec as spec
        label += f"_{spec.format_from_rank(parsed)}"
    return label


def resolve_row(raw: dict[str, object], row_num: int) -> RunRow:
    row = RunRow(row_num=row_num, raw=dict(raw))
    for pdef in spec.PARAMS:
        try:
            row.resolved[pdef.name] = coerce(pdef, raw.get(pdef.name), row_num)
        except ValueError as exc:
            row.errors.append(str(exc))
    if not row.resolved.get("label"):
        try:
            row.resolved["label"] = _derive_label(row.resolved)
        except Exception:                            # noqa: BLE001 — never let a label crash a row
            row.resolved["label"] = f"row{row_num}"
    return row


# ---------------------------------------------------------------------------
# Board-level read/validate
# ---------------------------------------------------------------------------


@dataclass
class BoardResult:
    runs: list[RunRow]
    settings: dict[str, object]
    board_errors: list[str]            # errors not tied to one row (e.g. duplicate labels)

    @property
    def active_runs(self) -> list[RunRow]:
        return [r for r in self.runs if r.active]

    @property
    def ok(self) -> bool:
        return not self.board_errors and all(r.ok for r in self.active_runs)


def _read_runs_sheet(ws: Worksheet) -> list[dict[str, object]]:
    headers = [c.value for c in ws[1]]
    rows: list[dict[str, object]] = []
    for excel_row in ws.iter_rows(min_row=2):
        values = [c.value for c in excel_row]
        if all(v is None or str(v).strip() == "" for v in values):
            continue
        rows.append({h: v for h, v in zip(headers, values) if h})
    return rows


def _read_settings_sheet(ws: Worksheet) -> dict[str, object]:
    out: dict[str, object] = {}
    for excel_row in ws.iter_rows(min_row=2):
        name = excel_row[0].value
        if not name:
            continue
        out[str(name).strip()] = excel_row[1].value if len(excel_row) > 1 else None
    return out


def _resolve_settings(raw: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    resolved: dict[str, object] = {}
    errors: list[str] = []
    for sdef in spec.SETTINGS:
        cell = raw.get(sdef.name)
        if cell is None or (isinstance(cell, str) and cell.strip() == ""):
            resolved[sdef.name] = sdef.default
            continue
        try:
            if sdef.dtype == "bool":
                resolved[sdef.name] = _coerce_bool(cell)
            elif sdef.dtype == "int":
                resolved[sdef.name] = int(float(cell))
            elif sdef.dtype == "float":
                resolved[sdef.name] = float(cell)
            else:
                resolved[sdef.name] = str(cell).strip()
        except ValueError as exc:
            errors.append(f"Settings '{sdef.name}'={cell!r} invalid — {exc}")
            resolved[sdef.name] = sdef.default
    return resolved, errors


def read_board(path: Path = CONTROL_BOARD_PATH) -> BoardResult:
    if not path.exists():
        raise FileNotFoundError(
            f"No control board at {path}. Run `python conductor.py --make-board` first."
        )
    wb = load_workbook(path, data_only=True)
    board_errors: list[str] = []

    if "Runs" not in wb.sheetnames:
        raise ValueError(f"{path}: no 'Runs' sheet found")
    raw_rows = _read_runs_sheet(wb["Runs"])
    runs = [resolve_row(raw, row_num=i + 2) for i, raw in enumerate(raw_rows)]

    settings: dict[str, object] = {}
    if "Settings" in wb.sheetnames:
        raw_settings = _read_settings_sheet(wb["Settings"])
        settings, setting_errors = _resolve_settings(raw_settings)
        board_errors.extend(setting_errors)
    else:
        settings = {s.name: s.default for s in spec.SETTINGS}

    labels = [r.resolved.get("label") for r in runs if r.active]
    dupes = {lbl for lbl in labels if labels.count(lbl) > 1}
    if dupes:
        board_errors.append(
            f"duplicate active labels (each run's label must be unique): {sorted(dupes)}"
        )

    return BoardResult(runs=runs, settings=settings, board_errors=board_errors)


# ---------------------------------------------------------------------------
# Board generation — `--make-board`
# ---------------------------------------------------------------------------


def _existing_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    wb = load_workbook(path, data_only=True)
    if "Runs" not in wb.sheetnames:
        return []
    return _read_runs_sheet(wb["Runs"])


def _existing_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    wb = load_workbook(path, data_only=True)
    if "Settings" not in wb.sheetnames:
        return {}
    return _read_settings_sheet(wb["Settings"])


def _write_runs_sheet(wb: Workbook, preserved_rows: list[dict[str, object]]) -> None:
    ws = wb.create_sheet("Runs")
    for col, name in enumerate(spec.RUNS_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=name)
        pdef = spec.PARAMS_BY_NAME[name]
        cell.fill = _META_FILL if pdef.step is None else _STEP_FILLS.get(pdef.step, _HEADER_FILL)
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    dropped: set[str] = set()
    for r, old_row in enumerate(preserved_rows, start=2):
        for c, name in enumerate(spec.RUNS_COLUMNS, start=1):
            if name in old_row:
                ws.cell(row=r, column=c, value=old_row[name])
        dropped |= (set(old_row) - set(spec.RUNS_COLUMNS)) - {None}
    if dropped:
        print(f"[control_board] columns no longer in the schema, dropped: {sorted(dropped)}")

    for col in range(1, len(spec.RUNS_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 18


def _write_settings_sheet(wb: Workbook, preserved: dict[str, object]) -> None:
    ws = wb.create_sheet("Settings")
    ws.cell(row=1, column=1, value="setting").font = Font(bold=True)
    ws.cell(row=1, column=2, value="value").font = Font(bold=True)
    ws.cell(row=1, column=3, value="help").font = Font(bold=True)
    for c in range(1, 4):
        ws.cell(row=1, column=c).fill = _HEADER_FILL
    for r, sdef in enumerate(spec.SETTINGS, start=2):
        ws.cell(row=r, column=1, value=sdef.name)
        ws.cell(row=r, column=2, value=preserved.get(sdef.name, sdef.default))
        ws.cell(row=r, column=3, value=sdef.help).alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 90


def _write_legend_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Legend")
    headers = ["column", "step", "type", "default", "choices", "help"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
    for r, pdef in enumerate(spec.PARAMS, start=2):
        ws.cell(row=r, column=1, value=pdef.name)
        ws.cell(row=r, column=2, value="meta" if pdef.step is None else pdef.step)
        ws.cell(row=r, column=3, value=pdef.dtype)
        ws.cell(row=r, column=4, value=str(pdef.default) if pdef.default is not None else "")
        ws.cell(row=r, column=5, value=", ".join(pdef.choices) if pdef.choices else "")
        ws.cell(row=r, column=6, value=pdef.help).alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 6
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 20
    ws.column_dimensions["F"].width = 90


def write_board(path: Path = CONTROL_BOARD_PATH) -> Path:
    """(Re)generate the board from param_spec, preserving any existing Runs rows and
    Settings overrides. Safe to call repeatedly — it only ever adds columns the schema
    has grown, never drops user data (a column the schema no longer has is reported,
    not deleted, so nothing vanishes silently)."""
    preserved_rows = _existing_rows(path)
    preserved_settings = _existing_settings(path)

    CONTROL_ROOT.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)   # drop the default blank sheet
    _write_runs_sheet(wb, preserved_rows)
    _write_settings_sheet(wb, preserved_settings)
    _write_legend_sheet(wb)
    wb.save(path)
    return path


if __name__ == "__main__":
    # Quick manual check: `python control_board.py` regenerates then prints a summary.
    p = write_board()
    print(f"Wrote {p}")
    result = read_board(p)
    print(f"{len(result.runs)} row(s), {len(result.active_runs)} active, "
          f"ok={result.ok}")
