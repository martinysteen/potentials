#!/bin/bash
# Main entry point: fetch -> produce -> upload -> sync back to Ubuntu's repositoryRTBI mirror.
# Model: ~/potentials/longi/start_longi.sh

LOGFILE=~/logs/run_conf.log

# Ignore SIGHUP so SSH disconnect does not kill the pipeline
trap '' HUP

# Log to file; also mirror to terminal while it is connected (tee errors are suppressed
# so a closed terminal does not break the pipe and kill the script)
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_conf.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# Change to working directory
cd /home/sm/potentials/group_conformity/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/group_conformity/app/code"
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

# Fetch input data
echo ""
echo "--- Fetching input data ---"
/home/sm/potentials/group_conformity/fetch_input.sh
FETCH_EXIT_CODE=$?
if [ $FETCH_EXIT_CODE -ne 0 ]; then
    echo "ERROR: fetch_input.sh failed with exit code $FETCH_EXIT_CODE"
    exit $FETCH_EXIT_CODE
fi
echo "Input data fetched successfully"

# Build the conformity grade + controls
echo ""
echo "--- Running analyze_conformity.py ---"
python3 analyze_conformity.py
CONF_EXIT_CODE=$?
echo "analyze_conformity.py exit code: $CONF_EXIT_CODE"
if [ $CONF_EXIT_CODE -ne 0 ]; then
    echo "ERROR: analyze_conformity.py failed, skipping gains verdict and upload"
    echo "=== run_conf.sh END: $(date) =========================================================="
    exit $CONF_EXIT_CODE
fi

# Gain-dispersion verdict (report-only; not uploaded, but worth keeping current)
echo ""
echo "--- Running analyze_conformity_gains.py ---"
python3 analyze_conformity_gains.py
GAINS_EXIT_CODE=$?
echo "analyze_conformity_gains.py exit code: $GAINS_EXIT_CODE"
if [ $GAINS_EXIT_CODE -ne 0 ]; then
    echo "WARNING: analyze_conformity_gains.py failed, continuing to upload the grade anyway"
fi

# Upload the Longi-shaped factor files to central storage
echo ""
echo "--- Uploading conformity factor files to Google Drive's repositoryRTBI/Longi ---"
/home/sm/potentials/group_conformity/upload_output.sh
UPLOAD_EXIT_CODE=$?
if [ $UPLOAD_EXIT_CODE -ne 0 ]; then
    echo "ERROR: upload_output.sh failed with exit code $UPLOAD_EXIT_CODE"
fi

# Pull the freshly-uploaded files back into Ubuntu's repositoryRTBI mirror immediately,
# rather than waiting for the next scheduled sync_rtbi.sh tick
echo ""
echo "--- Synchronize Google Drive's repositoryRTBI with Ubuntu's mirror ---"
/home/sm/potentials/repositoryRTBI/sync_rtbi.sh
SYNC_EXIT_CODE=$?
if [ $SYNC_EXIT_CODE -ne 0 ]; then
    echo "ERROR: sync_rtbi.sh failed with exit code $SYNC_EXIT_CODE"
fi

FINAL_EXIT_CODE=$SYNC_EXIT_CODE
echo ""
echo "=== run_conf.sh END: $(date) =========================================================="

exit $FINAL_EXIT_CODE
