#!/bin/bash
# Upload the group-conformity Longi factor files to central storage (Google Drive).
# Can be called standalone after running analyze_conformity.py.
# Model: ~/potentials/longi/upload_output.sh

# Ignore SIGHUP so SSH disconnect does not kill the upload mid-sync
trap '' HUP

echo "=== Upload output data START: $(date) ==="

# Change to working directory
cd /home/sm/potentials/group_conformity/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/group_conformity/app/code"
    exit 1
}

# CRITICAL: Initialize conda first
CONDA_BASE="$HOME/miniconda3"

if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
else
    echo "ERROR: Cannot find conda.sh at $CONDA_BASE/etc/profile.d/conda.sh"
    exit 1
fi

# Activate the environment
conda activate potsystem_env
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to activate conda environment 'potsystem_env'"
    exit 1
fi

# Run upload script
python3 conformity_upload.py
UPLOAD_EXIT_CODE=$?

if [ $UPLOAD_EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Output uploaded successfully"
else
    echo "ERROR: conformity_upload.py failed with exit code: $UPLOAD_EXIT_CODE"
fi

echo "=== upload_output.sh END: $(date) ==="

exit $UPLOAD_EXIT_CODE
