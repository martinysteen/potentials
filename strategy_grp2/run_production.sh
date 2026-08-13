#!/bin/bash
# Cron entry point for strategy_grp2's production tick ONLY -- steps 0-2 for every row
# marked `P`, writing/Drive-publishing StrategicStocks_<daynum>.xlsx/.csv. Never touches `D`
# rows, never writes compare_strategies_<date>.xlsx. See DesignVersion2.md's 2026-08-13
# corrections for why P/D are independent and why only --production may ship this file.
# Model: ~/potentials/longi/start_longi.sh / ~/potentials/group_conformity/run_conf.sh

LOGFILE=~/logs/run_production.log

# Ignore SIGHUP so SSH disconnect does not kill the pipeline
trap '' HUP

# Log to file; also mirror to terminal while it is connected (tee errors are suppressed
# so a closed terminal does not break the pipe and kill the script)
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_production.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# Change to working directory
cd /home/sm/potentials/strategy_grp2/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/strategy_grp2/app/code"
    exit 1
}

# CRITICAL: Initialize conda first
CONDA_BASE="$HOME/miniconda3"
echo "Conda base directory: $CONDA_BASE"

if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
    echo "Conda initialized successfully"
else
    echo "ERROR: Cannot find conda.sh at $CONDA_BASE/etc/profile.d/conda.sh"
    exit 1
fi

# Now activate the environment
conda activate potsystem_env
if [ $? -eq 0 ]; then
    echo "Conda environment 'potsystem_env' activated successfully"
else
    echo "ERROR: Failed to activate conda environment 'potsystem_env'"
    exit 1
fi

echo "Using Python: $(which python3)"

# --production only -- reads rows marked P, never D. Deliberately NOT passing
# --board-open-ok: if SM has the board open in Excel when this fires, conductor.py stops
# itself (exit 2) rather than risk reading unsaved edits -- a cron-fired run should respect
# that guard exactly the same way a run fired by hand does.
echo ""
echo "--- Running conductor.py --production ---"
python conductor.py --production
PROD_EXIT_CODE=$?
echo "conductor.py --production exit code: $PROD_EXIT_CODE"

echo ""
echo "=== run_production.sh END: $(date) =========================================================="

exit $PROD_EXIT_CODE
