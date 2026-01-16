#!/bin/bash
# Dette script kan testes med 'source start_yf3.sh'

LOGFILE=/home/sm/start_yf3.log
# Delete log file if it exists
# if [ -f "$LOGFILE" ]; then
#    rm "$LOGFILE"
# fi

exec 3>&1
exec >> $LOGFILE 2>&1
echo "=== start_yf3.sh START: $(date) ==="

# Change to working directory
cd /home/sm/potentials/yf3/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/yf3/app/code"
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
conda activate yf3_env
if [ $? -eq 0 ]; then
    echo "Conda environment 'yf3_env' activated successfully"
else
    echo "ERROR: Failed to activate conda environment 'yf3_env'"
    exit 1
fi

# Show which python is being used
echo "Using Python: $(which python3)"
echo "Python version: $(python3 --version)"

# Run the script
python3 yf3.py
PYTHON_EXIT_CODE=$?

echo "Python script exit code: $PYTHON_EXIT_CODE"
echo "=== start_yf3.sh END: $(date) ==="

# Display log file when on TTY
if [ -t 3 ]; then
    exec >&3
    echo "** Content of log: $LOGFILE"
    cat "$LOGFILE"
fi

exit $PYTHON_EXIT_CODE
