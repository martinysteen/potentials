#!/bin/bash

LOGFILE=~/start_longi.log

# Use tee to show output in real-time AND log to file
# All output goes to both terminal and log file
# Note: tee without -a overwrites the log file each run (use -a to append instead)
exec > >(tee "$LOGFILE") 2>&1

echo "=== start_longi.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# Change to working directory
cd /home/sm/potentials/longi/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/longi/app/code"
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

# Show which python is being used
echo "Using Python: $(which python3)"
echo "Python version: $(python3 --version)"

# Fetch input data using external provider
echo ""
echo "--- Fetching input data ---"
/home/sm/potentials/longi/fetch_input.sh
FETCH_EXIT_CODE=$?
if [ $FETCH_EXIT_CODE -ne 0 ]; then
    echo "ERROR: fetch_input.sh failed with exit code $FETCH_EXIT_CODE"
    exit $FETCH_EXIT_CODE
fi
echo "Input data fetched successfully"

# Run orchestrator (runs all calculations)
echo ""
echo "--- Starting longi.py orchestrator ---"
python3 longi.py
LONGI_EXIT_CODE=$?
echo "longi.py exit code: $LONGI_EXIT_CODE"

if [ $LONGI_EXIT_CODE -ne 0 ]; then
    echo "ERROR: longi.py failed, skipping upload"
    echo "=== start_longi.sh END: $(date) =========================================================="
    exit $LONGI_EXIT_CODE
fi

# Upload output data using external provider
echo ""
echo "--- Uploading output data ---"
/home/sm/potentials/longi/upload_output.sh
UPLOAD_EXIT_CODE=$?
if [ $UPLOAD_EXIT_CODE -ne 0 ]; then
    echo "ERROR: upload_output.sh failed with exit code $UPLOAD_EXIT_CODE"
fi

FINAL_EXIT_CODE=$UPLOAD_EXIT_CODE
echo ""
echo "=== start_longi.sh END: $(date) =========================================================="

exit $FINAL_EXIT_CODE
