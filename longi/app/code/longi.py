"""
Longi Pipeline Orchestrator

Manages execution of all longi_*.py indicator calculation modules.
Handles dependencies, parallel execution where possible, error handling, and logging.
(Input data fetching is handled by fetch_input.sh before this runs)
"""

import sys
import subprocess
import csv
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from longi_across import make_across, get_max_daynum_from_potdat


@dataclass
class Module:
    """Definition of a processing module."""
    name: str  # Display name
    script: str  # Python script filename (e.g., "longi_rsi.py")
    depends_on: List[str]  # List of module names this depends on
    timeout: int = 600  # Per-module timeout in seconds

    @property
    def script_path(self) -> Path:
        """Get full path to the script."""
        return Path(__file__).parent / self.script


# Module registry - defines all processing modules and their dependencies
# Add new modules here as they are developed
MODULES: Dict[str, Module] = {
    "price": Module(
        name="Price Snapshot (exact copy of PotDat.csv)",
        script="longi_price.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
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
    "quot1020": Module(
        name="MA10 / MA20 Quotient",
        script="longi_quot1020.py",
        depends_on=["ma10", "ma20"],  # Depends on longi_ma10.csv and longi_ma20.csv
    ),
    "quot2050": Module(
        name="MA20 / MA50 Quotient",
        script="longi_quot2050.py",
        depends_on=["ma20", "ma50"],  # Depends on longi_ma20.csv and longi_ma50.csv
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
    "coreindex": Module(
        name="CoreIndex Price per Ticker",
        script="longi_coreindex.py",
        depends_on=[],  # Independent - reads PotDat.csv and Stamdata.csv
    ),
    "coreindexRSI": Module(
        name="CoreIndex RSI per Ticker",
        script="longi_coreindexRSI.py",
        depends_on=["rsi"],  # Depends on longi_rsi.csv
    ),
    "beta3m": Module(
        name="3-Month Beta (Market Sensitivity)",
        script="longi_beta3m.py",
        depends_on=[],  # Independent - reads PotDat.csv and Stamdata.csv
    ),
    "beta6m": Module(
        name="6-Month Beta (Market Sensitivity)",
        script="longi_beta6m.py",
        depends_on=[],  # Independent - reads PotDat.csv and Stamdata.csv
    ),
    "beta1yr": Module(
        name="1-Year Beta (Market Sensitivity)",
        script="longi_beta1yr.py",
        depends_on=[],  # Independent - reads PotDat.csv and Stamdata.csv
    ),
    "trump": Module(
        name="Trump Tariff Price Index",
        script="longi_trump.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "iran": Module(
        name="Iran War Price Index",
        script="longi_iran.py",
        depends_on=[],  # Independent - reads only PotDat.csv
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
    "future_gain20d": Module(
        name="Future Gain 20-Day",
        script="future_gain20d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "future_gain50d": Module(
        name="Future Gain 50-Day",
        script="future_gain50d.py",
        depends_on=[],  # Independent - reads only PotDat.csv
    ),
    "across": Module(
        name="Cross-sectional Data Extraction",
        script="longi_across.py",
        depends_on=["rsi", "macd", "macd_Z", "performance", "rank", "medians", "stepup", "spr100d", "spr250d", "vola20d", "vola100d", "ma10", "ma20", "ma50", "ma200", "PdivMA20", "PdivMA50", "PdivMA200", "quot1020", "quot2050", "sh3m", "sh6m", "sh1yr", "grp_GICS_1yr", "grp_Sector2_1yr", "grp_GICS_3m", "grp_Sector2_3m", "coreindex", "coreindexRSI", "beta3m", "beta6m", "beta1yr", "trump", "iran"],  # Depends on ALL modules - must run last
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

    def __init__(self):
        self.completed: Set[str] = set()
        self.failed: Set[str] = set()

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

        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Starting: {module.name} ({module.script})")

        try:
            '''
            # Special handling for across module - call function directly
            if module_id == "across":
                max_daynum = get_max_daynum_from_potdat()
                if max_daynum is None:
                    error_msg = "ERROR: Failed to determine max daynum from PotDat.csv"
                    return (module_id, 1, error_msg)

                output_dir = Path(__file__).parent.parent / "output"
                exit_code = make_across(max_daynum, str(output_dir))
                return (module_id, exit_code, "")  # Output captured via make_across's print statements
            '''
        
            # Standard subprocess execution for other modules
            result = subprocess.run(
                [sys.executable, module.script],
                cwd=module.script_path.parent,
                capture_output=True,
                text=True,
                timeout=module.timeout,
            )

            exit_code = result.returncode
            output = result.stdout + result.stderr

            return (module_id, exit_code, output)

        except subprocess.TimeoutExpired:
            error_msg = f"ERROR: {module.name} timed out after {module.timeout} seconds"
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


def main() -> int:
    """
    Main execution function.
    Runs all processing modules.
    (Input data fetching is handled by fetch_input.sh before this runs)
    (Upload is handled by upload_output.sh after this runs)

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    executor = ModuleExecutor()
    exit_code = executor.run_pipeline(max_parallel=4)

    if exit_code != 0:
        print("** Pipeline FAILED **")
        return 1

    print("\n** Pipeline completed successfully **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
