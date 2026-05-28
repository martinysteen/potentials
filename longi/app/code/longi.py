"""
Longi Pipeline Orchestrator

Manages execution of all longi_*.py indicator calculation modules.
Handles dependencies, parallel execution where possible, error handling, and logging.
(Input data fetching is handled by fetch_input.sh before this runs)
"""

import argparse
import csv
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

INPUT_DIR = Path(__file__).parent.parent / "input"
POTDAT_FILE = INPUT_DIR / "PotDat.csv"
ACROSS_DIR = Path(__file__).parent.parent / "across"


@dataclass
class Module:
    """Definition of a processing module."""
    name: str  # Display name
    script: str  # Python script filename (e.g., "longi_rsi.py")
    depends_on: List[str]  # List of module names this depends on

    @property
    def script_path(self) -> Path:
        """Get full path to the script."""
        return Path(__file__).parent / self.script


# Module registry - defines all processing modules and their dependencies
# Add new modules here as they are developed
MODULES: Dict[str, Module] = {
    "rsi": Module(
        name="RSI14",
        script="longi_rsi.py",
        depends_on=[],  # No dependencies - can run first
    ),
    "macd": Module(
        name="MACD(4,15,9)",
        script="longi_macd.py",
        depends_on=[],  # Independent - can run in parallel with RSI
    ),
    "performance": Module(
        name="Performance (1d/1w/1m/3m/6m/1y)",
        script="longi_performance.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "rank": Module(
        name="Average Rank Across Periods",
        script="longi_rank.py",
        depends_on=["performance"],  # Depends on all 6 performance files
    ),
    "medians": Module(
        name="Rolling Medians (10d/20d/50d/100d)",
        script="longi_medians.py",
        depends_on=["rank"],  # Depends on longi_rank.csv
    ),
    "stepup": Module(
        name="Step-up Count",
        script="longi_stepup.py",
        depends_on=["medians"],  # Depends on all 4 median files
    ),
    "spr100d": Module(
        name="Spread to 100-day Maximum",
        script="longi_spr100d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "spr250d": Module(
        name="Spread to 250-day Maximum",
        script="longi_spr250d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "vola20d": Module(
        name="20-day Volatility (Returns-based)",
        script="longi_vola20d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "vola100d": Module(
        name="100-day Volatility (Returns-based)",
        script="longi_vola100d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "ma10": Module(
        name="10-day Simple Moving Average",
        script="longi_ma10.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "ma20": Module(
        name="20-day Simple Moving Average",
        script="longi_ma20.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "ma50": Module(
        name="50-day Simple Moving Average",
        script="longi_ma50.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "ma200": Module(
        name="200-day Simple Moving Average",
        script="longi_ma200.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "PdivMA20": Module(
        name="Price / MA20 Ratio",
        script="longi_PdivMA20.py",
        depends_on=["ma20"],  # Depends on longi_ma20.csv
    ),
    "PdivMA50": Module(
        name="Price / MA50 Ratio",
        script="longi_PdivMA50.py",
        depends_on=["ma50"],  # Depends on longi_ma50.csv
    ),
    "PdivMA200": Module(
        name="Price / MA200 Ratio",
        script="longi_PdivMA200.py",
        depends_on=["ma200"],  # Depends on longi_ma200.csv
    ),
    "grp_GICS_1yr": Module(
        name="GICS Sector-Aggregated 1-Year Growth",
        script="longi_grp_GICS_1yr.py",
        depends_on=["performance"],  # Depends on longi_per1y.csv
    ),
    "grp_Sector2_1yr": Module(
        name="Sector2-Aggregated 1-Year Growth",
        script="longi_grp_Sector2_1yr.py",
        depends_on=["performance"],  # Depends on longi_per1y.csv
    ),
    "grp_GICS_3m": Module(
        name="GICS Sector-Aggregated 3-Month Growth",
        script="longi_grp_GICS_3m.py",
        depends_on=["performance"],  # Depends on longi_per3m.csv
    ),
    "grp_Sector2_3m": Module(
        name="Sector2-Aggregated 3-Month Growth",
        script="longi_grp_Sector2_3m.py",
        depends_on=["performance"],  # Depends on longi_per3m.csv
    ),
    "macd_Z": Module(
        name="MACD Zero-Crossing Detection",
        script="longi_macd_Z.py",
        depends_on=["macd"],  # Depends on longi_macd_histogram.csv
    ),
    "sh3m": Module(
        name="3-Month Sharpe Ratio",
        script="longi_sh3m.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "sh6m": Module(
        name="6-Month Sharpe Ratio",
        script="longi_sh6m.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "sh1yr": Module(
        name="1-Year Sharpe Ratio",
        script="longi_sh1yr.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "beta3m": Module(
        name="3-Month Beta",
        script="longi_beta3m.py",
        depends_on=[],  # Independent - reads PotDat.csv + Stamdata.csv
    ),
    "beta6m": Module(
        name="6-Month Beta",
        script="longi_beta6m.py",
        depends_on=[],  # Independent - reads PotDat.csv + Stamdata.csv
    ),
    "beta1yr": Module(
        name="1-Year Beta",
        script="longi_beta1yr.py",
        depends_on=[],  # Independent - reads PotDat.csv + Stamdata.csv
    ),
    "future_gain20d": Module(
        name="20-Day Future Gain",
        script="future_gain20d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "future_gain50d": Module(
        name="50-Day Future Gain",
        script="future_gain50d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "GICS_1yr": Module(
        name="GICS 1-Year Sector Performance per Ticker",
        script="longi_GICS_1yr.py",
        depends_on=["grp_GICS_1yr"],  # Depends on longi_grp_GICS_1yr.csv
    ),
    "Sector2_1yr": Module(
        name="Sector2 1-Year Sector Performance per Ticker",
        script="longi_Sector2_1yr.py",
        depends_on=["grp_Sector2_1yr"],  # Depends on longi_grp_Sector2_1yr.csv
    ),
    "GICS_3m": Module(
        name="GICS 3-Month Sector Performance per Ticker",
        script="longi_GICS_3m.py",
        depends_on=["grp_GICS_3m"],  # Depends on longi_grp_GICS_3m.csv
    ),
    "Sector2_3m": Module(
        name="Sector2 3-Month Sector Performance per Ticker",
        script="longi_Sector2_3m.py",
        depends_on=["grp_Sector2_3m"],  # Depends on longi_grp_Sector2_3m.csv
    ),
    "trump": Module(
        name="Trump Tariff Index (origin daynum 1863)",
        script="longi_trump.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "iran": Module(
        name="Iran War Index (origin daynum 2094)",
        script="longi_iran.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "coreindex": Module(
        name="CoreIndex Price per Ticker",
        script="longi_coreindex.py",
        depends_on=[],  # Independent - reads PotDat.csv + Stamdata.csv
    ),
    "coreindexRSI": Module(
        name="CoreIndex RSI per Ticker",
        script="longi_coreindexRSI.py",
        depends_on=["rsi"],  # Depends on longi_rsi.csv
    ),
    "win_loss": Module(
        name="Daily Win/Loss Production Output",
        script="aux_win-loss.py",
        depends_on=[
            "beta3m",
            "coreindex",
            "coreindexRSI",
            "GICS_3m",
            "ma10",
            "ma20",
            "ma50",
            "macd",
            "medians",
            "PdivMA50",
            "performance",
            "rsi",
            "Sector2_3m",
            "sh3m",
            "spr100d",
            "stepup",
            "vola20d",
            "vola100d",
            "future_gain20d",
            "future_gain50d",
        ],
    ),
    "winloss_probs": Module(
        name="Win/Loss Probability Matrices",
        script="longi_winloss_probs.py",
        depends_on=["win_loss"],  # Serialize after daily aux output; uses same prerequisites
    ),
    "across": Module(
        name="Cross-sectional Data Extraction",
        script="aux_across.py",
        depends_on=["rsi", "macd", "macd_Z", "performance", "rank", "medians", "stepup", "spr100d", "spr250d", "vola20d", "vola100d", "ma20", "ma50", "ma200", "PdivMA20", "PdivMA50", "PdivMA200", "sh3m", "sh6m", "sh1yr", "beta3m", "beta6m", "beta1yr", "future_gain20d", "future_gain50d", "grp_GICS_1yr", "grp_Sector2_1yr", "grp_GICS_3m", "grp_Sector2_3m", "GICS_1yr", "Sector2_1yr", "GICS_3m", "Sector2_3m", "coreindex", "coreindexRSI", "winloss_probs"],  # Depends on ALL modules - must run last
    ),
    "deciles": Module(
        name="Decile Boundaries",
        script="aux_deciles.py",
        depends_on=["across"],  # Runs after all indicators are computed
    ),
    # Add more modules here:
    # "module_name": Module(
    #     name="Display Name",
    #     script="longi_xxx.py",
    #     depends_on=["rsi"],  # or [] for independent, or ["rsi", "macd"] for multiple deps
    # ),
}


class ModuleExecutor:
    """Handles execution of modules with dependency management."""

    def __init__(
        self,
        module_args: Optional[Dict[str, List[str]]] = None,
        module_timeout_sec: int = 600,
    ):
        self.completed: Set[str] = set()
        self.failed: Set[str] = set()
        self.module_args = module_args or {}
        self.module_timeout_sec = int(module_timeout_sec)

    def can_execute(self, module_id: str) -> bool:
        """
        Check if a module can be executed (all dependencies satisfied).

        Args:
            module_id: Module identifier

        Returns:
            True if module can be executed
        """
        module = MODULES[module_id]

        # Check if already completed or failed
        if module_id in self.completed or module_id in self.failed:
            return False

        # Check if any dependency failed
        for dep in module.depends_on:
            if dep in self.failed:
                return False

        # Check if all dependencies are completed
        for dep in module.depends_on:
            if dep not in self.completed:
                return False

        return True

    def get_ready_modules(self) -> List[str]:
        """
        Get list of modules that are ready to execute.

        Returns:
            List of module IDs ready for execution
        """
        ready = []
        for module_id in MODULES:
            if self.can_execute(module_id):
                ready.append(module_id)
        return ready

    def execute_module(self, module_id: str) -> tuple[str, int, str]:
        """
        Execute a single module.

        Args:
            module_id: Module identifier

        Returns:
            Tuple of (module_id, exit_code, output)
        """
        module = MODULES[module_id]
        extra_args = self.module_args.get(module_id, [])
        cmd = [sys.executable, module.script] + extra_args
        timeout_sec = self.module_timeout_sec

        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Starting: {module.name} ({module.script})")

        try:
            # Execute the module
            result = subprocess.run(
                cmd,
                cwd=module.script_path.parent,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )

            exit_code = result.returncode
            output = result.stdout + result.stderr

            return (module_id, exit_code, output)

        except subprocess.TimeoutExpired:
            error_msg = f"ERROR: {module.name} timed out after {timeout_sec} seconds"
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
            return (module_id, 124, error_msg)  # 124 = timeout exit code

        except Exception as e:
            error_msg = f"ERROR: {module.name} failed with exception: {e}"
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
            return (module_id, 1, error_msg)

    def run_pipeline(self, max_parallel: int = 4) -> int:
        """
        Run all modules in the pipeline, respecting dependencies.

        Args:
            max_parallel: Maximum number of modules to run in parallel

        Returns:
            Exit code (0 = success, 1 = any module failed)
        """
        print(f"longi.py: Pipeline orchestrator started")
        print(f"  Modules registered: {len(MODULES)}, max parallel: {max_parallel}")
        print()

        # Validate dependencies
        if not self._validate_dependencies():
            return 1

        # Execute modules in waves based on dependencies
        wave_num = 1
        overall_success = True

        while True:
            # Get modules ready to execute
            ready = self.get_ready_modules()

            if not ready:
                # Check if all modules are done
                if len(self.completed) + len(self.failed) == len(MODULES):
                    break  # Pipeline complete
                else:
                    # Deadlock - some modules can't execute due to failed dependencies
                    remaining = set(MODULES.keys()) - self.completed - self.failed
                    print(f"ERROR: Pipeline deadlock - remaining modules cannot execute: {remaining}")
                    overall_success = False
                    break

            print(f"=== Wave {wave_num}: {len(ready)} module(s) ready to execute ===")

            # Execute ready modules in parallel
            with ProcessPoolExecutor(max_workers=min(max_parallel, len(ready))) as executor:
                # Submit all ready modules
                future_to_module = {
                    executor.submit(self.execute_module, module_id): module_id
                    for module_id in ready
                }

                # Process results as they complete
                for future in as_completed(future_to_module):
                    module_id, exit_code, output = future.result()
                    module = MODULES[module_id]

                    # Print module output
                    print()
                    print(f"--- {module.name} ({module.script}) ---")
                    print(output.rstrip())
                    print()

                    # Update status
                    if exit_code == 0:
                        self.completed.add(module_id)
                        print(f"  [{datetime.now().strftime('%H:%M:%S')}] SUCCESS: {module.name} completed")
                    else:
                        self.failed.add(module_id)
                        print(f"  [{datetime.now().strftime('%H:%M:%S')}] FAILED: {module.name} (exit code: {exit_code})")
                        overall_success = False

            print()
            wave_num += 1

        # Summary
        print(f"longi.py: Pipeline orchestrator finished")
        print(f"  Modules completed: {len(self.completed)}/{len(MODULES)}")
        if self.failed:
            print(f"Modules failed: {len(self.failed)} - {', '.join(MODULES[mid].name for mid in self.failed)}")

        return 0 if overall_success else 1

    def _validate_dependencies(self) -> bool:
        """
        Validate that all module dependencies exist and there are no circular dependencies.

        Returns:
            True if dependencies are valid
        """
        # Check all dependencies exist
        for module_id, module in MODULES.items():
            for dep in module.depends_on:
                if dep not in MODULES:
                    print(f"ERROR: Module '{module_id}' depends on unknown module '{dep}'")
                    return False

        # Check for circular dependencies using DFS
        def has_cycle(node: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for dep in MODULES[node].depends_on:
                if dep not in visited:
                    if has_cycle(dep, visited, rec_stack):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        visited = set()
        for module_id in MODULES:
            if module_id not in visited:
                if has_cycle(module_id, visited, set()):
                    print(f"ERROR: Circular dependency detected involving module '{module_id}'")
                    return False

        return True


def parse_args() -> argparse.Namespace:
    """Parse longi orchestrator command-line arguments."""
    parser = argparse.ArgumentParser(description="Run longi pipeline with optional historical across/prob generation.")
    parser.add_argument("--max-parallel", type=int, default=4, help="Maximum modules to run in parallel.")
    parser.add_argument(
        "--module-timeout-sec",
        type=int,
        default=600,
        help="Timeout per module subprocess in seconds (increase for backfills).",
    )

    # across-file generation controls (exposed at orchestrator level)
    parser.add_argument("--across-daynum", type=int, default=None, help="Create/focus on a specific across daynum.")
    parser.add_argument(
        "--across-max-daynums",
        type=int,
        default=None,
        help="Create newest N across files (newest-first from PotDat header order).",
    )
    parser.add_argument(
        "--across-prune",
        action="store_true",
        help="After successful generation, delete across files not in the requested across target set.",
    )
    parser.add_argument(
        "--across-reset",
        action="store_true",
        help="Before generation, delete all local across files (requires explicit across target selection).",
    )

    # win/loss probability history controls (pass-through to longi_winloss_probs.py)
    parser.add_argument("--prob-daynum", type=int, default=None, help="Compute win/loss probs for one daynum.")
    parser.add_argument(
        "--prob-backfill-all",
        action="store_true",
        help="Compute win/loss probs historically (all scoreable daynums; can be slow).",
    )
    parser.add_argument(
        "--prob-max-daynums",
        type=int,
        default=None,
        help="Limit win/loss probability computation to newest N daynums (used with backfill mode).",
    )
    return parser.parse_args()


def read_potdat_daynums() -> List[int]:
    """Read numeric daynums from PotDat header in source order (newest-first)."""
    with open(POTDAT_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)

    daynums: List[int] = []
    for col in header[1:]:
        s = str(col).strip()
        if s.isdigit():
            daynums.append(int(s))
    return daynums


def select_across_daynums(args: argparse.Namespace) -> Optional[List[int]]:
    """Resolve requested across targets from orchestrator flags."""
    if args.across_daynum is not None and args.across_max_daynums is not None:
        raise ValueError("Use either --across-daynum or --across-max-daynums, not both.")

    if args.across_daynum is not None:
        return [int(args.across_daynum)]

    if args.across_max_daynums is not None:
        if int(args.across_max_daynums) <= 0:
            raise ValueError("--across-max-daynums must be > 0.")
        daynums = read_potdat_daynums()
        return daynums[: int(args.across_max_daynums)]

    return None


def validate_across_retention_flags(args: argparse.Namespace, across_targets: Optional[List[int]]) -> None:
    """Validate safety rules for across deletion/pruning options."""
    if args.across_prune and args.across_reset:
        raise ValueError("Use either --across-prune or --across-reset, not both.")

    if (args.across_prune or args.across_reset) and not across_targets:
        raise ValueError(
            "--across-prune/--across-reset require explicit across targets "
            "(use --across-daynum or --across-max-daynums)."
        )


def get_existing_across_files() -> Dict[int, Path]:
    """Return existing across files keyed by daynum."""
    out: Dict[int, Path] = {}
    if not ACROSS_DIR.exists():
        return out

    for path in ACROSS_DIR.glob("longi_across_*.csv"):
        name = path.name
        if not (name.startswith("longi_across_") and name.endswith(".csv")):
            continue
        daynum_str = name[len("longi_across_") : -4]
        if daynum_str.isdigit():
            out[int(daynum_str)] = path
    return out


def delete_across_files(daynums: List[int], reason: str) -> int:
    """Delete selected across files; returns count deleted."""
    if not daynums:
        print(f"longi.py: {reason} - nothing to delete")
        return 0

    existing = get_existing_across_files()
    to_delete = [existing[d] for d in daynums if d in existing]

    print(f"longi.py: {reason}")
    print(f"  Requested deletes: {len(daynums)}; existing files to delete: {len(to_delete)}")
    if not to_delete:
        return 0

    for path in sorted(to_delete, key=lambda p: p.name):
        try:
            path.unlink()
            print(f"  deleted {path.name}")
        except Exception as e:
            raise RuntimeError(f"Failed to delete {path}: {e}") from e
    return len(to_delete)


def reset_all_across_files() -> int:
    """Delete all local across files."""
    existing = get_existing_across_files()
    return delete_across_files(sorted(existing.keys()), reason="Across reset (delete all local across files)")


def prune_across_files_to_targets(target_daynums: List[int]) -> int:
    """Delete local across files not in target set."""
    target_set = {int(d) for d in target_daynums}
    existing = get_existing_across_files()
    stale_daynums = sorted([d for d in existing.keys() if d not in target_set])
    return delete_across_files(
        stale_daynums,
        reason=f"Across prune (keep exactly {len(target_set)} target daynum file(s))",
    )


def build_winloss_probs_module_args(args: argparse.Namespace, across_targets: Optional[List[int]]) -> List[str]:
    """
    Build args for longi_winloss_probs.py.

    If no explicit prob flags are given, derive sensible defaults from across flags so
    prob matrices line up with the across files being requested.
    """
    if args.prob_daynum is not None and args.prob_backfill_all:
        raise ValueError("Use either --prob-daynum or --prob-backfill-all, not both.")
    if args.prob_daynum is not None and args.prob_max_daynums is not None:
        raise ValueError("Use either --prob-daynum or --prob-max-daynums, not both.")

    explicit_prob_flags = any(
        [
            args.prob_daynum is not None,
            bool(args.prob_backfill_all),
            args.prob_max_daynums is not None,
        ]
    )

    out: List[str] = []
    if explicit_prob_flags:
        if args.prob_daynum is not None:
            out.extend(["--daynum", str(int(args.prob_daynum))])
        if args.prob_backfill_all or (args.prob_daynum is None and args.prob_max_daynums is not None):
            out.append("--backfill-all")
        if args.prob_max_daynums is not None:
            out.extend(["--max-daynums", str(int(args.prob_max_daynums))])
        return out

    # No explicit prob flags: align with requested across outputs.
    if not across_targets:
        return out  # default newest-only mode in longi_winloss_probs.py

    if len(across_targets) == 1:
        out.extend(["--daynum", str(int(across_targets[0]))])
        return out

    out.append("--backfill-all")
    out.extend(["--max-daynums", str(len(across_targets))])
    return out


def run_aux_across_for_daynum(daynum: int, timeout_sec: int) -> int:
    """Run aux_across.py for a specific daynum and print output in orchestrator style."""
    script_path = Path(__file__).parent / "aux_across.py"
    cmd = [sys.executable, str(script_path), str(int(daynum))]

    print()
    print(f"--- Cross-sectional Data Extraction (aux_across.py) [extra daynum {daynum}] ---")
    try:
        result = subprocess.run(
            cmd,
            cwd=script_path.parent,
            capture_output=True,
            text=True,
            timeout=int(timeout_sec),
        )
        output = (result.stdout or "") + (result.stderr or "")
        print(output.rstrip())
        return int(result.returncode)
    except subprocess.TimeoutExpired:
        print(f"ERROR: aux_across.py timed out after {int(timeout_sec)} seconds for daynum {daynum}")
        return 124
    except Exception as e:
        print(f"ERROR: aux_across.py failed for daynum {daynum}: {e}")
        return 1


def run_additional_across_daynums(daynums: List[int], timeout_sec: int) -> int:
    """Create additional across files after the main pipeline across module has run."""
    if not daynums:
        return 0

    print()
    print(f"longi.py: Generating additional across files for {len(daynums)} daynum(s)")
    if len(daynums) <= 10:
        print(f"  Daynums: {', '.join(map(str, daynums))}")
    else:
        print(f"  Range: {daynums[0]} .. {daynums[-1]}")

    for idx, daynum in enumerate(daynums, start=1):
        print(f"  [{idx}/{len(daynums)}] daynum {daynum}")
        rc = run_aux_across_for_daynum(daynum=daynum, timeout_sec=timeout_sec)
        if rc != 0:
            print(f"ERROR: Failed to generate across file for daynum {daynum} (exit code {rc})")
            return rc

    print("longi.py: Additional across generation completed")
    return 0


def main() -> int:
    """
    Main execution function.
    Runs all processing modules.
    (Input data fetching is handled by fetch_input.sh before this runs)
    (Upload is handled by upload_output.sh after this runs)

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    args = parse_args()

    try:
        across_targets = select_across_daynums(args)
        validate_across_retention_flags(args, across_targets)
        winloss_prob_args = build_winloss_probs_module_args(args, across_targets)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    module_args: Dict[str, List[str]] = {}
    if winloss_prob_args:
        module_args["winloss_probs"] = winloss_prob_args

    # Make the pipeline's built-in across module target the first requested daynum.
    # If multiple across files are requested, additional daynums are generated after the pipeline.
    if across_targets:
        module_args["across"] = [str(int(across_targets[0]))]

    print("longi.py: Orchestrator options")
    print(f"  max_parallel={int(args.max_parallel)}, module_timeout_sec={int(args.module_timeout_sec)}")
    if across_targets:
        if len(across_targets) == 1:
            print(f"  across target daynum: {across_targets[0]}")
        else:
            print(f"  across target daynums (newest-first): {len(across_targets)}")
    if args.across_reset:
        print("  across retention: reset (delete all local across files before generation)")
    elif args.across_prune:
        print("  across retention: prune (delete non-target across files after successful generation)")
    if winloss_prob_args:
        print(f"  winloss_probs args: {' '.join(winloss_prob_args)}")
    print()

    if args.across_reset:
        try:
            reset_all_across_files()
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return 1

    executor = ModuleExecutor(module_args=module_args, module_timeout_sec=int(args.module_timeout_sec))
    exit_code = executor.run_pipeline(max_parallel=int(args.max_parallel))

    if exit_code != 0:
        print("** Pipeline FAILED **")
        return 1

    # If multiple across daynums were requested, generate the remaining files now.
    if across_targets and len(across_targets) > 1:
        extra_daynums = across_targets[1:]
        rc_extra = run_additional_across_daynums(
            daynums=extra_daynums,
            timeout_sec=int(args.module_timeout_sec),
        )
        if rc_extra != 0:
            print("** Pipeline completed, but historical across generation FAILED **")
            return 1

    if args.across_prune and across_targets:
        try:
            prune_across_files_to_targets(across_targets)
        except RuntimeError as e:
            print(f"** Pipeline completed, but across prune FAILED **")
            print(f"ERROR: {e}")
            return 1

    print("\n** Pipeline completed successfully **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
