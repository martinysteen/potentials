#!/bin/bash
# Main entry point: build potrank2.csv -> upload -> (mirror refreshes on its own cron).
# The ONE entry point for both cron (:25 hourly) and a manual refresh (potrank.cmd option 1)
# -- deliberately the same script, so a button-triggered run and a scheduled one can never
# drift apart. Model: ~/potentials/longi/start_longi.sh / ~/potentials/group_conformity/run_conf.sh
#
# Unlike those two, this script can now be fired by a human while cron is also about to fire
# it (SM asked for an immediate-update button after the plan was otherwise settled) -- the
# flock below is what makes that safe: two builds racing into the same app/output/potrank2.csv
# and then both `rclone sync`-ing the same Drive file is exactly the failure an on-demand
# button would otherwise invite.

LOGFILE=~/logs/run_potrank.log

# Ignore SIGHUP so SSH disconnect does not kill the pipeline
trap '' HUP

# Log to file; also mirror to terminal while it is connected (tee errors are suppressed
# so a closed terminal does not break the pipe and kill the script)
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_potrank.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# Non-blocking lock on fd 200, held for the rest of this process's life and released
# automatically on any exit (normal, error, or killed) -- no separate cleanup needed. A
# second run finding the lock held prints one line and exits 0: this is an expected
# outcome of a manual refresh landing near the :25 cron tick, not a failure.
LOCKFILE=/tmp/potrank.lock
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "potrank already running - nothing to do: $(date)"
    echo "=== run_potrank.sh END: $(date) ==="
    exit 0
fi

cd /home/sm/potentials/potrank/app/code || {
    echo "ERROR: Failed to change to /home/sm/potentials/potrank/app/code"
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

conda activate potsystem_env
if [ $? -eq 0 ]; then
    echo "Conda environment 'potsystem_env' activated successfully"
else
    echo "ERROR: Failed to activate conda environment 'potsystem_env'"
    exit 1
fi

echo "Using Python: $(which python3)"

# Build potrank2.csv. preflight (inside potrank.py) does its own live-repository read and
# vintage check -- no separate fetch step, same shape as strategy_grp2/conductor.py.
echo ""
echo "--- Running potrank.py ---"
python3 potrank.py "$@"
BUILD_EXIT_CODE=$?
echo "potrank.py exit code: $BUILD_EXIT_CODE"
if [ $BUILD_EXIT_CODE -ne 0 ]; then
    echo "ERROR: potrank.py failed, skipping upload"
    echo "=== run_potrank.sh END: $(date) ==="
    exit $BUILD_EXIT_CODE
fi

# Publish potrank2.csv to Drive and the local mirror
echo ""
echo "--- Uploading potrank2.csv to Google Drive's repositoryRTBI root ---"
/home/sm/potentials/potrank/upload_output.sh
UPLOAD_EXIT_CODE=$?
if [ $UPLOAD_EXIT_CODE -ne 0 ]; then
    echo "ERROR: upload_output.sh failed with exit code $UPLOAD_EXIT_CODE"
fi

# Deliberately NOT calling repositoryRTBI/sync_rtbi.sh here. A producer's job ends when its
# own output is published; refreshing the local mirror is the mirror's business, on the
# mirror's own cron. See longi/start_longi.sh for the fuller version of this note.

FINAL_EXIT_CODE=$UPLOAD_EXIT_CODE
echo ""
echo "=== run_potrank.sh END: $(date) ==="

exit $FINAL_EXIT_CODE
