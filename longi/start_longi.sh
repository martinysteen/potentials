#!/bin/bash

LOGFILE=~/start_longi.log
# Delete log file if it exists
# if [ -f "$LOGFILE" ]; then
#    rm "$LOGFILE"
# fi

exec 3>&1
exec >> $LOGFILE 2>&1
echo "=== start_longi.sh START: $(date) ==="

# Change to working directory
cd /home/sm/potentials/longi/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/longi/app/code"
    exit 1
}

# CRITICAL: Initialize conda first
# Replace with your actual conda installation path if different
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

# Run orchestrator (downloads data, runs all calculations, uploads results)
echo "Starting longi.py orchestrator..."
python3 longi.py
FINAL_EXIT_CODE=$?
echo "longi.py exit code: $FINAL_EXIT_CODE"

echo "=== start_longi.sh END: $(date) =========================================================="
echo ""

# Display log file when on TTY
if [ -t 3 ]; then
    exec >&3
    echo "** Content of log: $LOGFILE"
    cat "$LOGFILE"
fi

exit $FINAL_EXIT_CODE
