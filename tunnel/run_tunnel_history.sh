#!/bin/bash
# Nightly historical tunnels: tunnel_history.py rebuilds the WHOLE history (every daynum x
# all tickers, one long CSV) into app/output/history/ and publishes it to repositoryRTBI/Tunnel/history/.
# Always a full rebuild, never incremental (PotDat is corrected across the whole past).
# Shares /tmp/tunnel.lock with run_tunnel.sh so the two never touch output/ at the same time:
# this one WAITS (up to 30 min) for the nightly build instead of skipping.
# Model: run_tunnel.sh. Cron 20 0 * * * (the nightly build is done by then, ~1 min).

LOGFILE=~/logs/run_tunnel_history.log
trap '' HUP
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_tunnel_history.sh START: $(date) ==="

exec 200>/tmp/tunnel.lock
if ! flock -w 1800 200; then
    echo "ERROR: tunnel.lock still held after 30 min - giving up"
    echo "=== run_tunnel_history.sh END: $(date) ==="
    exit 1
fi

cd /home/sm/potentials/tunnel/app/code || { echo "ERROR: cd failed"; exit 1; }
CONDA_BASE="$HOME/miniconda3"
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
else
    echo "ERROR: Cannot find conda.sh at $CONDA_BASE/etc/profile.d/conda.sh"; exit 1
fi
conda activate potsystem_env || { echo "ERROR: Failed to activate 'potsystem_env'"; exit 1; }

python3 tunnel_history.py "$@" < /dev/null
RC=$?
if [ $RC -ne 0 ]; then
    echo "ERROR: tunnel_history.py exited $RC - keeping the previous history, no publish"
    echo "=== run_tunnel_history.sh END: $(date) ==="
    exit $RC
fi

echo ""
echo "--- Publishing app/output/ to repositoryRTBI/Tunnel/ ---"
python3 /home/sm/potentials/shared/app/code/repository.py publish tunnel
PUB_RC=$?
[ $PUB_RC -ne 0 ] && echo "ERROR: publish failed with exit code $PUB_RC"
echo "=== run_tunnel_history.sh END: $(date) ==="
exit $PUB_RC
